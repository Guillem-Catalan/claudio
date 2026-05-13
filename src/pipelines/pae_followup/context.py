"""
Build full context for PAE follow-up.
Loads: deal, call, pae_audit, deal_context, front_deals snapshot, company atlas.
Falls back to HubSpot live fetch when deal_context is empty.
"""

from src.db.client import supabase
from src.pipelines.pae_demo_prep.context_temp import build_context_from_hubspot


def load_full_context(call_ref: str) -> dict:
    """
    Returns a dict with all data needed for classification and generation:
      call, deal, pae_audit, deal_context, context_text,
      front_deals_snapshot, company, pae_name, contact, amount_str,
      partner, demo_datetime, demo_date_short.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    _MESES_CORTO = {
        1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
        7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic",
    }

    call = (
        supabase.table("calls")
        .select("*")
        .eq("id", call_ref)
        .maybe_single()
        .execute()
    )
    if not call.data:
        raise ValueError(f"Call {call_ref} not found")

    call_data = call.data
    deal_id = call_data.get("deal_id")
    if not deal_id:
        raise ValueError(f"No deal_id on call {call_ref}")

    deal = (
        supabase.table("deals")
        .select("*, atlas:atlas_id(company_name)")
        .eq("id", deal_id)
        .maybe_single()
        .execute()
    )
    if not deal.data:
        raise ValueError(f"Deal {deal_id} not found")

    deal_data = deal.data

    pae_audit = (
        supabase.table("pae_audits")
        .select("*")
        .eq("call_ref", call_ref)
        .maybe_single()
        .execute()
    )
    pae_audit_data = pae_audit.data if pae_audit.data else {}

    deal_context = deal_data.get("deal_context") or ""
    if not deal_context.strip():
        print("   deal_context empty — fetching from HubSpot ...")
        deal_context = build_context_from_hubspot(deal_id)

    context_parts = [
        f"## DEAL — {deal_data.get('deal_name', '?')}",
        f"Amount: {deal_data.get('amount') or '?'} | Stage: {deal_data.get('deal_stage', '?')}",
        f"PBD: {deal_data.get('pbd', '?')} | PAE: {deal_data.get('pae', '?')}",
        f"Contacts: {deal_data.get('contacts_info') or 'N/A'}",
        "",
        deal_context,
    ]
    context_text = "\n".join(context_parts)

    hs_deal_id = deal_data.get("hs_deal_id") or deal_data.get("deal_id") or ""
    front_snapshot = None
    if hs_deal_id:
        snap = (
            supabase.table("front_deal_snapshots")
            .select("*")
            .eq("hs_deal_id", str(hs_deal_id))
            .order("snapshot_date", desc=True)
            .limit(1)
            .maybe_single()
            .execute()
        )
        front_snapshot = snap.data if snap.data else None

    raw_company = (
        (deal_data.get("atlas") or {}).get("company_name")
        or deal_data.get("deal_name")
        or "?"
    )
    company = (
        raw_company.split(" - from ")[0].split(" from ")[0].strip()
        if " from " in raw_company
        else raw_company
    )

    contacts_info = deal_data.get("contacts_info") or ""
    if contacts_info:
        first_line = contacts_info.split("\n")[0]
        parts = [p.strip() for p in first_line.split("|")]
        contact = {
            "name": parts[0] if len(parts) > 0 else "?",
            "jobtitle": parts[1] if len(parts) > 1 else "",
            "email": parts[2] if len(parts) > 2 else "",
            "phone": parts[3] if len(parts) > 3 else "",
        }
    else:
        contact = {"name": "?", "jobtitle": "", "email": "", "phone": ""}

    pae_name = deal_data.get("pae") or call_data.get("owner_nombre") or ""

    fecha = call_data.get("fecha") or ""
    if fecha:
        try:
            dt = datetime.fromisoformat(fecha.replace("Z", "+00:00"))
            demo_date_short = f"{dt.day} {_MESES_CORTO[dt.month]}"
            madrid = dt.astimezone(ZoneInfo("Europe/Madrid"))
            demo_datetime = f"Demo · {madrid.day} {_MESES_CORTO[madrid.month]}, {madrid.strftime('%H:%M')}"
        except Exception:
            demo_date_short = fecha[:10]
            demo_datetime = f"Demo · {fecha[:10]}"
    else:
        demo_date_short = "—"
        demo_datetime = "Demo"

    amount = deal_data.get("amount")
    amount_str = f"€{float(amount):.0f} MRR" if amount else "MRR desconocido"

    deal_name = deal_data.get("deal_name") or ""
    partner = deal_name.split("from ")[-1].strip() if "from " in deal_name else "Santander"

    return {
        "call": call_data,
        "deal": deal_data,
        "pae_audit": pae_audit_data,
        "deal_context": deal_context,
        "context_text": context_text,
        "front_deals_snapshot": front_snapshot,
        "company": company,
        "pae_name": pae_name,
        "contact": contact,
        "amount_str": amount_str,
        "partner": partner,
        "demo_datetime": demo_datetime,
        "demo_date_short": demo_date_short,
    }
