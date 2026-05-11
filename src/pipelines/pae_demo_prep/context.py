"""
Build full deal context for PAE demo preparation.
Pulls all interactions from Supabase: atlas, calls+audits, emails, notes.
"""

from datetime import datetime, timezone

from src.db.client import supabase

BANT_PILLARS = ("budget", "authority", "need", "timing")
STATUS_RANK = {"Confirmed": 3, "Partial": 2, "Missing": 1, "N/A": 0}


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _fmt(s: str | None) -> str:
    d = _parse_dt(s)
    return d.strftime("%Y-%m-%d") if d else "?"


def _best_status(audits: list[tuple[str, dict]], pillar: str) -> dict:
    best = {"status": "Missing", "confidence": None, "evidence": None}
    for _, audit in audits:
        status = audit.get(f"bant_{pillar}_status") or "Missing"
        if STATUS_RANK.get(status, 0) > STATUS_RANK.get(best["status"], 0):
            best = {
                "status": status,
                "confidence": audit.get(f"bant_{pillar}_confidence"),
                "evidence": audit.get(f"bant_{pillar}_evidence"),
            }
    return best


def _format_call(call: dict, audit: dict | None) -> str:
    fecha = _fmt(call.get("fecha"))
    rol = call.get("rol") or "?"
    tags = call.get("tags") or []
    tags_str = ", ".join(tags) if tags else "untagged"
    dur = round((call.get("duracion_segundos") or 0) / 60)
    rep = call.get("owner_nombre") or call.get("owner_email") or "?"

    header = f"[{fecha}] CALL — {rol} {rep} — Tags: [{tags_str}] ({dur}min)"

    if not audit:
        return header + "\n  (no audit data)"

    parts = [header]

    wrs = audit.get("win_rate_score")
    lt = audit.get("lead_temperature") or "—"
    parts.append(f"  Win rate: {wrs} | Temperature: {lt}")

    dc = audit.get("deal_context")
    if dc:
        parts.append(f"  Narrative: {dc[:500]}")

    gap = audit.get("biggest_gap")
    if gap:
        parts.append(f"  Biggest gap: {gap}")

    obj = audit.get("objections")
    if obj:
        parts.append(f"  Objections: {obj[:300]}")

    sig = audit.get("buying_signals")
    if sig:
        parts.append(f"  Buying signals: {sig[:300]}")

    return "\n".join(parts)


def _format_email(email: dict) -> str:
    fecha = _fmt(email.get("date"))
    direction = (email.get("direction") or "").upper()
    subject = email.get("subject") or "—"
    summary = email.get("email_summary") or "—"
    etype = email.get("email_type") or ""
    return f"[{fecha}] EMAIL {direction} — {etype} — {subject}\n  {summary}"


def _format_note(note: dict) -> str:
    fecha = _fmt(note.get("date"))
    owner = note.get("owner") or "?"
    content = (note.get("body") or "")[:300]
    return f"[{fecha}] NOTE — {owner}\n  {content}"


def build_context(deal_uuid: str) -> tuple[dict, str]:
    """Returns (deal_data, context_text) for the given deal."""

    deal = (
        supabase.table("deals")
        .select("*, atlas:atlas_id(company_name, company_context, deal_history, contacts_map, company_info, industry, company_size, country)")
        .eq("id", deal_uuid)
        .maybe_single()
        .execute()
    )
    if not deal.data:
        raise ValueError(f"Deal {deal_uuid} not found")

    deal_data = deal.data
    atlas = deal_data.get("atlas") or {}

    # Calls + audits
    calls = (
        supabase.table("calls")
        .select("*")
        .eq("deal_id", deal_uuid)
        .order("fecha")
        .execute()
    ).data or []

    pbd_audits = {
        a["call_ref"]: a
        for a in (
            supabase.table("pbd_audits")
            .select("*")
            .eq("deal_ref", deal_uuid)
            .execute()
        ).data or []
    }

    pae_audits = {
        a["call_ref"]: a
        for a in (
            supabase.table("pae_audits")
            .select("*")
            .eq("deal_ref", deal_uuid)
            .execute()
        ).data or []
    }

    # Emails
    emails = (
        supabase.table("emails")
        .select("*")
        .eq("deal_id", deal_uuid)
        .order("date")
        .execute()
    ).data or []

    # Notes
    notes = (
        supabase.table("notes")
        .select("*")
        .eq("deal_id", deal_uuid)
        .order("date")
        .execute()
    ).data or []

    # Build timeline
    _MIN_DT = datetime.min.replace(tzinfo=timezone.utc)
    events: list[tuple[str, datetime, object]] = []
    for c in calls:
        events.append(("call", _parse_dt(c.get("fecha")) or _MIN_DT, c))
    for e in emails:
        events.append(("email", _parse_dt(e.get("date")) or _MIN_DT, e))
    for n in notes:
        events.append(("note", _parse_dt(n.get("date")) or _MIN_DT, n))
    events.sort(key=lambda x: x[1])

    timeline_lines = []
    bant_pairs: list[tuple[str, dict]] = []

    for ev_type, _, rec in events:
        if ev_type == "call":
            audit = pbd_audits.get(rec["id"]) or pae_audits.get(rec["id"])
            timeline_lines.append(_format_call(rec, audit))
            if audit and rec.get("rol") == "PBD":
                bant_pairs.append((rec.get("fecha", ""), audit))
        elif ev_type == "email":
            timeline_lines.append(_format_email(rec))
        elif ev_type == "note":
            timeline_lines.append(_format_note(rec))

    # BANT cumulative
    cum_bant = {p: _best_status(bant_pairs, p) for p in BANT_PILLARS}

    n_pbd = sum(1 for c in calls if c.get("rol") == "PBD")
    n_pae = sum(1 for c in calls if c.get("rol") == "PAE")

    # Assemble
    parts = []

    parts.append(f"## DEAL — {atlas.get('company_name') or deal_data.get('deal_name', '?')}")
    parts.append(f"Deal: {deal_data.get('deal_name', '?')} | Amount: {deal_data.get('amount') or '?'} | Stage: {deal_data.get('deal_stage', '?')}")
    parts.append(f"PBD: {deal_data.get('pbd', '?')} | PAE: {deal_data.get('pae', '?')}")
    parts.append(f"Contacts: {deal_data.get('contacts_info') or 'N/A'}")
    parts.append(f"Interactions: {n_pbd} PBD calls + {n_pae} PAE calls + {len(emails)} emails + {len(notes)} notes")

    if atlas.get("company_context"):
        parts += ["", "--- COMPANY HISTORY (ATLAS) ---", "", atlas["company_context"]]

    if atlas.get("deal_history"):
        parts += ["", "--- PRIOR DEALS ---", "", atlas["deal_history"]]

    if atlas.get("contacts_map"):
        parts += ["", "--- CONTACTS MAP ---", "", atlas["contacts_map"]]

    # BANT state
    bant_lines = ["", "--- BANT STATE (cumulative from PBD calls) ---"]
    for p in BANT_PILLARS:
        d = cum_bant[p]
        line = f"  {p.title()}: {d['status']}"
        if d["evidence"]:
            line += f" — \"{d['evidence']}\""
        bant_lines.append(line)
    parts += bant_lines

    if timeline_lines:
        parts += ["", "--- DEAL TIMELINE ---", "", "\n\n".join(timeline_lines)]
    else:
        parts += ["", "--- DEAL TIMELINE ---", "", "No interactions recorded."]

    return deal_data, "\n".join(parts)
