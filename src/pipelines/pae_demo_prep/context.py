"""
Build full deal context for PAE demo preparation.
Reads pre-built deal_context from deals table.
"""

from src.db.client import supabase


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
    deal_context = deal_data.get("deal_context") or ""

    parts = []

    parts.append(f"## DEAL — {atlas.get('company_name') or deal_data.get('deal_name', '?')}")
    parts.append(f"Deal: {deal_data.get('deal_name', '?')} | Amount: {deal_data.get('amount') or '?'} | Stage: {deal_data.get('deal_stage', '?')}")
    parts.append(f"PBD: {deal_data.get('pbd', '?')} | PAE: {deal_data.get('pae', '?')}")
    parts.append(f"Contacts: {deal_data.get('contacts_info') or 'N/A'}")

    if atlas.get("company_context"):
        parts += ["", "--- COMPANY HISTORY (ATLAS) ---", "", atlas["company_context"]]

    if atlas.get("deal_history"):
        parts += ["", "--- PRIOR DEALS ---", "", atlas["deal_history"]]

    if atlas.get("contacts_map"):
        parts += ["", "--- CONTACTS MAP ---", "", atlas["contacts_map"]]

    if deal_context:
        parts += ["", "--- DEAL TIMELINE ---", "", deal_context]
    else:
        parts += ["", "--- DEAL TIMELINE ---", "", "No interactions recorded."]

    return deal_data, "\n".join(parts)
