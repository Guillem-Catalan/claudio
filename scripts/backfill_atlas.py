"""Temporary backfill: create atlas stubs + generate context for all companies."""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.db.client import supabase
from src.pipelines.atlas.run import generate

BATCH = 500
WORKERS = 2
MAX_RETRIES = 2


def _ensure_stubs() -> int:
    """Create atlas stubs for all companies that don't have one yet."""
    print("  Finding deals without atlas_id ...")
    offset = 0
    crm_ids: set[str] = set()
    while True:
        result = (
            supabase.table("deals")
            .select("crm_id")
            .is_("atlas_id", "null")
            .not_.is_("crm_id", "null")
            .range(offset, offset + BATCH - 1)
            .execute()
        )
        rows = result.data or []
        crm_ids.update(r["crm_id"] for r in rows)
        if len(rows) < BATCH:
            break
        offset += BATCH

    if not crm_ids:
        print("  All deals already linked to atlas.")
        return 0

    print(f"  {len(crm_ids)} companies need stubs ...")
    created = 0
    crm_list = sorted(crm_ids)
    for i in range(0, len(crm_list), BATCH):
        batch = crm_list[i : i + BATCH]
        rows = [{"crm_id": cid} for cid in batch]
        supabase.table("atlas").upsert(rows, on_conflict="crm_id").execute()
        created += len(batch)
        print(f"  [{created}/{len(crm_list)}] stubs created")

    print("  Linking deals to atlas ...")
    offset = 0
    linked = 0
    while True:
        result = (
            supabase.table("deals")
            .select("id, crm_id")
            .is_("atlas_id", "null")
            .not_.is_("crm_id", "null")
            .range(offset, offset + BATCH - 1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            break
        for row in rows:
            atlas_result = (
                supabase.table("atlas")
                .select("id")
                .eq("crm_id", row["crm_id"])
                .maybe_single()
                .execute()
            )
            if atlas_result.data:
                supabase.table("deals").update(
                    {"atlas_id": atlas_result.data["id"]}
                ).eq("id", row["id"]).execute()
                linked += 1
        if linked % 500 == 0:
            print(f"  {linked} deals linked ...")
        if len(rows) < BATCH:
            break
        offset += BATCH
    print(f"  {linked} deals linked total")

    return created


def _pending_atlas_ids() -> list[dict]:
    print("  Loading atlas rows without context ...")
    rows = []
    offset = 0
    while True:
        result = (
            supabase.table("atlas")
            .select("id, crm_id")
            .is_("last_generated", "null")
            .order("crm_id")
            .range(offset, offset + BATCH - 1)
            .execute()
        )
        batch = result.data or []
        rows.extend(batch)
        if len(batch) < BATCH:
            break
        offset += BATCH
    return rows


def _process_one(idx_and_row: tuple[int, dict, int]) -> tuple[bool, str]:
    i, row, total = idx_and_row
    if i % 50 == 0:
        print(f"[{i}/{total}] generating atlas for {row['crm_id']}")
    for attempt in range(MAX_RETRIES + 1):
        try:
            generate(atlas_id=row["id"], crm_id=row["crm_id"])
            return True, row["crm_id"]
        except Exception as e:
            if attempt < MAX_RETRIES:
                wait = 5 * (2 ** attempt)
                print(f"  RETRY {attempt + 1}/{MAX_RETRIES} on {row['crm_id']}: {e} — waiting {wait}s")
                time.sleep(wait)
            else:
                print(f"  ERROR on {row['crm_id']}: {e}")
                return False, row["crm_id"]


def main():
    print("1. Ensuring atlas stubs exist ...")
    created = _ensure_stubs()
    print(f"   {created} new stubs\n")

    print("2. Loading pending atlas rows ...")
    pending = _pending_atlas_ids()
    print(f"   {len(pending)} to generate\n")

    if not pending:
        print("Nothing to do.")
        return

    ok = 0
    errors = 0
    tasks = [(i, row, len(pending)) for i, row in enumerate(pending, 1)]

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
