"""
Backfill PBD (BANT) snapshots for active deals.

Covers:
  1. Deals currently in PBD stages → generate BANT from deal_context
  2. Deals past PBD (active pipeline) → generate frozen BANT from their PBD history

Usage:
    python -m src.pipelines.pbd_snapshot.backfill [--limit N] [--dry-run]
"""

import argparse
import json
import time
import traceback

from src.db.client import supabase
from src.pipelines.pbd_snapshot.run import run, PBD_STAGES

EXCLUDE_STAGES = [
    "Opportunity lost", "Closed lost", "Closed Lost", "Closed won", "Closed Won",
    "Closed Won - Finance Only", "Opportunity Lost", "Opportunity Lost ",
    "Onboarding Completed - Converted", "Onboarding Completed - Pending Conversion",
    "Onboarding Failed", "Onboarding On Hold",
    "> 75% sessions done", "51-75% sessions done", "26-50% sessions done",
    "≤ 25% sessions done", "1st Session Scheduled", "Client pending to launch",
    "Churned (Closed)", "Retained (Closed)", "Preventive Churn Risk (New)",
    "Requested Churn (New)", "(DO NOT USE) Churn Confirmed",
    "Product related process (Ongoing)", "Pending approval because low joined rate",
    "Wrongly Created Ticket (Closed)", "SPAM",
    "(DO NOT USE) Pending Post-Mortem Analysis", "(DO NOT USE) Action Plan",
    "Closed - pending finance validation",
]

PROGRESS_FILE = "/tmp/pbd_backfill_progress.json"


def _load_progress() -> dict:
    try:
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"completed": [], "failed": []}


def _save_progress(progress: dict):
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)


def _run_skip_stage_check(deal_uuid: str, hs_deal_id: str):
    """Run pipeline but skip the PBD stage check (for post-PBD deals)."""
    from src.pipelines.pbd_snapshot.run import (
        _fetch_previous_bant, _build_user_prompt, _parse_response,
        _PROMPT, _MODEL,
    )
    from src.integrations.claude import analyze
    from datetime import date

    deal = (
        supabase.table("deals")
        .select("*")
        .eq("id", deal_uuid)
        .limit(1)
        .execute()
    )
    if not deal.data:
        print(f"   Deal {deal_uuid} not found — skipping.")
        return

    d = deal.data[0]
    deal_context = d.get("deal_context") or ""
    if not deal_context.strip():
        print("   No deal_context — skipping.")
        return

    print(f"   {d.get('deal_name')} | stage={d.get('deal_stage')} | context={len(deal_context)} chars")

    prev_bant = _fetch_previous_bant(deal_uuid)

    prev_result = (
        supabase.table("pbd_snapshots")
        .select("*")
        .eq("hs_deal_id", hs_deal_id)
        .order("snapshot_date", desc=True)
        .limit(1)
        .execute()
    )
    prev_snapshot = prev_result.data[0] if prev_result.data else None

    user_prompt = _build_user_prompt(d, deal_context, prev_bant, prev_snapshot)
    print(f"   Calling Claude ({len(user_prompt)} chars) ...")
    response_text = analyze(_PROMPT, user_prompt, model=_MODEL)

    import re
    out = _parse_response(response_text)

    snapshot = {
        "deal_id": deal_uuid,
        "hs_deal_id": hs_deal_id,
        "snapshot_date": date.today().isoformat(),
        "bant_b_status": out.get("bant_b_status"),
        "bant_b_evidence": out.get("bant_b_evidence"),
        "bant_a_status": out.get("bant_a_status"),
        "bant_a_evidence": out.get("bant_a_evidence"),
        "bant_n_status": out.get("bant_n_status"),
        "bant_n_evidence": out.get("bant_n_evidence"),
        "bant_t_status": out.get("bant_t_status"),
        "bant_t_evidence": out.get("bant_t_evidence"),
        "pbd_summary": out.get("pbd_summary"),
    }
    snapshot = {k: v for k, v in snapshot.items() if v is not None}

    print(f"   B={snapshot.get('bant_b_status')} A={snapshot.get('bant_a_status')} "
          f"N={snapshot.get('bant_n_status')} T={snapshot.get('bant_t_status')}")

    supabase.table("pbd_snapshots").upsert(
        snapshot, on_conflict="hs_deal_id,snapshot_date"
    ).execute()

    print(f"   Done.")


def get_targets() -> list[dict]:
    """Get all active deals that need a PBD snapshot."""
    offset = 0
    all_deals = []
    while True:
        r = (
            supabase.table("deals")
            .select("id, deal_id, deal_name, deal_stage")
            .not_.is_("deal_context", "null")
            .neq("deal_context", "")
            .range(offset, offset + 999)
            .execute()
        )
        if not r.data:
            break
        for d in r.data:
            if d["deal_stage"] not in EXCLUDE_STAGES:
                all_deals.append(d)
        if len(r.data) < 1000:
            break
        offset += 1000

    all_deals.sort(key=lambda x: x["deal_name"] or "")
    return all_deals


def run_backfill(limit: int | None = None, dry_run: bool = False):
    print("Fetching targets ...")
    targets = get_targets()
    print(f"  {len(targets)} deals with context (active pipeline)")

    pbd_targets = [t for t in targets if t["deal_stage"] in PBD_STAGES]
    post_pbd_targets = [t for t in targets if t["deal_stage"] not in PBD_STAGES]
    print(f"  {len(pbd_targets)} in PBD stages")
    print(f"  {len(post_pbd_targets)} post-PBD (frozen BANT)")

    progress = _load_progress()
    completed_set = set(progress["completed"])
    targets = [t for t in targets if t["id"] not in completed_set]
    print(f"  {len(targets)} remaining (after excluding completed)")

    if limit:
        targets = targets[:limit]
        print(f"  Limited to {limit}")

    if dry_run:
        print("\n--- DRY RUN ---")
        for t in targets[:30]:
            is_pbd = "PBD" if t["deal_stage"] in PBD_STAGES else "POST"
            print(f"  [{is_pbd}] {t['deal_stage'][:30]:30} \"{t['deal_name']}\"")
        if len(targets) > 30:
            print(f"  ... and {len(targets) - 30} more")
        return

    total = len(targets)
    success = 0
    failed = 0
    start_time = time.time()

    for i, target in enumerate(targets):
        deal_id = target["id"]
        hs_deal_id = target["deal_id"]
        name = target["deal_name"] or "(sin nombre)"
        is_pbd = target["deal_stage"] in PBD_STAGES

        print(f"\n[{i + 1}/{total}] {'PBD' if is_pbd else 'POST'} | {name}")

        try:
            if is_pbd:
                run(deal_id, hs_deal_id)
            else:
                _run_skip_stage_check(deal_id, hs_deal_id)
            success += 1
            progress["completed"].append(deal_id)
        except Exception as e:
            failed += 1
            progress["failed"].append({"id": deal_id, "error": str(e)})
            print(f"  ERROR: {e}")
            traceback.print_exc()

        _save_progress(progress)

        elapsed = time.time() - start_time
        avg = elapsed / (i + 1)
        remaining = avg * (total - i - 1)
        print(f"  Progress: {success} OK, {failed} failed, ~{int(remaining / 60)}min remaining")

        time.sleep(1)

    print(f"\n{'=' * 50}")
    print(f"PBD BACKFILL COMPLETE")
    print(f"  Total: {total}")
    print(f"  Success: {success}")
    print(f"  Failed: {failed}")
    print(f"  Time: {int((time.time() - start_time) / 60)}min")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run_backfill(limit=args.limit, dry_run=args.dry_run)
