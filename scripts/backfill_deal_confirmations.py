"""Temporary backfill: create deal_confirmations rows for all existing deals."""

from src.db.client import supabase

BATCH = 500


def _all_deals() -> list[dict]:
    deals = []
    offset = 0
    while True:
        result = (
            supabase.table("deals")
            .select("id, deal_id")
            .order("deal_id")
            .range(offset, offset + BATCH - 1)
            .execute()
        )
        rows = result.data or []
        deals.extend(rows)
        if len(rows) < BATCH:
            break
        offset += BATCH
    return deals


def _existing_deal_ids() -> set[str]:
    ids = set()
    offset = 0
    while True:
        result = (
            supabase.table("deal_confirmations")
            .select("deal_id")
            .range(offset, offset + BATCH - 1)
            .execute()
        )
        rows = result.data or []
        ids.update(str(r["deal_id"]) for r in rows)
        if len(rows) < BATCH:
            break
        offset += BATCH
    return ids


def main():
    print("1. Loading all deals ...")
    deals = _all_deals()
    print(f"   {len(deals)} deals in total")

    print("2. Checking existing deal_confirmations ...")
    existing = _existing_deal_ids()
    pending = [d for d in deals if d["id"] not in existing]
    print(f"   {len(existing)} already exist, {len(pending)} to create")

    if not pending:
        print("Nothing to do.")
        return

    print(f"3. Inserting {len(pending)} rows ...")
    inserted = 0
    for i in range(0, len(pending), BATCH):
        batch = pending[i : i + BATCH]
        rows = [
            {
                "deal_id": d["id"],
                "hs_deal_id": d["deal_id"],
                "calls_ready": True,
                "emails_ready": True,
                "notes_ready": True,
                "atlas_ready": False,
            }
            for d in batch
        ]
        result = (
            supabase.table("deal_confirmations")
            .upsert(rows, on_conflict="deal_id")
            .execute()
        )
        inserted += len(result.data or [])
        print(f"   [{i + len(batch)}/{len(pending)}] {inserted} inserted")

    print(f"\nDone: {inserted} deal_confirmations created")


if __name__ == "__main__":
    main()
