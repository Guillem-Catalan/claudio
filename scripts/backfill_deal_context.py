"""
Temporary: build deal_context for all deals that don't have one yet.
Fetches emails, notes, and calls from HubSpot, sorts chronologically,
and writes formatted context.
"""

import time

from src.db.client import supabase
from src.pipelines.sync_deal_context.run import run


def main():
    print("Loading deals without deal_context ...")

    offset = 0
    batch_size = 1000
    deals = []
    while True:
        result = (
            supabase.table("deals")
            .select("id, deal_id, deal_name")
            .or_("deal_context.is.null,deal_context.eq.")
            .order("deal_id")
            .range(offset, offset + batch_size - 1)
            .execute()
        )
        deals.extend(result.data or [])
        if len(result.data or []) < batch_size:
            break
        offset += batch_size

    print(f"Found {len(deals)} deals to process")

    for i, deal in enumerate(deals, 1):
        deal_uuid = deal["id"]
        hs_deal_id = deal["deal_id"]
        deal_name = deal.get("deal_name") or "?"

        print(f"\n[{i}/{len(deals)}] {deal_name} ({hs_deal_id})")
        try:
            run(deal_uuid=deal_uuid, hs_deal_id=hs_deal_id)
        except Exception as e:
            print(f"   ERROR: {e}")
            time.sleep(2)
            continue


if __name__ == "__main__":
    main()
