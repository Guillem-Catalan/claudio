"""Temporary backfill: sync all HubSpot emails for deals that have them."""

import time
from src.db.client import supabase
from src.pipelines.sync_emails.fetch import run

BATCH = 500


def _pending_deals() -> list[dict]:
    print("  Loading all deals with emails ...")
    deals = []
    offset = 0
    while True:
        result = (
            supabase.table("deals")
            .select("id, deal_id, numero_de_emails")
            .gt("numero_de_emails", 0)
            .order("deal_id")
            .range(offset, offset + BATCH - 1)
            .execute()
        )
        rows = result.data or []
        deals.extend(rows)
        if len(rows) < BATCH:
            break
        offset += BATCH

    print(f"  {len(deals)} deals with emails in total")

    print("  Counting emails already loaded per deal ...")
    loaded: dict[str, int] = {}
    offset = 0
    while True:
        result = (
            supabase.table("emails")
            .select("hs_deal_id")
            .range(offset, offset + 9999)
            .execute()
        )
        rows = result.data or []
        if not rows:
            break
        for r in rows:
            did = r["hs_deal_id"]
            loaded[did] = loaded.get(did, 0) + 1
        if len(rows) < 10000:
            break
        offset += 10000

    pending = [d for d in deals if loaded.get(d["deal_id"], 0) < d["numero_de_emails"]]
    print(f"  {len(deals) - len(pending)} already complete, {len(pending)} still pending")
    return pending


def main():
    deals = _pending_deals()
    if not deals:
        print("Nothing to do.")
        return

    print(f"\nProcessing {len(deals)} deals ...\n")
    ok = 0
    errors = 0
    for i, deal in enumerate(deals, 1):
        try:
            print(f"[{i}/{len(deals)}] deal {deal['deal_id']} ({deal['numero_de_emails']} emails)")
            run(deal_uuid=deal["id"], hs_deal_id=deal["deal_id"])
            ok += 1
        except Exception as e:
            print(f"   ERROR: {e}")
            errors += 1
            time.sleep(1)

    print(f"\nDone: {ok} ok, {errors} errors")


if __name__ == "__main__":
    main()
