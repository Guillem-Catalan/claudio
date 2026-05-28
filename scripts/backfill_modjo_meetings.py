"""
Backfill: fetch missing Modjo calls referenced in deal_context meetings.

Finds Modjo links in deal_context where the call doesn't exist in the calls
table, fetches from Modjo API, normalizes (with HubSpot meeting owner fallback),
inserts into calls, audits with Claude, and appends audit to deal_context.

Two-phase approach:
  Phase 1: Batch-fetch from Modjo + normalize + upsert to calls (fast, no Azure)
  Phase 2: Audit in parallel with --workers N (default 3)

By default only processes open deals (excludes lost/won/churned/closed).

Usage:
    python -m scripts.backfill_modjo_meetings [--dry-run] [--limit N] [--no-audit] [--workers 3] [--include-closed]
"""

import argparse
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.config import PAE_TAGS, PBD_TAGS, get_role, get_subteam
from src.db.client import supabase
from src.integrations import hubspot
from src.pipelines.modjo_calls.api_client import fetch_call_details as modjo_fetch_details
from src.pipelines.modjo_calls.fetch import normalize as modjo_normalize, build_transcript
from src.pipelines.sync_deal_context.run import _MODJO_RE

_CLOSED_KEYWORDS = ["closed", "lost", "won", "churned", "spam", "wrongly", "failed",
                     "retained", "do not use", "churn confirmed"]


def _is_closed_stage(stage: str) -> bool:
    if not stage:
        return True
    sl = stage.lower().strip()
    if any(kw in sl for kw in _CLOSED_KEYWORDS):
        return True
    if "onboarding completed" in sl and "converted" in sl:
        return True
    return False


MEETING_PROPS = [
    "hs_timestamp",
    "hs_meeting_title",
    "hs_meeting_body",
    "hs_internal_meeting_notes",
    "hs_meeting_start_time",
    "hs_meeting_end_time",
    "hs_meeting_outcome",
    "hubspot_owner_id",
    "hs_attendee_owner_ids",
]


def _normalize_fallback(raw_call, owner_email, owner_name, meeting_title):
    rels = raw_call.get("relations") or {}
    transcript = build_transcript(rels.get("transcript", []))
    if len(transcript.strip()) < 100:
        return None

    rol = get_role(owner_email) if owner_email else None
    tags_raw = rels.get("tags", [])
    tags = [t["name"] for t in tags_raw]

    if not rol and tags:
        if any(t in PAE_TAGS for t in tags):
            rol = "PAE"
        elif any(t in PBD_TAGS for t in tags):
            rol = "PBD"

    return {
        "call_id": str(raw_call["callId"]),
        "titulo": raw_call.get("title") or meeting_title or "",
        "fecha": raw_call.get("startDate"),
        "duracion_segundos": int(raw_call.get("duration", 0)),
        "owner_email": owner_email,
        "owner_nombre": owner_name,
        "rol": rol,
        "tags": tags,
        "team": "Partners",
        "crm_id": "",
        "hs_deal_id": "",
        "transcript": transcript,
        "subteam": get_subteam(owner_email) if owner_email else None,
    }


def _find_missing_modjo_calls(*, include_closed: bool = False):
    """Scan deal_context for Modjo links whose call_id doesn't exist in calls table."""
    print("1. Scanning deal_context for Modjo references ...")
    offset = 0
    batch = 500
    all_refs = []
    skipped_closed = 0

    while True:
        result = (
            supabase.table("deals")
            .select("id, deal_id, deal_name, deal_context, crm_id, deal_stage")
            .not_.is_("deal_context", "null")
            .range(offset, offset + batch - 1)
            .execute()
        )
        if not result.data:
            break
        for d in result.data:
            if not include_closed and _is_closed_stage(d.get("deal_stage") or ""):
                skipped_closed += 1
                continue
            ctx = d.get("deal_context") or ""
            for m in _MODJO_RE.finditer(ctx):
                all_refs.append({
                    "deal_uuid": d["id"],
                    "hs_deal_id": d["deal_id"],
                    "deal_name": d["deal_name"],
                    "crm_id": d.get("crm_id"),
                    "modjo_call_id": m.group(1),
                })
        offset += batch
        if len(result.data) < batch:
            break

    if skipped_closed:
        print(f"   {skipped_closed} closed deals skipped")
    print(f"   {len(all_refs)} Modjo references found")

    unique_call_ids = list({r["modjo_call_id"] for r in all_refs})
    print(f"   {len(unique_call_ids)} unique call IDs")

    existing = set()
    for i in range(0, len(unique_call_ids), 200):
        b = unique_call_ids[i : i + 200]
        result = supabase.table("calls").select("call_id").in_("call_id", b).execute()
        for r in result.data or []:
            existing.add(r["call_id"])

    print(f"   {len(existing)} already in calls table")

    missing = [r for r in all_refs if r["modjo_call_id"] not in existing]

    seen = set()
    unique_missing = []
    for r in missing:
        if r["modjo_call_id"] not in seen:
            seen.add(r["modjo_call_id"])
            unique_missing.append(r)

    print(f"   {len(unique_missing)} unique missing calls across {len({r['deal_uuid'] for r in missing})} deals")
    return unique_missing


def _fetch_owners():
    owners = {}
    url = "/crm/v3/owners?limit=100"
    while url:
        data = hubspot.get(url)
        for o in data.get("results", []):
            first = o.get("firstName") or ""
            last = o.get("lastName") or ""
            name = f"{first} {last}".strip() or o.get("email", "")
            owners[o["id"]] = {"name": name, "email": o.get("email", "")}
        next_link = data.get("paging", {}).get("next", {}).get("link")
        url = next_link.replace(hubspot.BASE, "") if next_link else ""
    return owners


def _resolve_meeting_owner(modjo_call_id, hs_deal_id, owners):
    """Find the HubSpot meeting that references this Modjo call and get its owner."""
    meeting_ids = []
    after = None
    while True:
        params = {"limit": "500"}
        if after:
            params["after"] = after
        data = hubspot.get(
            f"/crm/v4/objects/deals/{hs_deal_id}/associations/meetings", params
        )
        for item in data.get("results", []):
            oid = str(item.get("toObjectId", ""))
            if oid:
                meeting_ids.append(oid)
        after = data.get("paging", {}).get("next", {}).get("after")
        if not after:
            break

    if not meeting_ids:
        return None, None, None, None

    for i in range(0, len(meeting_ids), 100):
        batch = meeting_ids[i : i + 100]
        data = hubspot.post(
            "/crm/v3/objects/meetings/batch/read",
            {"inputs": [{"id": mid} for mid in batch], "properties": MEETING_PROPS},
        )
        for obj in data.get("results", []):
            p = obj.get("properties", {})
            notes = p.get("hs_internal_meeting_notes") or ""
            m = _MODJO_RE.search(notes)
            if m and m.group(1) == modjo_call_id:
                owner_id = p.get("hubspot_owner_id") or ""
                owner_info = owners.get(owner_id, {})
                email = owner_info.get("email", "") if isinstance(owner_info, dict) else ""
                name = owner_info.get("name", "") if isinstance(owner_info, dict) else ""
                title = p.get("hs_meeting_title") or ""
                hs_meeting_id = str(obj.get("id", ""))
                return email, name, title, hs_meeting_id

    return None, None, None, None


def _audit_one(call_id: str) -> tuple[bool, str]:
    from src.pipelines.audit.run import run_single
    try:
        result = run_single(call_id)
        return (True, call_id) if result else (False, call_id)
    except Exception as e:
        print(f"      AUDIT {call_id} failed: {e}")
        return False, call_id


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-audit", action="store_true")
    parser.add_argument("--include-closed", action="store_true")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    missing = _find_missing_modjo_calls(include_closed=args.include_closed)
    if not missing:
        print("\nNo missing calls found.")
        return

    if args.limit:
        missing = missing[: args.limit]
        print(f"\n   Limited to {args.limit} calls")

    if args.dry_run:
        print(f"\n--- DRY RUN ---")
        for r in missing[:30]:
            dn = (r["deal_name"] or "?")[:50]
            print(f"  {dn:<50} modjo={r['modjo_call_id']}")
        if len(missing) > 30:
            print(f"  ... and {len(missing) - 30} more")
        return

    # ── Phase 1: Fetch from Modjo + normalize + upsert (no Azure) ────────

    print(f"\n2. Fetching HubSpot owners ...")
    owners = _fetch_owners()
    print(f"   {len(owners)} owners")

    print(f"\n3. Phase 1 — Batch fetch from Modjo + insert ({len(missing)} calls) ...")

    all_modjo_ids = [int(r["modjo_call_id"]) for r in missing]
    ref_by_id = {r["modjo_call_id"]: r for r in missing}

    raw_by_id: dict[str, dict] = {}
    for i in range(0, len(all_modjo_ids), 50):
        batch = all_modjo_ids[i : i + 50]
        try:
            raw_calls = modjo_fetch_details(batch)
            for rc in raw_calls:
                raw_by_id[str(rc["callId"])] = rc
            print(f"   Batch {i // 50 + 1}: {len(raw_calls)} fetched")
        except Exception as e:
            print(f"   Batch {i // 50 + 1} FAILED: {e}")

    print(f"   {len(raw_by_id)} calls fetched from Modjo")

    inserted_ids: list[str] = []
    no_transcript = 0
    no_owner = 0
    modjo_failed = len(missing) - len(raw_by_id)

    for modjo_id, raw in raw_by_id.items():
        ref = ref_by_id.get(modjo_id)
        if not ref:
            continue

        normalized = modjo_normalize(raw)

        if not normalized:
            owner_email, owner_name, meeting_title, _ = _resolve_meeting_owner(
                modjo_id, ref["hs_deal_id"], owners,
            )
            if owner_email:
                normalized = _normalize_fallback(raw, owner_email, owner_name, meeting_title)
                if normalized:
                    print(f"      {modjo_id}: fallback OK (owner: {owner_name})")
            else:
                no_owner += 1
                continue

        if not normalized or not normalized.get("transcript") or len(normalized["transcript"]) < 200:
            no_transcript += 1
            continue

        normalized["deal_id"] = ref["deal_uuid"]
        normalized["hs_deal_id"] = ref["hs_deal_id"]
        normalized["crm_id"] = ref.get("crm_id")
        normalized["source"] = "modjo"

        try:
            supabase.table("calls").upsert(
                {k: v for k, v in normalized.items() if not k.startswith("_")},
                on_conflict="call_id",
            ).execute()
            inserted_ids.append(modjo_id)
        except Exception as e:
            print(f"      {modjo_id} INSERT failed: {e}")

    print(f"\n   Phase 1 done:")
    print(f"     Inserted:       {len(inserted_ids)}")
    print(f"     No transcript:  {no_transcript}")
    print(f"     Modjo failed:   {modjo_failed}")
    print(f"     No owner:       {no_owner}")

    if args.no_audit or not inserted_ids:
        print(f"\n{'=' * 60}")
        print(f"DONE (phase 1 only)")
        print(f"  HubSpot requests: {hubspot.total_requests()}")
        return

    # ── Phase 2: Parallel audits ─────────────────────────────────────────

    print(f"\n4. Phase 2 — Auditing {len(inserted_ids)} calls ({args.workers} workers) ...")

    audited = 0
    failed = 0

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(_audit_one, cid): cid for cid in inserted_ids}
        for i, future in enumerate(as_completed(futures), 1):
            ok, cid = future.result()
            if ok:
                audited += 1
            else:
                failed += 1
            if i % 20 == 0 or i == len(inserted_ids):
                print(f"   [{i}/{len(inserted_ids)}] audited={audited} failed={failed}")

    print(f"\n{'=' * 60}")
    print(f"DONE")
    print(f"  Fetched from Modjo:  {len(raw_by_id)}")
    print(f"  Inserted to calls:   {len(inserted_ids)}")
    print(f"  Audited:             {audited}")
    print(f"  Audit failed:        {failed}")
    print(f"  No transcript:       {no_transcript}")
    print(f"  Modjo fetch failed:  {modjo_failed}")
    print(f"  No owner resolved:   {no_owner}")
    print(f"  HubSpot requests:    {hubspot.total_requests()}")


if __name__ == "__main__":
    main()
