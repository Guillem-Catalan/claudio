"""
One-shot backfill: load all HubSpot meetings into deal_meetings table.

Usage:
    python -m src.pipelines.sync_deals.backfill_meetings [--limit N] [--dry-run]
"""

import argparse
import time

from src.db.client import supabase
from src.pipelines.sync_deals.properties import fetch_meeting_details
from src.pipelines.sync_deals.search import find_all_deal_ids


def run(limit: int | None = None, dry_run: bool = False):
    print("1. Finding all deal IDs ...")
    deal_ids = sorted(find_all_deal_ids())
    print(f"   {len(deal_ids)} deals")

    print("\n2. Fetching meeting details from HubSpot ...")
    meeting_details = fetch_meeting_details(deal_ids)
    total = sum(len(v) for v in meeting_details.values())
    print(f"   {total} meetings across {len(meeting_details)} deals")

    if not meeting_details:
        print("   No meetings found.")
        return

    print("\n3. Resolving deal UUIDs ...")
    hs_deal_ids = list(meeting_details.keys())
    deal_uuid_map: dict[str, str] = {}
    for i in range(0, len(hs_deal_ids), 200):
        batch = hs_deal_ids[i : i + 200]
        existing = (
            supabase.table("deals")
            .select("id, deal_id")
            .in_("deal_id", batch)
            .execute()
        )
        for r in existing.data or []:
            deal_uuid_map[r["deal_id"]] = r["id"]
    print(f"   {len(deal_uuid_map)} deals matched")

    print("\n4. Building meeting rows ...")
    meeting_rows: list[dict] = []
    for hs_did, meetings in meeting_details.items():
        deal_uuid = deal_uuid_map.get(hs_did)
        for m in meetings:
            if not m.get("hs_meeting_id"):
                continue
            row = {
                "hs_deal_id": hs_did,
                "hs_meeting_id": m["hs_meeting_id"],
                "meeting_start": m.get("meeting_start"),
                "meeting_end": m.get("meeting_end"),
                "title": (m.get("title") or "")[:500],
                "outcome": m.get("outcome") or "SCHEDULED",
            }
            if deal_uuid:
                row["deal_id"] = deal_uuid
            meeting_rows.append(row)

    if limit:
        meeting_rows = meeting_rows[:limit]

    print(f"   {len(meeting_rows)} rows to upsert")

    if dry_run:
        print("\n--- DRY RUN ---")
        for r in meeting_rows[:20]:
            print(f"  {r['hs_deal_id']} | {r['hs_meeting_id']} | {r.get('meeting_start','?')[:16]} | {r.get('outcome','?')}")
        if len(meeting_rows) > 20:
            print(f"  ... and {len(meeting_rows) - 20} more")
        return

    print("\n5. Upserting to Supabase ...")
    written = 0
    failed = 0
    batch_size = 100
    total_batches = (len(meeting_rows) + batch_size - 1) // batch_size

    for i in range(0, len(meeting_rows), batch_size):
        batch_num = i // batch_size + 1
        batch = meeting_rows[i : i + batch_size]
        try:
            result = (
                supabase.table("deal_meetings")
                .upsert(batch, on_conflict="hs_meeting_id")
                .execute()
            )
            written += len(result.data or [])
        except Exception as e:
            failed += len(batch)
            print(f"   batch {batch_num}/{total_batches} failed: {e}")

        if batch_num % 10 == 0:
            print(f"   {batch_num}/{total_batches} batches | {written} OK, {failed} failed")
        time.sleep(0.1)

    print(f"\n   Done: {written} meetings upserted, {failed} failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(limit=args.limit, dry_run=args.dry_run)
