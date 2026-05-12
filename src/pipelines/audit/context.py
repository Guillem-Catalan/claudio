from src.db.client import supabase

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


def get_deal_context(deal_uuid: str | None, call_date: str, role: str) -> str:
    if not deal_uuid:
        return NO_CONTEXT

    deal = (
        supabase.table("deals")
        .select("deal_context")
        .eq("id", deal_uuid)
        .maybe_single()
        .execute()
    )
    if not deal.data:
        return NO_CONTEXT

    deal_context = deal.data.get("deal_context") or ""
    if not deal_context.strip():
        return NO_CONTEXT

    return INSTRUCTIONS + "\n\n" + deal_context


def append_audit_to_context(deal_uuid: str, call: dict, audit_fields: dict):
    deal = (
        supabase.table("deals")
        .select("deal_context")
        .eq("id", deal_uuid)
        .maybe_single()
        .execute()
    )
    if not deal.data:
        return

    current = deal.data.get("deal_context") or ""

    fecha = (call.get("fecha") or "?")[:10]
    rol = call.get("rol") or "?"
    tags = call.get("tags") or []
    tags_str = ", ".join(tags) if tags else "untagged"
    dur = round((call.get("duracion_segundos") or 0) / 60)
    rep = call.get("owner_nombre") or call.get("owner_email") or "?"
    call_id = call.get("call_id") or "?"

    parts = [f"[{fecha}] CALL AUDITED — {rol} {rep} — Tags: [{tags_str}] ({dur}min) [call:{call_id}]"]

    wrs = audit_fields.get("win_rate_score")
    ff = audit_fields.get("forecast_flag") or "—"
    pl = audit_fields.get("partner_leverage_score") or "—"
    lt = audit_fields.get("lead_temperature") or "—"
    parts.append(f"  Win rate: {wrs} | Forecast: {ff} | Partner leverage: {pl} | Temperature: {lt}")

    dc = audit_fields.get("deal_context")
    if dc:
        parts.append(f"  Narrative: {dc[:500]}")

    gap = audit_fields.get("biggest_gap")
    if gap:
        parts.append(f"  Biggest gap: {gap}")

    nco = audit_fields.get("next_call_objective")
    if nco:
        parts.append(f"  Next objective: {nco}")

    obj = audit_fields.get("objections")
    if obj:
        parts.append(f"  Objections: {obj[:300]}")

    sig = audit_fields.get("buying_signals")
    if sig:
        parts.append(f"  Buying signals: {sig[:300]}")

    blk = audit_fields.get("blockers")
    if blk:
        parts.append(f"  Blockers: {blk[:300]}")

    for prefix, pillars in [
        ("bant", ("budget", "authority", "need", "timing")),
        ("meddic", ("metrics", "economic_buyer", "decision_criteria", "decision_process", "champion", "competition")),
    ]:
        pillar_lines = []
        for p in pillars:
            status = audit_fields.get(f"{prefix}_{p}_status")
            if status and status != "Missing":
                evidence = audit_fields.get(f"{prefix}_{p}_evidence") or ""
                line = f"    {p.replace('_', ' ').title()}: {status}"
                if evidence:
                    line += f' — "{evidence[:150]}"'
                pillar_lines.append(line)
        if pillar_lines:
            parts.append(f"  {prefix.upper()}:")
            parts.extend(pillar_lines)

    entry = "\n".join(parts)

    if current:
        updated = current + "\n\n" + entry
    else:
        updated = entry

    supabase.table("deals").update(
        {"deal_context": updated}
    ).eq("id", deal_uuid).execute()
