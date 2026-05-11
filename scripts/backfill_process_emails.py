"""Temporary backfill: process all emails with Claude (summary, type, key_people)."""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from src.db.client import supabase
from src.pipelines.process_email.run import run

BATCH = 500
WORKERS = 8


def _pending_email_ids() -> list[str]:
    print("  Loading emails without summary ...")
    ids = []
    offset = 0
    while True:
        result = (
            supabase.table("emails")
            .select("id")
            .is_("email_summary", "null")
            .order("id")
            .range(offset, offset + BATCH - 1)
            .execute()
        )
        rows = result.data or []
        ids.extend(r["id"] for r in rows)
        if len(rows) < BATCH:
            break
        offset += BATCH

    return ids


def _process_one(idx_and_id: tuple[int, str, int]) -> tuple[bool, str]:
    i, email_id, total = idx_and_id
    try:
        if i % 100 == 0:
            print(f"[{i}/{total}] processing {email_id}")
        run(email_id)
        return True, email_id
    except Exception as e:
        print(f"  ERROR on {email_id}: {e}")
        return False, email_id


def main():
    ids = _pending_email_ids()
    print(f"  {len(ids)} emails to process\n")

    if not ids:
        print("Nothing to do.")
        return

    ok = 0
    errors = 0
    tasks = [(i, eid, len(ids)) for i, eid in enumerate(ids, 1)]

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(_process_one, t): t for t in tasks}
        for future in as_completed(futures):
            success, _ = future.result()
            if success:
                ok += 1
            else:
                errors += 1

    print(f"\nDone: {ok} ok, {errors} errors")


if __name__ == "__main__":
    main()
