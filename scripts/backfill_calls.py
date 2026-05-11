"""Temporary backfill: sync calls for deals that have fewer calls loaded than expected."""

import time
from src.db.client import supabase
from src.pipelines.sync_calls.fetch import run

BATCH = 500


def _pending_deals() -> list[dict]:
    """Find deals where actual call count < expected, using RPC."""
    print("  Finding deals with call gaps ...")

    all_deals = []
    offset = 0
    while True:
        result = (
            supabase.table("deals")
            .select("id, deal_id, numero_de_calls")
            .gt("numero_de_calls", 0)
            .order("deal_id")
            .range(offset, offset + BATCH - 1)
            .execute()
        )
        rows = result.data or []
        all_deals.extend(rows)
        if len(rows) < BATCH:
            break
        offset += BATCH

    print(f"  {len(all_deals)} deals with calls expected")

    deal_ids = [d["id"] for d in all_deals]
    actual_counts: dict[str, int] = {}
    for i in range(0, len(deal_ids), BATCH):
        batch = deal_ids[i : i + BATCH]
        result = (
            supabase.rpc("count_calls_per_deal", {"deal_ids": batch}).execute()
        )
        for r in (result.data or []):
            actual_counts[r["deal_id"]] = r["cnt"]

    pending = [
        d for d in all_deals
        if actual_counts.get(d["id"], 0) < d["numero_de_calls"]
    ]

    print(f"  {len(all_deals) - len(pending)} complete, {len(pending)} with gaps")
    return pending


def _pending_deals_simple() -> list[dict]:
    """Fallback: load deals and count calls separately."""
    print("  Loading deals with calls ...")
    all_deals = []
    offset = 0
    while True:
        result = (
            supabase.table("deals")
            .select("id, deal_id, numero_de_calls")
            .gt("numero_de_calls", 0)
            .order("deal_id")
            .range(offset, offset + BATCH - 1)
            .execute()
        )
        rows = result.data or []
        all_deals.extend(rows)
        if len(rows) < BATCH:
            break
        offset += BATCH

    print(f"  {len(all_deals)} deals with calls expected")
    print("  Counting loaded calls per deal ...")

    loaded: dict[str, int] = {}
    offset = 0
    while True:
        result = (
            supabase.table("calls")
            .select("deal_id")
            .not_.is_("deal_id", "null")
            .range(offset, offset + 9999)
            .execute()
        )
        rows = result.data or []
        if not rows:
            break
        for r in rows:
            did = r["deal_id"]
            loaded[did] = loaded.get(did, 0) + 1
        if len(rows) < 10000:
            break
        offset += 10000

    pending = [
        d for d in all_deals
        if loaded.get(d["id"], 0) < d["numero_de_calls"]
    ]

    print(f"  {len(all_deals) - len(pending)} complete, {len(pending)} with gaps")
    return pending


def main():
    try:
        deals = _pending_deals()
    except Exception:
        print("  RPC not available, using fallback method ...")
        deals = _pending_deals_simple()

    if not deals:
        print("Nothing to do.")
        return

    print(f"\nProcessing {len(deals)} deals ...\n")
    ok = 0
    errors = 0
    for i, deal in enumerate(deals, 1):
        try:
            print(f"[{i}/{len(deals)}] deal {deal['deal_id']} ({deal['numero_de_calls']} calls)")
            run(deal_uuid=deal["id"], hs_deal_id=deal["deal_id"])
            ok += 1
        except Exception as e:
            print(f"   ERROR: {e}")
            errors += 1
            time.sleep(1)

    print(f"\nDone: {ok} ok, {errors} errors")


if __name__ == "__main__":
    main()
