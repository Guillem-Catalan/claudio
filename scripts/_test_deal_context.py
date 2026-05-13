"""Temporary: build deal_context for GRUPO CAPISA to verify chronological output."""

from src.db.client import supabase
from src.integrations import hubspot
from src.pipelines.audit.run import run_single
from src.pipelines.sync_deal_context.run import (
    EMAIL_PROPS,
    NOTE_PROPS,
    _build_atlas_header,
    _fetch_associations,
    _batch_read,
    _fetch_owners,
    _format_email,
    _format_note,
    _format_call_context,
    _flush_context,
    _parse_date,
    _format_date,
)

DEAL_UUID = "05a08c88-c00c-46cb-bb00-36e4b98256a5"
HS_DEAL_ID = "33058046267"


def _is_audited(call: dict) -> bool:
    role = call.get("rol")
    if not role:
        return False
    table = "pbd_audits" if role == "PBD" else "pae_audits"
    r = (
        supabase.table(table)
        .select("win_rate_score")
        .eq("call_ref", call["id"])
        .maybe_single()
        .execute()
    )
    return bool(r.data and r.data.get("win_rate_score") is not None)


def main():
    print(f"=== TEST DEAL CONTEXT: GRUPO CAPISA ===\n")

    # 1. Atlas header
    print("1. Building atlas header ...")
    atlas_header = _build_atlas_header(DEAL_UUID)
    if atlas_header:
        supabase.rpc(
            "append_deal_context",
            {"p_deal_id": DEAL_UUID, "p_text": atlas_header},
        ).execute()
        print(f"   Written: {len(atlas_header)} chars")
    else:
        print("   No atlas found")

    # 2. Fetch owners
    print("2. Fetching owners ...")
    owners = _fetch_owners()

    # 3. Collect all items: (date_sort, type, payload)
    items: list[tuple[str, str, str | dict]] = []

    # 3a. Emails from HubSpot
    print("3. Fetching emails ...")
    email_ids = _fetch_associations(HS_DEAL_ID, "emails")
    if email_ids:
        email_objects = _batch_read("emails", email_ids, EMAIL_PROPS)
        for obj in email_objects:
            p = obj.get("properties", {})
            hs_id = str(obj.get("id", ""))
            date = p.get("hs_timestamp") or p.get("hs_createdate") or ""
            items.append((date, "context", _format_email(hs_id, p)))
        print(f"   {len(email_ids)} emails")
    else:
        print("   No emails")

    # 3b. Notes from HubSpot
    print("4. Fetching notes ...")
    note_ids = _fetch_associations(HS_DEAL_ID, "notes")
    if note_ids:
        note_objects = _batch_read("notes", note_ids, NOTE_PROPS)
        for obj in note_objects:
            p = obj.get("properties", {})
            hs_id = str(obj.get("id", ""))
            date = p.get("hs_timestamp") or p.get("hs_createdate") or ""
            body = p.get("hs_note_body") or ""
            if not body.strip():
                items.append((
                    date,
                    "context",
                    f"[{_format_date(date)}] NOTE [hs:{hs_id}] — (sin contenido)",
                ))
            else:
                items.append((date, "context", _format_note(hs_id, p, owners)))
        print(f"   {len(note_ids)} notes")
    else:
        print("   No notes")

    # 3c. Existing calls from Supabase (NOT HubSpot)
    print("5. Loading existing calls from table ...")
    calls_result = (
        supabase.table("calls")
        .select("*")
        .eq("deal_id", DEAL_UUID)
        .execute()
    )
    calls = calls_result.data or []
    auditable_count = 0
    context_count = 0

    for call in calls:
        date_sort = call.get("fecha") or ""
        transcript = call.get("transcript") or ""
        has_real_transcript = len(transcript) >= 200
        has_role = call.get("rol") is not None

        if has_real_transcript and has_role and not _is_audited(call):
            items.append((date_sort, "audit_existing", call))
            auditable_count += 1
        else:
            dur_s = call.get("duracion_segundos") or 0
            dur_min = round(dur_s / 60) if dur_s else 0
            owner = call.get("owner_nombre") or call.get("owner_email") or "?"
            hs_id = call.get("hs_call_id") or call["call_id"]
            items.append((
                date_sort,
                "context",
                _format_call_context(hs_id, {
                    "hs_timestamp": call.get("fecha"),
                    "hs_call_title": call.get("titulo"),
                    "hs_call_body": transcript if has_real_transcript else "",
                }, owner, dur_min),
            ))
            context_count += 1

    print(f"   {len(calls)} calls: {auditable_count} to audit, {context_count} context-only")

    # 4. Sort chronologically and process
    items.sort(key=lambda x: x[0])
    pending_context: list[str] = []
    audit_failures = 0

    print(f"\n6. Processing {len(items)} items chronologically ...\n")

    for i, (date_sort, item_type, payload) in enumerate(items, 1):
        date_display = _format_date(date_sort)
        if item_type == "context":
            preview = payload[:80].replace("\n", " ") if isinstance(payload, str) else "?"
            print(f"   [{i}/{len(items)}] CTX  {date_display} — {preview}")
            pending_context.append(payload)
        else:
            # Flush pending context BEFORE audit
            if pending_context:
                print(f"   --- flushing {len(pending_context)} context entries to DB ---")
                _flush_context(DEAL_UUID, pending_context)
                pending_context = []

            call = payload
            print(f"   [{i}/{len(items)}] AUDIT {date_display} — {call['rol']} {call.get('owner_nombre', '?')} [{call['call_id']}]")
            try:
                result = run_single(call["call_id"])
                if result:
                    print(f"         OK: win_rate={result.get('win_rate_score')}")
                else:
                    print(f"         Skipped")
                    audit_failures += 1
            except Exception as e:
                print(f"         FAILED: {e}")
                audit_failures += 1

    # Flush remaining context
    if pending_context:
        print(f"   --- flushing {len(pending_context)} remaining context entries ---")
        _flush_context(DEAL_UUID, pending_context)

    # 5. Read and print the final deal_context
    print(f"\n{'='*60}")
    print(f"FINAL DEAL_CONTEXT")
    print(f"{'='*60}\n")

    final = (
        supabase.table("deals")
        .select("deal_context")
        .eq("id", DEAL_UUID)
        .single()
        .execute()
    )
    context = final.data.get("deal_context") or "(empty)"
    print(context)
    print(f"\n{'='*60}")
    print(f"Total length: {len(context)} chars")
    print(f"Audit failures: {audit_failures}")
    print(f"HubSpot API requests: {hubspot.total_requests()}")


if __name__ == "__main__":
    main()
