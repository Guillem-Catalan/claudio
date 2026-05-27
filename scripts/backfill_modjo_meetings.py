"""
Backfill: fetch missing Modjo calls referenced in deal_context meetings.

Finds Modjo links in deal_context where the call doesn't exist in the calls
table, fetches from Modjo API, normalizes (with HubSpot meeting owner fallback),
inserts into calls, audits with Claude, and appends audit to deal_context.

Usage:
    python -m scripts.backfill_modjo_meetings [--dry-run] [--limit N] [--no-audit]
"""

import argparse
import re
import time

from src.config import PAE_TAGS, PBD_TAGS, get_role, get_subteam
from src.db.client import supabase
from src.integrations import hubspot
from src.pipelines.modjo_calls.api_client import fetch_call_details as modjo_fetch_details
from src.pipelines.modjo_calls.fetch import normalize as modjo_normalize, build_transcript
from src.pipelines.sync_deal_context.run import (
    _fetch_existing_audit,
    _format_meeting,
    _MODJO_RE,
)

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


def _find_missing_modjo_calls():
    """Scan deal_context for Modjo links whose call_id doesn't exist in calls table."""
    print("1. Scanning deal_context for Modjo references ...")
    offset = 0
    batch = 500
    all_refs = []

    while True:
        result = (
            supabase.table("deals")
            .select("id, deal_id, deal_name, deal_context, crm_id")
            .not_.is_("deal_context", "null")
            .range(offset, offset + batch - 1)
            .execute()
        )
        if not result.data:
            break
        for d in result.data:
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-audit", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    missing = _find_missing_modjo_calls()
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

    print(f"\n2. Fetching HubSpot owners ...")
    owners = _fetch_owners()
    print(f"   {len(owners)} owners")

    fetched = 0
    inserted = 0
    audited = 0
    appended = 0
    no_transcript = 0
    modjo_failed = 0
    no_owner = 0

    from src.pipelines.audit.run import run_single

    print(f"\n3. Processing {len(missing)} missing calls ...")

    for i, ref in enumerate(missing, 1):
        modjo_id = ref["modjo_call_id"]
        deal_uuid = ref["deal_uuid"]
        hs_deal_id = ref["hs_deal_id"]
        crm_id = ref.get("crm_id")
        deal_name = (ref["deal_name"] or "?")[:40]

        if i % 20 == 1 or i == len(missing):
            print(
                f"\n   [{i}/{len(missing)}] {deal_name} — modjo={modjo_id}"
                f"  (fetched={fetched} inserted={inserted} audited={audited})"
            )

        try:
            raw_calls = modjo_fetch_details([int(modjo_id)])
        except Exception as e:
            print(f"      Modjo fetch failed: {e}")
            modjo_failed += 1
            time.sleep(1)
            continue

        if not raw_calls:
            modjo_failed += 1
            continue

        fetched += 1
        normalized = modjo_normalize(raw_calls[0])

        if not normalized:
            owner_email, owner_name, meeting_title, _ = _resolve_meeting_owner(
                modjo_id, hs_deal_id, owners,
            )
            if owner_email:
                normalized = _normalize_fallback(
                    raw_calls[0], owner_email, owner_name, meeting_title,
                )
                if normalized:
                    print(f"      fallback OK (owner: {owner_name})")
            else:
                no_owner += 1
                print(f"      no meeting owner found — skipping")
                continue

        if not normalized or not normalized.get("transcript") or len(normalized["transcript"]) < 200:
            no_transcript += 1
            continue

        normalized["deal_id"] = deal_uuid
        normalized["hs_deal_id"] = hs_deal_id
        normalized["crm_id"] = crm_id
        normalized["source"] = "modjo"

        try:
            supabase.table("calls").upsert(
                {k: v for k, v in normalized.items() if not k.startswith("_")},
                on_conflict="call_id",
            ).execute()
            inserted += 1
        except Exception as e:
            print(f"      INSERT failed: {e}")
            continue

        if args.no_audit:
            continue

        try:
            result = run_single(modjo_id)
            if result:
                audited += 1
                audit_text = _fetch_existing_audit(modjo_id, normalized)
                if audit_text:
                    supabase.rpc(
                        "append_deal_context",
                        {"p_deal_id": deal_uuid, "p_text": audit_text},
                    ).execute()
                    appended += 1
        except Exception as e:
            print(f"      AUDIT failed: {e}")

        time.sleep(0.5)

    print(f"\n{'=' * 60}")
    print(f"DONE")
    print(f"  Fetched from Modjo:  {fetched}")
    print(f"  Inserted to calls:   {inserted}")
    print(f"  Audited:             {audited}")
    print(f"  Appended to context: {appended}")
    print(f"  No transcript:       {no_transcript}")
    print(f"  Modjo fetch failed:  {modjo_failed}")
    print(f"  No owner resolved:   {no_owner}")
    print(f"  HubSpot requests:    {hubspot.total_requests()}")


if __name__ == "__main__":
    main()
