"""
Temporary backfill: audit pending calls on open deals (excluding onboarding).

Phase 1: Audit calls (4 parallel deal workers)
Phase 2: Build deal_context for all open non-onboarding deals (4 parallel workers)
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.db.client import supabase
from src.integrations.claude import analyze
from src.integrations import hubspot
from src.pipelines.audit.prompt_builder import build
from src.pipelines.audit.parser import parse
from src.pipelines.audit.context import INSTRUCTIONS, NO_CONTEXT
from src.pipelines.sync_deal_context.run import run as run_deal_context
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

WORKERS = 4

# ── Thread-safe rate limiter ───────────────────────────────────────────

TOKENS_PER_AUDIT = 20_000
MAX_TOKENS_PER_MIN = 100_000
_rate_lock = threading.Lock()
_window_start = 0.0
_window_tokens = 0


def _rate_limit():
    global _window_start, _window_tokens
    with _rate_lock:
        now = time.monotonic()
        if _window_start == 0.0:
            _window_start = now

        elapsed = now - _window_start
        if elapsed >= 60:
            _window_start = now
            _window_tokens = 0
            elapsed = 0

        _window_tokens += TOKENS_PER_AUDIT
        if _window_tokens >= MAX_TOKENS_PER_MIN:
            sleep_time = 60 - elapsed
            if sleep_time > 0:
                print(f"    [rate-limit] sleeping {sleep_time:.0f}s", flush=True)
                _rate_lock.release()
                time.sleep(sleep_time)
                _rate_lock.acquire()
            _window_start = time.monotonic()
            _window_tokens = 0


# ── Thread-safe counters ──────────────────────────────────────────────

_counter_lock = threading.Lock()
_audit_count = 0
_error_count = 0


def _inc_audit():
    global _audit_count
    with _counter_lock:
        _audit_count += 1
        return _audit_count


def _inc_error():
    global _error_count
    with _counter_lock:
        _error_count += 1
        return _error_count


# ── Context builder ─────────────────────────────────────────────────────


def _format_existing_audit(call: dict, audit: dict) -> str:
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


def _load_audit_cache(deal_uuid: str) -> dict[str, dict]:
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


# ── Process one deal (runs in thread) ──────────────────────────────────


def _process_deal(
    deal_idx: int,
    total_deals: int,
    deal_uuid: str,
    pending_calls: list[dict],
    owners: dict,
) -> None:
    deal_info = pending_calls[0].get("deals") or {}
    deal_name = deal_info.get("deal_name") or "?"
    hs_deal_id = deal_info.get("deal_id") or ""

    print(f"\n[{deal_idx}/{total_deals}] {deal_name} — {len(pending_calls)} pending", flush=True)

    if not hs_deal_id:
        print(f"   [{deal_name}] No hs_deal_id — skipping", flush=True)
        return

    atlas_header = _build_atlas_header(deal_uuid)

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
        print(f"   [{deal_name}] Email fetch error: {e}", flush=True)

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
        print(f"   [{deal_name}] Note fetch error: {e}", flush=True)

    all_calls_result = (
        supabase.table("calls")
        .select("*")
        .eq("deal_id", deal_uuid)
        .order("fecha")
        .execute()
    )
    all_calls = all_calls_result.data or []

    audit_cache = _load_audit_cache(deal_uuid)

    pending_calls.sort(key=lambda c: c.get("fecha") or "")

    for call_idx, call in enumerate(pending_calls, 1):
        call_date = (call.get("fecha") or "?")[:10]
        call_id = call["call_id"]
        role = call.get("rol")

        try:
            context = _build_context_for_call(
                call, atlas_header, hs_emails, hs_notes, all_calls, audit_cache,
            )
            result = _audit_call(call, context)
            if result:
                wrs = result.get("win_rate_score")
                print(f"   [{deal_name}] {call_idx}/{len(pending_calls)} {role} {call_date} → win_rate={wrs}", flush=True)
                _inc_audit()
                audit_cache[call["id"]] = result
            else:
                print(f"   [{deal_name}] {call_idx}/{len(pending_calls)} → skipped", flush=True)
        except Exception as e:
            print(f"   [{deal_name}] {call_idx}/{len(pending_calls)} → ERROR: {e}", flush=True)
            _inc_error()
            time.sleep(5)


# ── Process one deal context (runs in thread) ─────────────────────────


def _process_deal_context(
    deal_idx: int,
    total_deals: int,
    deal: dict,
) -> bool:
    deal_name = deal.get("deal_name") or "?"
    try:
        print(f"[{deal_idx}/{total_deals}] {deal_name}", flush=True)
        run_deal_context(deal_uuid=deal["id"], hs_deal_id=deal["deal_id"])
        return True
    except Exception as e:
        print(f"   [{deal_name}] ERROR: {e}", flush=True)
        time.sleep(2)
        return False


# ── Main ────────────────────────────────────────────────────────────────


def main():
    print(f"=== BACKFILL AUDITS: Open Deals ({WORKERS} workers) ===\n")

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

    pending_by_deal: dict[str, list[dict]] = {}

    for call in all_pending:
        deal = call.get("deals") or {}
        stage = deal.get("deal_stage") or ""
        if any(s.lower() in stage.lower() for s in ("closed", "lost", "won", "nurturing")):
            continue

        deal_name = (deal.get("deal_name") or "").lower()
        if "session" in deal_name:
            continue

        transcript = call.get("transcript") or ""
        if len(transcript) < 200:
            continue

        deal_uuid = call.get("deal_id")
        if not deal_uuid:
            continue

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

    # 2. Fetch owners once
    print("2. Fetching HubSpot owners ...")
    owners = _fetch_owners()

    # 3. Process deals in parallel
    start_time = time.monotonic()
    deal_list = sorted(pending_by_deal.items(), key=lambda x: len(x[1]))

    if total_pending > 0:
        print(f"\n3. Auditing with {WORKERS} workers ...\n")
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = []
            for deal_idx, (deal_uuid, pending_calls) in enumerate(deal_list, 1):
                futures.append(pool.submit(
                    _process_deal, deal_idx, len(deal_list),
                    deal_uuid, pending_calls, owners,
                ))
            for f in as_completed(futures):
                try:
                    f.result()
                except Exception as e:
                    print(f"   Worker error: {e}", flush=True)
    else:
        print("Nothing to audit.")

    # Summary phase 1
    elapsed = time.monotonic() - start_time
    print(f"\n{'=' * 60}")
    print(f"Phase 1 done in {elapsed / 60:.1f} min")
    print(f"Audited: {_audit_count}")
    print(f"Errors: {_error_count}")
    print(f"HubSpot API requests: {hubspot.total_requests()}")

    # ── Phase 2: Deal Context ──────────────────────────────────────────

    print(f"\n{'=' * 60}")
    print(f"=== PHASE 2: Deal Context ({WORKERS} workers) ===\n")

    offset = 0
    dc_deals: list[dict] = []
    while True:
        result = (
            supabase.table("deals")
            .select("id, deal_id, deal_name, deal_stage")
            .or_("deal_context.is.null,deal_context.eq.")
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
            dc_deals.append(d)
        if len(rows) < 1000:
            break
        offset += 1000

    print(f"{len(dc_deals)} deals to build context for\n")

    dc_count = 0
    dc_errors = 0

    if dc_deals:
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = []
            for i, deal in enumerate(dc_deals, 1):
                futures.append(pool.submit(
                    _process_deal_context, i, len(dc_deals), deal,
                ))
            for f in as_completed(futures):
                try:
                    ok = f.result()
                    if ok:
                        dc_count += 1
                    else:
                        dc_errors += 1
                except Exception as e:
                    print(f"   Worker error: {e}", flush=True)
                    dc_errors += 1

    total_elapsed = time.monotonic() - start_time
    print(f"\n{'=' * 60}")
    print(f"Phase 2 done. Total elapsed: {total_elapsed / 60:.1f} min")
    print(f"Deal contexts built: {dc_count}")
    print(f"Deal context errors: {dc_errors}")
    print(f"Total HubSpot API requests: {hubspot.total_requests()}")


if __name__ == "__main__":
    main()
