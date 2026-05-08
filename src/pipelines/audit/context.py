from datetime import datetime, timezone

from src.db.client import supabase

STATUS_RANK = {"Confirmed": 3, "Partial": 2, "Missing": 1, "N/A": 0}

BANT_PILLARS = ("budget", "authority", "need", "timing")
MEDDIC_PILLARS = ("metrics", "economic_buyer", "decision_criteria",
                   "decision_process", "champion", "competition")

STILL_NEEDED = {
    "budget":            "Confirm budget ownership, frame Factorial as partner-discounted",
    "authority":         "Identify the true decision-maker and their role",
    "need":              "Surface a specific pain the prospect has verbalized",
    "timing":            "Identify trigger event, deadline, or timeframe",
    "metrics":           "Quantify business impact — hours saved, € cost, headcount",
    "economic_buyer":    "Confirm who signs the contract — not just HR contact",
    "decision_criteria": "Map mandatory requirements: integrations, GDPR, IT, price",
    "decision_process":  "Map approval chain: who, in what order, what can block",
    "champion":          "Confirm internal ally who can defend Factorial alone",
    "competition":       "Ask what alternatives are being evaluated",
}

INSTRUCTIONS = """\
## DEAL CONTEXT — HOW TO USE THIS

The following is the complete history of this deal up to the second
before this call starts. Treat it as ground truth.

BANT and MEDDIC are cumulative. A pillar confirmed in a previous call
carries forward — it does not reset. Your job is to assess what THIS
call added, confirmed, or left unchanged.

Missing pillars that should have been raised by now are explicit
coaching gaps — flag them in improvement_items."""

NO_CONTEXT = (
    "## DEAL CONTEXT\n\n"
    "No prior interactions recorded for this deal.\n"
    "Treat this as a first contact — evaluate without prior context."
)


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


def _before(date_str: str | None, cutoff: str) -> bool:
    d, c = _parse_dt(date_str), _parse_dt(cutoff)
    return bool(d and c and d < c)


def _best_status(audits: list[dict], prefix: str, pillar: str) -> dict:
    best = {"status": "Missing", "confidence": None, "evidence": None, "source": None}
    for date_str, audit in audits:
        status = audit.get(f"{prefix}_{pillar}_status") or "Missing"
        rank = STATUS_RANK.get(status, 0)
        if rank > STATUS_RANK.get(best["status"], 0):
            best = {
                "status": status,
                "confidence": audit.get(f"{prefix}_{pillar}_confidence"),
                "evidence": audit.get(f"{prefix}_{pillar}_evidence"),
                "source": date_str,
            }
    return best


def _format_cumulative(cumulative: dict, pillars: tuple, label: str) -> str:
    lines = [f"{label}:"]
    covered = 0
    for p in pillars:
        d = cumulative[p]
        hint = STILL_NEEDED.get(p, "")
        lines.append(f"  {p.replace('_', ' ').title():<22} {d['status']}")
        if d["evidence"]:
            lines.append(f"  {'':22} \"{d['evidence']}\" — {_fmt(d['source'])}")
        if d["status"] not in ("Confirmed", "N/A") and hint:
            lines.append(f"  {'':22} → Still needed: {hint}")
        if d["status"] in ("Confirmed", "Partial"):
            covered += 1
    lines.append(f"\n  Coverage: {covered}/{len(pillars)} pillars Confirmed or Partial")
    return "\n".join(lines)


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

    obj = audit.get("objections")
    if obj:
        parts.append(f"  Objections: {obj[:300]}")

    sig = audit.get("buying_signals")
    if sig:
        parts.append(f"  Buying signals: {sig[:300]}")

    blk = audit.get("blockers")
    if blk:
        parts.append(f"  Blockers: {blk[:300]}")

    return "\n".join(parts)


def _format_email(email: dict) -> str:
    fecha = _fmt(email.get("date"))
    direction = (email.get("direction") or "").upper()
    subject = email.get("subject") or "—"
    summary = email.get("email_summary") or "—"
    return f"[{fecha}] EMAIL {direction} — {subject}\n  {summary}"


def _format_note(note: dict) -> str:
    fecha = _fmt(note.get("created_hs"))
    author = note.get("author") or "?"
    content = (note.get("content") or "")[:300]
    return f"[{fecha}] NOTE — {author}\n  {content}"


def get_deal_context(deal_uuid: str | None, call_date: str, role: str) -> str:
    if not deal_uuid:
        return NO_CONTEXT

    deal = (
        supabase.table("deals")
        .select("*, atlas:atlas_id(company_context, name)")
        .eq("id", deal_uuid)
        .maybe_single()
        .execute()
    )
    if not deal.data:
        return NO_CONTEXT

    deal_data = deal.data
    atlas = deal_data.get("atlas") or {}
    atlas_context = atlas.get("company_context") or ""
    company_name = atlas.get("name") or deal_data.get("deal_name") or "?"

    prior_calls = (
        supabase.table("calls")
        .select("*")
        .eq("deal_id", deal_uuid)
        .order("fecha")
        .execute()
    ).data or []
    prior_calls = [c for c in prior_calls if _before(c.get("fecha"), call_date)]

    pbd_audits_raw = (
        supabase.table("pbd_audits")
        .select("*")
        .eq("deal_ref", deal_uuid)
        .execute()
    ).data or []

    pae_audits_raw = (
        supabase.table("pae_audits")
        .select("*")
        .eq("deal_ref", deal_uuid)
        .execute()
    ).data or []

    pbd_audit_map = {a["call_ref"]: a for a in pbd_audits_raw}
    pae_audit_map = {a["call_ref"]: a for a in pae_audits_raw}

    prior_emails = (
        supabase.table("emails")
        .select("*")
        .eq("deal_id", deal_uuid)
        .order("date")
        .execute()
    ).data or []
    prior_emails = [e for e in prior_emails if _before(e.get("date"), call_date)]

    prior_notes = (
        supabase.table("notes")
        .select("*")
        .eq("deal_id", deal_uuid)
        .order("created_hs")
        .execute()
    ).data or []
    prior_notes = [n for n in prior_notes if _before(n.get("created_hs"), call_date)]

    if not prior_calls and not prior_emails and not prior_notes:
        return NO_CONTEXT

    _MIN_DT = datetime.min.replace(tzinfo=timezone.utc)
    events: list[tuple[str, datetime, str]] = []
    for c in prior_calls:
        events.append(("call", _parse_dt(c.get("fecha")) or _MIN_DT, c))
    for e in prior_emails:
        events.append(("email", _parse_dt(e.get("date")) or _MIN_DT, e))
    for n in prior_notes:
        events.append(("note", _parse_dt(n.get("created_hs")) or _MIN_DT, n))
    events.sort(key=lambda x: x[1])

    timeline_lines = []
    bant_pairs: list[tuple[str, dict]] = []
    meddic_pairs: list[tuple[str, dict]] = []

    for ev_type, ev_dt, rec in events:
        if ev_type == "call":
            audit = pbd_audit_map.get(rec["id"]) or pae_audit_map.get(rec["id"])
            timeline_lines.append(_format_call(rec, audit))
            if audit:
                fecha_str = rec.get("fecha", "")
                if rec.get("rol") == "PBD":
                    bant_pairs.append((fecha_str, audit))
                elif rec.get("rol") == "PAE":
                    meddic_pairs.append((fecha_str, audit))
        elif ev_type == "email":
            timeline_lines.append(_format_email(rec))
        elif ev_type == "note":
            timeline_lines.append(_format_note(rec))

    cum_bant = {p: _best_status(bant_pairs, "bant", p) for p in BANT_PILLARS}
    cum_meddic = {p: _best_status(meddic_pairs, "meddic", p) for p in MEDDIC_PILLARS}

    n_pbd = sum(1 for c in prior_calls if c.get("rol") == "PBD")
    n_pae = sum(1 for c in prior_calls if c.get("rol") == "PAE")

    parts = [INSTRUCTIONS, ""]

    parts.append(f"## DEAL — {company_name} (Deal: {deal_data.get('deal_id', '?')})")
    parts.append(f"Prior interactions: {n_pbd} PBD calls + {n_pae} PAE calls + {len(prior_emails)} emails + {len(prior_notes)} notes")

    if atlas_context:
        parts += ["", "--- COMPANY HISTORY (ATLAS) ---", "", atlas_context]

    parts += ["", "--- DEAL TIMELINE ---", "", "\n\n".join(timeline_lines)]

    parts += ["", "--- CUMULATIVE STATE ENTERING THIS CALL ---", ""]
    if role == "PBD" or bant_pairs:
        parts.append(_format_cumulative(cum_bant, BANT_PILLARS, "BANT"))
    if role == "PAE" or meddic_pairs:
        parts.append(_format_cumulative(cum_meddic, MEDDIC_PILLARS, "MEDDIC"))

    return "\n".join(parts)
