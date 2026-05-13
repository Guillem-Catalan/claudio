"""
Temporary backfill: audit 1,575 pending calls on open deals.

For each call, builds context on-the-fly:
  - Atlas header (from DB)
  - Emails + notes from HubSpot (filtered to date < call.fecha)
  - Prior calls from DB (formatted as context)
  - Prior audits from DB (formatted as CALL AUDITED)

Writes results to pbd_audits / pae_audits only. Does NOT touch deal_context.
"""

import time

from src.db.client import supabase
from src.integrations.claude import analyze
from src.integrations import hubspot
from src.pipelines.audit.prompt_builder import build
from src.pipelines.audit.parser import parse
from src.pipelines.audit.context import INSTRUCTIONS, NO_CONTEXT
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
    _format_date,
)

# ── Rate limiter ────────────────────────────────────────────────────────

TOKENS_PER_AUDIT = 20_000
MAX_TOKENS_PER_MIN = 100_000
_window_start = 0.0
_window_tokens = 0


def _rate_limit():
    global _window_start, _window_tokens
    now = time.monotonic()
    if _window_start == 0.0:
        _window_start = now

    elapsed = now - _window_start
    if elapsed >= 60:
        _window_start = now
        _window_tokens = 0

    _window_tokens += TOKENS_PER_AUDIT
    if _window_tokens >= MAX_TOKENS_PER_MIN:
        sleep_time = 60 - elapsed
        if sleep_time > 0:
            print(f"    [rate-limit] sleeping {sleep_time:.0f}s")
            time.sleep(sleep_time)
        _window_start = time.monotonic()
        _window_tokens = 0


# ── Context builder ─────────────────────────────────────────────────────


def _format_existing_audit(call: dict, audit: dict) -> str:
    """Format an existing audit result as a context entry (same as append_audit_to_context)."""
    fecha = (call.get("fecha") or "?")[:10]
    rol = call.get("rol") or "?"
    tags = call.get("tags") or []
    tags_str = ", ".join(tags) if tags else "untagged"
    dur = round((call.get("duracion_segundos") or 0) / 60)
    rep = call.get("owner_nombre") or call.get("owner_email") or "?"
    call_id = call.get("call_id") or "?"

    parts = [f"[{fecha}] CALL AUDITED — {rol} {rep} — Tags: [{tags_str}] ({dur}min) [call:{call_id}]"]

    wrs = audit.get("win_rate_score")
    ff = audit.get("forecast_flag") or "—"
    pl = audit.get("partner_leverage_score") or "—"
    lt = audit.get("lead_temperature") or "—"
    parts.append(f"  Win rate: {wrs} | Forecast: {ff} | Partner leverage: {pl} | Temperature: {lt}")

    dc = audit.get("deal_context")
    if dc:
        parts.append(f"  Narrative: {dc[:500]}")

    gap = audit.get("biggest_gap")
    if gap:
        parts.append(f"  Biggest gap: {gap}")

    nco = audit.get("next_call_objective")
    if nco:
        parts.append(f"  Next objective: {nco}")

    for prefix, pillars in [
        ("bant", ("budget", "authority", "need", "timing")),
        ("meddic", ("metrics", "economic_buyer", "decision_criteria", "decision_process", "champion", "competition")),
    ]:
        pillar_lines = []
        for p in pillars:
            status = audit.get(f"{prefix}_{p}_status")
            if status and status != "Missing":
                evidence = audit.get(f"{prefix}_{p}_evidence") or ""
                line = f"    {p.replace('_', ' ').title()}: {status}"
                if evidence:
                    line += f' — "{evidence[:150]}"'
                pillar_lines.append(line)
        if pillar_lines:
            parts.append(f"  {prefix.upper()}:")
            parts.extend(pillar_lines)

    return "\n".join(parts)


def _build_context_for_call(
    call: dict,
    atlas_header: str,
    hs_emails: list[tuple[str, str]],
    hs_notes: list[tuple[str, str]],
    all_calls: list[dict],
    audit_cache: dict[str, dict],
) -> str:
    """Build deal context for a specific call, including only items with date < call.fecha."""
    call_date = call.get("fecha") or ""
    call_id = call.get("call_id")

    items: list[tuple[str, str]] = []

    for date, text in hs_emails:
        if date < call_date:
            items.append((date, text))

    for date, text in hs_notes:
        if date < call_date:
            items.append((date, text))

    for c in all_calls:
        c_date = c.get("fecha") or ""
        c_id = c.get("call_id")
        if c_date >= call_date or c_id == call_id:
            continue

        audit = audit_cache.get(c["id"])
        if audit:
            items.append((c_date, _format_existing_audit(c, audit)))
        else:
            dur_s = c.get("duracion_segundos") or 0
            dur_min = round(dur_s / 60) if dur_s else 0
            owner = c.get("owner_nombre") or c.get("owner_email") or "?"
            hs_id = c.get("hs_call_id") or c["call_id"]
            transcript = c.get("transcript") or ""
            items.append((c_date, _format_call_context(hs_id, {
                "hs_timestamp": c.get("fecha"),
                "hs_call_title": c.get("titulo"),
                "hs_call_body": transcript if len(transcript) >= 200 else "",
            }, owner, dur_min)))

    if not items and not atlas_header:
        return NO_CONTEXT

    items.sort(key=lambda x: x[0])
    context_text = "\n\n".join(text for _, text in items)

    parts = []
    if atlas_header:
        parts.append(atlas_header)
    if context_text:
        parts.append(context_text)

    if not parts:
        return NO_CONTEXT

    return INSTRUCTIONS + "\n\n" + "\n\n".join(parts)


# ── Audit one call ──────────────────────────────────────────────────────


def _audit_call(call: dict, context: str) -> dict | None:
    role = call.get("rol")
    if not role:
        return None

    system_prompt, user_prompt = build(call, context)

    _rate_limit()
    response_text = analyze(system_prompt, user_prompt)
    fields = parse(response_text, role)

    table = "pbd_audits" if role == "PBD" else "pae_audits"
    row = {
        "call_ref": call["id"],
        "call_id": call["call_id"],
        "deal_ref": call.get("deal_id"),
        "crm_id": call.get("crm_id"),
        "hs_deal_id": call.get("hs_deal_id"),
        "owner_name": call.get("owner_nombre"),
        **fields,
    }

    supabase.table(table).upsert(row, on_conflict="call_ref").execute()
    return row


# ── Load audit cache for a deal ─────────────────────────────────────────


def _load_audit_cache(deal_uuid: str) -> dict[str, dict]:
    """Load all existing audits for a deal, keyed by call_ref (calls.id)."""
    cache: dict[str, dict] = {}
    for table in ("pbd_audits", "pae_audits"):
        result = (
            supabase.table(table)
            .select("*")
            .eq("deal_ref", deal_uuid)
            .not_.is_("win_rate_score", "null")
            .execute()
        )
        for row in result.data or []:
            cache[row["call_ref"]] = row
    return cache


# ── Main ────────────────────────────────────────────────────────────────


def main():
    print("=== BACKFILL AUDITS: Open Deals ===\n")

    # 1. Find all pending calls grouped by deal
    print("1. Loading pending calls ...")

    offset = 0
    batch_size = 1000
    all_pending: list[dict] = []
    while True:
        result = (
            supabase.table("calls")
            .select("*, deals!inner(deal_id, deal_name, deal_stage)")
            .not_.is_("rol", "null")
            .gte("duracion_segundos", 1)
            .order("fecha")
            .range(offset, offset + batch_size - 1)
            .execute()
        )
        rows = result.data or []
        all_pending.extend(rows)
        if len(rows) < batch_size:
            break
        offset += batch_size

    # Filter: open deals + transcript >= 200 + not audited
    CLOSED_STAGES = {
        "Closed Won", "Closed won", "Closed Lost", "Closed lost",
        "Opportunity lost", "Opportunity won", "7. Closed Won",
        "Nurturing",
    }

    pending_by_deal: dict[str, list[dict]] = {}
    seen_call_refs: set[str] = set()

    for call in all_pending:
        deal = call.get("deals") or {}
        stage = deal.get("deal_stage") or ""
        if any(s.lower() in stage.lower() for s in ("closed", "lost", "won", "nurturing")):
            continue

        transcript = call.get("transcript") or ""
        if len(transcript) < 200:
            continue

        deal_uuid = call.get("deal_id")
        if not deal_uuid:
            continue

        seen_call_refs.add(call["id"])
        pending_by_deal.setdefault(deal_uuid, []).append(call)

    # Filter out already audited
    print("   Checking existing audits ...")
    audited_refs: set[str] = set()
    for table in ("pbd_audits", "pae_audits"):
        offset = 0
        while True:
            result = (
                supabase.table(table)
                .select("call_ref")
                .not_.is_("win_rate_score", "null")
                .range(offset, offset + batch_size - 1)
                .execute()
            )
            rows = result.data or []
            for row in rows:
                audited_refs.add(row["call_ref"])
            if len(rows) < batch_size:
                break
            offset += batch_size

    for deal_uuid in list(pending_by_deal.keys()):
        pending_by_deal[deal_uuid] = [
            c for c in pending_by_deal[deal_uuid] if c["id"] not in audited_refs
        ]
        if not pending_by_deal[deal_uuid]:
            del pending_by_deal[deal_uuid]

    total_pending = sum(len(v) for v in pending_by_deal.values())
    print(f"   {total_pending} pending calls across {len(pending_by_deal)} deals\n")

    if total_pending == 0:
        print("Nothing to do.")
        return

    # 2. Fetch owners once
    print("2. Fetching HubSpot owners ...")
    owners = _fetch_owners()

    # 3. Process deal by deal
    audit_count = 0
    error_count = 0
    start_time = time.monotonic()

    deal_list = sorted(pending_by_deal.items(), key=lambda x: len(x[1]))

    for deal_idx, (deal_uuid, pending_calls) in enumerate(deal_list, 1):
        deal_info = pending_calls[0].get("deals") or {}
        deal_name = deal_info.get("deal_name") or "?"
        hs_deal_id = deal_info.get("deal_id") or ""

        print(f"\n[{deal_idx}/{len(deal_list)}] {deal_name} — {len(pending_calls)} pending")

        if not hs_deal_id:
            print("   No hs_deal_id — skipping")
            continue

        # Atlas header
        atlas_header = _build_atlas_header(deal_uuid)

        # Fetch emails from HubSpot
        hs_emails: list[tuple[str, str]] = []
        try:
            email_ids = _fetch_associations(hs_deal_id, "emails")
            if email_ids:
                email_objects = _batch_read("emails", email_ids, EMAIL_PROPS)
                for obj in email_objects:
                    p = obj.get("properties", {})
                    hs_id = str(obj.get("id", ""))
                    date = p.get("hs_timestamp") or p.get("hs_createdate") or ""
                    hs_emails.append((date, _format_email(hs_id, p)))
        except Exception as e:
            print(f"   Email fetch error: {e}")

        # Fetch notes from HubSpot
        hs_notes: list[tuple[str, str]] = []
        try:
            note_ids = _fetch_associations(hs_deal_id, "notes")
            if note_ids:
                note_objects = _batch_read("notes", note_ids, NOTE_PROPS)
                for obj in note_objects:
                    p = obj.get("properties", {})
                    hs_id = str(obj.get("id", ""))
                    date = p.get("hs_timestamp") or p.get("hs_createdate") or ""
                    body = p.get("hs_note_body") or ""
                    if not body.strip():
                        hs_notes.append((
                            date,
                            f"[{_format_date(date)}] NOTE [hs:{hs_id}] — (sin contenido)",
                        ))
                    else:
                        hs_notes.append((date, _format_note(hs_id, p, owners)))
        except Exception as e:
            print(f"   Note fetch error: {e}")

        # Load ALL calls for this deal (for context)
        all_calls_result = (
            supabase.table("calls")
            .select("*")
            .eq("deal_id", deal_uuid)
            .order("fecha")
            .execute()
        )
        all_calls = all_calls_result.data or []

        # Load existing audits (for context of prior audited calls)
        audit_cache = _load_audit_cache(deal_uuid)

        # Sort pending calls by date
        pending_calls.sort(key=lambda c: c.get("fecha") or "")

        # Audit each pending call
        for call_idx, call in enumerate(pending_calls, 1):
            call_date = (call.get("fecha") or "?")[:10]
            call_id = call["call_id"]
            role = call.get("rol")

            print(f"   [{call_idx}/{len(pending_calls)}] {role} {call_date} {call_id} ", end="", flush=True)

            try:
                context = _build_context_for_call(
                    call, atlas_header, hs_emails, hs_notes, all_calls, audit_cache,
                )
                result = _audit_call(call, context)
                if result:
                    wrs = result.get("win_rate_score")
                    print(f"→ win_rate={wrs}")
                    audit_count += 1
                    # Add to audit_cache so next calls in this deal see it
                    audit_cache[call["id"]] = result
                else:
                    print("→ skipped")
            except Exception as e:
                print(f"→ ERROR: {e}")
                error_count += 1
                time.sleep(5)

    # Summary
    elapsed = time.monotonic() - start_time
    print(f"\n{'=' * 60}")
    print(f"Done in {elapsed / 60:.1f} min")
    print(f"Audited: {audit_count}")
    print(f"Errors: {error_count}")
    print(f"HubSpot API requests: {hubspot.total_requests()}")


if __name__ == "__main__":
    main()
