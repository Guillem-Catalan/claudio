"""
Backfill deal_context for all deals that don't have one yet.
Reuses the sync_deal_context pipeline with cached owners to avoid
redundant HubSpot API calls (~15 requests/deal saved).

Usage:
  python -m scripts.backfill_deal_context [--offset N] [--limit N]
"""

import argparse
import time

from src.db.client import supabase
from src.pipelines.sync_deal_context.run import run, _fetch_owners


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    print("1. Fetching owners (once) ...")
    owners = _fetch_owners()
    print(f"   {len(owners)} owners cached")

    print("2. Loading deals without deal_context ...")
    page = 0
    page_size = 1000
    deals = []
    while True:
        result = (
            supabase.table("deals")
            .select("id, deal_id, deal_name")
            .or_("deal_context.is.null,deal_context.eq.")
            .order("deal_id")
            .range(page, page + page_size - 1)
            .execute()
        )
        deals.extend(result.data or [])
        if len(result.data or []) < page_size:
            break
        page += page_size

    print(f"   {len(deals)} deals total without context")

    if args.offset:
        deals = deals[args.offset:]
        print(f"   Skipping first {args.offset} → {len(deals)} remaining")

    if args.limit:
        deals = deals[: args.limit]
        print(f"   Limited to {len(deals)} deals")

    success = 0
    errors = 0

    for i, deal in enumerate(deals, 1):
        deal_uuid = deal["id"]
        hs_deal_id = deal["deal_id"]
        deal_name = deal.get("deal_name") or "?"
        global_idx = i + args.offset

        print(f"\n{'='*60}")
        print(f"[{global_idx}] {deal_name} ({hs_deal_id})")
        print(f"{'='*60}")

        try:
            run(deal_uuid=deal_uuid, hs_deal_id=hs_deal_id, owners=owners)
            success += 1
        except Exception as e:
            print(f"   ERROR: {e}")
            errors += 1
            time.sleep(2)
            continue

        if i % 100 == 0:
            print(f"\n--- Progress: {i}/{len(deals)} done ({success} ok, {errors} errors) ---\n")

    print(f"\n{'='*60}")
    print(f"DONE: {success} ok, {errors} errors out of {len(deals)}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
