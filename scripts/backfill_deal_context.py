"""
Backfill deal_context for all deals that don't have one yet.
Reuses the sync_deal_context pipeline with cached owners to avoid
redundant HubSpot API calls (~15 requests/deal saved).

Usage:
  python -m scripts.backfill_deal_context [--offset N] [--limit N] [--workers N] [--model MODEL]
"""

import argparse
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.db.client import supabase
from src.pipelines.sync_deal_context.run import run, _fetch_owners

_counter_lock = threading.Lock()
_success = 0
_errors = 0


def _process_deal(deal: dict, idx: int, total: int, owners: dict):
    global _success, _errors
    deal_uuid = deal["id"]
    hs_deal_id = deal["deal_id"]
    deal_name = deal.get("deal_name") or "?"

    try:
        run(deal_uuid=deal_uuid, hs_deal_id=hs_deal_id, owners=owners)
        with _counter_lock:
            _success += 1
            current = _success + _errors
            if current % 50 == 0:
                print(f"\n--- Progress: {current}/{total} ({_success} ok, {_errors} errors) ---\n")
    except Exception as e:
        print(f"   [{idx}] ERROR {deal_name}: {e}")
        with _counter_lock:
            _errors += 1
        time.sleep(2)


def main():
    global _success, _errors

    parser = argparse.ArgumentParser()
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--model", type=str, default="")
    args = parser.parse_args()

    if args.model:
        os.environ["AZURE_CLAUDE_DEPLOYMENT"] = args.model
        print(f"0. Model override: {args.model}")

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

    total = len(deals)
    print(f"3. Processing {total} deals with {args.workers} workers ...")

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(_process_deal, deal, i, total, owners): deal
            for i, deal in enumerate(deals, 1)
        }
        for future in as_completed(futures):
            future.result()

    print(f"\n{'='*60}")
    print(f"DONE: {_success} ok, {_errors} errors out of {total}")
    print(f"{'='*60}")

    print("\n4. Unblocking snapshots (resetting front_deal_triggered_at) ...")
    supabase.table("deal_confirmations").update(
        {"front_deal_triggered_at": None}
    ).not_.is_("front_deal_triggered_at", "null").execute()
    print("   Snapshots unblocked")


if __name__ == "__main__":
    main()
