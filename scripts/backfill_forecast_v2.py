"""Backfill forecast v2 for active deals with existing snapshots. Priority: Commit/Upside first."""

import sys
import traceback

from src.db.client import supabase
from src.pipelines.intelligence.forecast_v2 import run as forecast_v2_run


def backfill(limit: int = 100):
    print(f"Backfilling forecast v2 (limit {limit}) ...")

    # Priority 1: Commit + Upside deals
    resp1 = (
        supabase.table("deals")
        .select("id, deal_id, deal_name, deal_stage, amount, deal_age_days, pae, pbd, close_date, deal_context, forecast_category")
        .in_("forecast_category", ["Commit", "Upside"])
        .not_.is_("deal_context", "null")
        .order("amount", desc=True)
        .limit(limit)
        .execute()
    )

    # Priority 2: Pipeline_new with meetings soon
    resp2 = (
        supabase.table("deals")
        .select("id, deal_id, deal_name, deal_stage, amount, deal_age_days, pae, pbd, close_date, deal_context, forecast_category")
        .eq("forecast_category", "Pipeline_new")
        .not_.is_("deal_context", "null")
        .order("amount", desc=True)
        .limit(max(0, limit - len(resp1.data or [])))
        .execute()
    )

    deals = (resp1.data or []) + (resp2.data or [])

    # Filter out deals that already have forecast v2
    deal_ids = [d["id"] for d in deals]
    already = set()
    for i in range(0, len(deal_ids), 30):
        batch = deal_ids[i:i + 30]
        resp = (
            supabase.table("front_deal_snapshots")
            .select("deal_id")
            .in_("deal_id", batch)
            .eq("closes_this_month", True)
            .limit(len(batch))
            .execute()
        )
        already |= {r["deal_id"] for r in (resp.data or [])}
        resp2 = (
            supabase.table("front_deal_snapshots")
            .select("deal_id")
            .in_("deal_id", batch)
            .eq("closes_this_month", False)
            .limit(len(batch))
            .execute()
        )
        already |= {r["deal_id"] for r in (resp2.data or [])}

    deals = [d for d in deals if d["id"] not in already]
    print(f"  {len(deals)} deals to process ({len(already)} already have v2)")

    ok = 0
    failed = 0
    for i, d in enumerate(deals, 1):
        deal_uuid = d["id"]
        deal_name = d.get("deal_name", "?")
        print(f"\n  [{i}/{len(deals)}] {deal_name[:50]} ({d.get('forecast_category','?')})")

        # Get latest snapshot
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
                if result.get("closes_this_month") is not None:
                    update["closes_this_month"] = result["closes_this_month"]
                if result.get("closes_next_month") is not None:
                    update["closes_next_month"] = result["closes_next_month"]
                if result.get("forecast_confidence"):
                    update["forecast_confidence"] = result["forecast_confidence"]
                if result.get("forecast_reasoning"):
                    update["forecast_reasoning"] = result["forecast_reasoning"]
                if result.get("forecast_risks"):
                    update["forecast_risks"] = result["forecast_risks"]
                if result.get("forecast_accelerators"):
                    update["forecast_accelerators"] = result["forecast_accelerators"]
                if result.get("estimated_close_date"):
                    update["claudio_close_date"] = result["estimated_close_date"]

                if update:
                    supabase.table("front_deal_snapshots").update(update).eq("id", snapshot["id"]).execute()

                ctm = "YES" if result.get("closes_this_month") else "NO"
                conf = result.get("forecast_confidence", "?")
                print(f"    → closes_this_month={ctm} ({conf})")
                ok += 1
            else:
                print(f"    → no result")
                failed += 1
        except Exception as e:
            print(f"    → FAILED: {e}")
            traceback.print_exc()
            failed += 1

    print(f"\n  Done: {ok} OK, {failed} failed")


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    backfill(limit)
