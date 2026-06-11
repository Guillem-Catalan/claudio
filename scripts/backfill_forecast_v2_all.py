"""Backfill forecast v2 for ALL open deals (excluding onboarding/upsell). Runs in batches."""

import sys
import traceback

from src.db.client import supabase
from src.pipelines.intelligence.forecast_v2 import run as forecast_v2_run

EXCLUDE_STAGES_LOWER = {
    "closed won", "closed lost", "closed won - finance only", "opportunity lost",
    "onboarding completed - converted", "onboarding completed - pending conversion",
    "onboarding failed", "onboarding on hold", "client pending to launch",
    "> 75% sessions done", "51-75% sessions done", "26-50% sessions done",
    "≤ 25% sessions done", "1st session scheduled",
    "churned (closed)", "retained (closed)", "preventive churn risk (new)",
    "requested churn (new)", "(do not use) churn confirmed",
    "spam", "wrongly created ticket (closed)",
    "(do not use) pending post-mortem analysis", "(do not use) action plan",
    "closed - pending finance validation",
}


def backfill(limit: int = 100, offset: int = 0):
    print(f"Backfilling forecast v2 (limit={limit}, offset={offset}) ...")

    # Get deals with latest snapshot that DON'T have v2 yet
    all_deals = (
        supabase.table("deals")
        .select("id, deal_id, deal_name, deal_stage, amount, deal_age_days, pae, pbd, close_date, deal_context, forecast_category, pipeline_name")
        .not_.is_("deal_context", "null")
        .order("amount", desc=True)
        .limit(5000)
        .execute()
    ).data or []

    # Filter: only open, non-onboarding, non-upsell without PAE
    filtered = []
    for d in all_deals:
        stage = (d.get("deal_stage") or "").lower()
        if stage in EXCLUDE_STAGES_LOWER:
            continue
        if "session" in (d.get("deal_name") or "").lower():
            continue
        pipeline = (d.get("pipeline_name") or "").lower()
        has_pae = bool(d.get("pae"))
        if pipeline and pipeline not in ("partners distribution", "sales pipeline", "") and not has_pae:
            continue
        filtered.append(d)

    # Check which already have v2
    deal_ids = [d["id"] for d in filtered]
    already = set()
    for i in range(0, len(deal_ids), 50):
        batch = deal_ids[i:i + 50]
        for val in (True, False):
            resp = (
                supabase.table("front_deal_snapshots")
                .select("deal_id")
                .in_("deal_id", batch)
                .eq("closes_this_month", val)
                .limit(len(batch))
                .execute()
            )
            already |= {r["deal_id"] for r in (resp.data or [])}

    todo = [d for d in filtered if d["id"] not in already]
    todo = todo[offset:offset + limit]

    print(f"  {len(filtered)} open deals total, {len(already)} already have v2, processing {len(todo)}")

    ok = 0
    failed = 0
    for i, d in enumerate(todo, 1):
        deal_uuid = d["id"]
        deal_name = d.get("deal_name", "?")
        print(f"\n  [{i}/{len(todo)}] {deal_name[:55]} ({d.get('deal_stage','?')})")

        snap_resp = (
            supabase.table("front_deal_snapshots")
            .select("*")
            .eq("deal_id", deal_uuid)
            .order("snapshot_date", desc=True)
            .limit(1)
            .execute()
        )
        if not snap_resp.data:
            print(f"    No snapshot — skip")
            continue

        snapshot = snap_resp.data[0]

        try:
            result = forecast_v2_run(deal_uuid, snapshot, d)
            if result:
                update = {}
                for key in ("closes_this_month", "closes_next_month", "forecast_confidence",
                            "forecast_reasoning", "forecast_risks", "forecast_accelerators"):
                    if result.get(key) is not None:
                        update[key] = result[key]
                if result.get("estimated_close_date"):
                    update["claudio_close_date"] = result["estimated_close_date"]

                if update:
                    supabase.table("front_deal_snapshots").update(update).eq("id", snapshot["id"]).execute()

                ctm = "YES" if result.get("closes_this_month") else "NO"
                print(f"    → {ctm} ({result.get('forecast_confidence', '?')})")
                ok += 1
            else:
                print(f"    → no result")
                failed += 1
        except Exception as e:
            print(f"    → FAILED: {e}")
            failed += 1

    print(f"\n  Done: {ok} OK, {failed} failed (batch offset={offset})")


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    offset = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    backfill(limit, offset)
