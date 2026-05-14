"""
Temporary backfill: generate front_deal_snapshots for open non-onboarding deals.

Only processes deals that have deal_context and no snapshot for today.
4 parallel workers.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

from src.db.client import supabase
from src.pipelines.front_deals.run import run

WORKERS = 4
TODAY = date.today().isoformat()

_lock = threading.Lock()
_ok = 0
_errors = 0


def _inc_ok():
    global _ok
    with _lock:
        _ok += 1
        return _ok


def _inc_error():
    global _errors
    with _lock:
        _errors += 1
        return _errors


def _process(idx: int, total: int, deal: dict) -> bool:
    deal_name = deal.get("deal_name") or "?"
    try:
        print(f"[{idx}/{total}] {deal_name}", flush=True)
        run(deal_uuid=deal["id"], hs_deal_id=deal["deal_id"])
        _inc_ok()
        return True
    except Exception as e:
        print(f"   [{deal_name}] ERROR: {e}", flush=True)
        _inc_error()
        time.sleep(2)
        return False


def main():
    print(f"=== BACKFILL FRONT DEAL SNAPSHOTS ({WORKERS} workers) ===\n")

    # Load deals: open, not onboarding, with deal_context, no snapshot today
    print("1. Loading deals ...")

    offset = 0
    candidates: list[dict] = []
    while True:
        result = (
            supabase.table("deals")
            .select("id, deal_id, deal_name, deal_stage")
            .not_.is_("deal_context", "null")
            .neq("deal_context", "")
            .order("deal_id")
            .range(offset, offset + 999)
            .execute()
        )
        rows = result.data or []
        for d in rows:
            stage = (d.get("deal_stage") or "").lower()
            name = (d.get("deal_name") or "").lower()
            if any(s in stage for s in ("closed", "lost", "won", "nurturing")):
                continue
            if "session" in name:
                continue
            candidates.append(d)
        if len(rows) < 1000:
            break
        offset += 1000

    print(f"   {len(candidates)} open deals with context")

    # Exclude deals that already have a snapshot for today
    print("2. Checking existing snapshots for today ...")
    existing: set[str] = set()
    offset = 0
    while True:
        result = (
            supabase.table("front_deal_snapshots")
            .select("hs_deal_id")
            .eq("snapshot_date", TODAY)
            .range(offset, offset + 999)
            .execute()
        )
        rows = result.data or []
        for r in rows:
            existing.add(r["hs_deal_id"])
        if len(rows) < 1000:
            break
        offset += 1000

    deals = [d for d in candidates if d["deal_id"] not in existing]
    print(f"   {len(existing)} already have today's snapshot, {len(deals)} to process\n")

    if not deals:
        print("Nothing to do.")
        return

    # Process in parallel
    start = time.monotonic()

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = []
        for i, deal in enumerate(deals, 1):
            futures.append(pool.submit(_process, i, len(deals), deal))
        for f in as_completed(futures):
            try:
                f.result()
            except Exception as e:
                print(f"   Worker error: {e}", flush=True)

    elapsed = time.monotonic() - start
    print(f"\n{'=' * 60}")
    print(f"Done in {elapsed / 60:.1f} min")
    print(f"Snapshots created: {_ok}")
    print(f"Errors: {_errors}")


if __name__ == "__main__":
    main()
