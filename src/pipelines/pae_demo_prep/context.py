"""
Build full deal context for PAE demo preparation.
Reads pre-built deal_context from deals table (already includes atlas).
"""

from src.db.client import supabase


def build_context(deal_uuid: str) -> tuple[dict, str]:
    """Returns (deal_data, context_text) for the given deal."""

    deal = (
        supabase.table("deals")
        .select("*, atlas:atlas_id(company_name, partner)")
        .eq("id", deal_uuid)
        .maybe_single()
        .execute()
    )
    if not deal.data:
        raise ValueError(f"Deal {deal_uuid} not found")

    deal_data = deal.data
    deal_context = deal_data.get("deal_context") or ""

    parts = [
        f"## DEAL — {deal_data.get('deal_name', '?')}",
        f"Amount: {deal_data.get('amount') or '?'} | Stage: {deal_data.get('deal_stage', '?')}",
        f"PBD: {deal_data.get('pbd', '?')} | PAE: {deal_data.get('pae', '?')}",
        f"Contacts: {deal_data.get('contacts_info') or 'N/A'}",
        "",
        deal_context or "No interactions recorded.",
    ]

    return deal_data, "\n".join(parts)
