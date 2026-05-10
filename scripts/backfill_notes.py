"""Temporary backfill: sync all notes for deals that have them."""

import time
from src.db.client import supabase
from src.pipelines.sync_notes.fetch import run

BATCH = 500


def main():
    print("Fetching deals with notes ...")
    deal_ids = []
    offset = 0
    while True:
        result = (
            supabase.table("deals")
            .select("id, deal_id, numero_de_notas")
            .gt("numero_de_notas", 0)
            .order("deal_id")
            .range(offset, offset + BATCH - 1)
            .execute()
        )
        rows = result.data or []
        deal_ids.extend(rows)
        if len(rows) < BATCH:
            break
        offset += BATCH

    print(f"{len(deal_ids)} deals to process\n")

    ok = 0
    errors = 0
    for i, deal in enumerate(deal_ids, 1):
        try:
            print(f"[{i}/{len(deal_ids)}] deal {deal['deal_id']} ({deal['numero_de_notas']} notes)")
            run(deal_uuid=deal["id"], hs_deal_id=deal["deal_id"])
            ok += 1
        except Exception as e:
            print(f"   ERROR: {e}")
            errors += 1
            time.sleep(1)

    print(f"\nDone: {ok} ok, {errors} errors")


if __name__ == "__main__":
    main()
