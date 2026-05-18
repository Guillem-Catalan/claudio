"""Backfill close_probability + claudio_forecast for all snapshots missing it.

Rate-limit aware: ~1,500 tokens per call, 100k tokens/min limit → ~66 calls/min.
Uses 4 threads but throttles to stay under the limit.
"""

import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.db.client import supabase
from src.pipelines.front_forecast.run import run

BATCH_SIZE = 500
MAX_WORKERS = 4
CALLS_PER_MINUTE = 60  # conservative vs 66 theoretical


def _fetch_pending(offset: int, limit: int) -> list[str]:
    query = (
        supabase.table("front_deal_snapshots")
        .select("id")
        .is_("close_probability", "null")
        .order("snapshot_date", desc=True)
        .range(offset, offset + limit - 1)
    )
    result = query.execute()
    return [row["id"] for row in (result.data or [])]


def _run_one(snapshot_id: str) -> tuple[str, bool, str]:
    try:
        run(snapshot_id)
        return snapshot_id, True, ""
    except Exception as e:
        return snapshot_id, False, str(e)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=0, help="0 = all")
    args = parser.parse_args()

    print("Fetching pending snapshots ...")
    all_ids: list[str] = []
    offset = args.offset
    while True:
        batch = _fetch_pending(offset, BATCH_SIZE)
        if not batch:
            break
        all_ids.extend(batch)
        offset += BATCH_SIZE
        if args.limit and len(all_ids) >= args.limit:
            all_ids = all_ids[: args.limit]
            break

    total = len(all_ids)
    print(f"{total} snapshots to process (offset={args.offset})")
    if not total:
        return

    done = 0
    errors = 0
    start = time.monotonic()
    min_interval = 60.0 / CALLS_PER_MINUTE

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {}
        submitted = 0

        for sid in all_ids:
            futures[pool.submit(_run_one, sid)] = sid
            submitted += 1

            # Throttle submission to respect rate limit
            if submitted % CALLS_PER_MINUTE == 0:
                elapsed = time.monotonic() - start
                expected = submitted * min_interval
                if elapsed < expected:
                    time.sleep(expected - elapsed)

        for future in as_completed(futures):
            sid, ok, err = future.result()
            done += 1
            if not ok:
                errors += 1
                print(f"  ERROR {sid}: {err}")
            if done % 100 == 0 or done == total:
                elapsed = time.monotonic() - start
                rate = done / (elapsed / 60) if elapsed > 0 else 0
                print(f"  [{done}/{total}] {rate:.0f}/min — {errors} errors")

    elapsed = time.monotonic() - start
    print(f"\nDone: {done - errors}/{total} OK, {errors} errors in {elapsed/60:.1f} min")


if __name__ == "__main__":
    main()
