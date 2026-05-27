"""
Backfill atlas entries for active pipeline deals.

Regenerates company_card + deal_insights (structured JSONB) and
aggregates sibling companies (same domain) for richer context.

Usage:
    python -m src.pipelines.atlas.backfill [--limit N] [--resume-from ATLAS_ID] [--dry-run] [--workers N]
"""

import argparse
import json
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from src.db.client import supabase
from src.pipelines.atlas.run import generate
from src.pipelines.atlas.hubspot_fetcher import fetch_owners

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

PROGRESS_FILE = "/tmp/atlas_backfill_progress.json"


def _load_progress() -> dict:
    try:
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"completed": [], "failed": [], "last_id": None}


def _save_progress(progress: dict):
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)


def get_backfill_targets() -> list[dict]:
    atlas_ids: set[str] = set()
    offset = 0
    while True:
        r = (
            supabase.table("deals")
            .select("atlas_id, deal_stage")
            .not_.is_("atlas_id", "null")
            .range(offset, offset + 999)
            .execute()
        )
        if not r.data:
            break
        for d in r.data:
            if d["deal_stage"] not in EXCLUDE_STAGES and d.get("atlas_id"):
                atlas_ids.add(d["atlas_id"])
        if len(r.data) < 1000:
            break
        offset += 1000

    targets = []
    id_list = list(atlas_ids)
    for i in range(0, len(id_list), 100):
        batch = id_list[i : i + 100]
        r = (
            supabase.table("atlas")
            .select("id, crm_id, company_name")
            .in_("id", batch)
            .execute()
        )
        targets.extend(r.data or [])

    targets.sort(key=lambda x: x["company_name"] or "")
    return targets


_counter_lock = threading.Lock()


def run_backfill(limit: int | None = None, resume_from: str | None = None, dry_run: bool = False, model: str | None = None, workers: int = 1):
    print("Fetching backfill targets ...")
    targets = get_backfill_targets()
    print(f"  {len(targets)} atlas to backfill")

    progress = _load_progress()
    completed_set = set(progress["completed"])

    if resume_from:
        idx = next((i for i, t in enumerate(targets) if t["id"] == resume_from), 0)
        targets = targets[idx:]
        print(f"  Resuming from index {idx}")

    targets = [t for t in targets if t["id"] not in completed_set]
    print(f"  {len(targets)} remaining (after excluding already completed)")

    if limit:
        targets = targets[:limit]
        print(f"  Limited to {limit}")

    if dry_run:
        print("\n--- DRY RUN ---")
        for t in targets[:20]:
            print(f"  {t['id'][:12]} crm={t['crm_id']} \"{t['company_name']}\"")
        if len(targets) > 20:
            print(f"  ... and {len(targets) - 20} more")
        return

    print("\nFetching owners (shared cache) ...")
    owners = fetch_owners()
    print(f"  {len(owners)} owners cached")

    total = len(targets)
    success = 0
    failed = 0
    start_time = time.time()

    def _process(idx_target):
        nonlocal success, failed
        i, target = idx_target
        atlas_id = target["id"]
        crm_id = target["crm_id"]
        name = target["company_name"] or "(sin nombre)"

        print(f"\n[{i + 1}/{total}] {name} (crm={crm_id})")

        try:
            generate(atlas_id, crm_id, owners=owners, model=model)
            with _counter_lock:
                success += 1
                progress["completed"].append(atlas_id)
                progress["last_id"] = atlas_id
                _save_progress(progress)
                current = success + failed
                if current % 10 == 0:
                    elapsed = time.time() - start_time
                    avg = elapsed / current
                    remaining = avg * (total - current)
                    print(f"\n--- Progress: {success} OK, {failed} failed, ~{int(remaining / 60)}min remaining ---\n")
        except Exception as e:
            with _counter_lock:
                failed += 1
                progress["failed"].append({"id": atlas_id, "crm_id": crm_id, "error": str(e)})
                _save_progress(progress)
            print(f"  ERROR [{name}]: {e}")
            traceback.print_exc()
            time.sleep(5)

    if workers <= 1:
        for item in enumerate(targets):
            _process(item)
            time.sleep(2)
    else:
        print(f"\nUsing {workers} parallel workers")
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(_process, (i, t)): t
                for i, t in enumerate(targets)
            }
            for future in as_completed(futures):
                future.result()

    print(f"\n{'=' * 50}")
    print(f"BACKFILL COMPLETE")
    print(f"  Total: {total}")
    print(f"  Success: {success}")
    print(f"  Failed: {failed}")
    print(f"  Time: {int((time.time() - start_time) / 60)}min")
    print(f"  Progress saved to {PROGRESS_FILE}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill atlas entries")
    parser.add_argument("--limit", type=int, help="Max entries to process")
    parser.add_argument("--resume-from", type=str, help="Atlas ID to resume from")
    parser.add_argument("--dry-run", action="store_true", help="Show targets without processing")
    parser.add_argument("--model", type=str, help="Claude model override (e.g. claude-sonnet-4-6)")
    parser.add_argument("--workers", type=int, default=1, help="Parallel workers (default 1, max 4)")
    args = parser.parse_args()
    run_backfill(limit=args.limit, resume_from=args.resume_from, dry_run=args.dry_run, model=args.model, workers=args.workers)
