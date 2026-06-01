"""
Resolve calendar attendees → deals via domain matching in Supabase.

Strategy:
  1. Filter out internal (@factorial) and partner domains
  2. Extract unique prospect domains from remaining attendees
  3. Search Supabase deals where contacts_info contains that domain
  4. Return matching open deal(s)
"""

from src.config import ALL_PARTNER_DOMAINS
from src.db.client import supabase

FACTORIAL_DOMAINS = {"factorial.co", "factorial.com"}

GENERIC_DOMAINS = frozenset({
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.es",
    "hotmail.com", "hotmail.es", "outlook.com", "outlook.es",
    "live.com", "icloud.com", "me.com", "protonmail.com",
    "aol.com", "mail.com", "zoho.com",
})

IGNORE_DOMAINS = FACTORIAL_DOMAINS | ALL_PARTNER_DOMAINS | GENERIC_DOMAINS

MAX_DEALS_PER_DOMAIN = 5

CLOSED_STAGES = {
    "opportunity lost", "closed lost", "closed won",
    "closed won - finance only", "closed - pending finance validation",
    "closed pending payment", "nurturing", "sales nurturing",
    "long nurturing", "hot nurturing",
}

ONBOARDING_STAGES = {
    "onboarding completed - converted",
    "onboarding completed - pending conversion",
    "onboarding failed", "onboarding on hold",
}

EXCLUDE_STAGES = CLOSED_STAGES | ONBOARDING_STAGES

_domain_cache: dict[str, list[dict]] = {}
_atlas_crm_cache: dict[str, list[str]] = {}


def _extract_domain(email: str) -> str:
    return email.split("@")[-1].lower() if "@" in email else ""


def is_external(email: str) -> bool:
    return _extract_domain(email) not in FACTORIAL_DOMAINS


def is_partner(email: str) -> bool:
    return _extract_domain(email) in ALL_PARTNER_DOMAINS


def is_prospect(email: str) -> bool:
    return _extract_domain(email) not in IGNORE_DOMAINS


def prospect_domains(attendees: list[dict]) -> set[str]:
    """Extract unique prospect domains from attendee list."""
    domains = set()
    for att in attendees:
        email = att.get("email", "")
        if not email:
            continue
        domain = _extract_domain(email)
        if domain and domain not in IGNORE_DOMAINS:
            domains.add(domain)
    return domains


def _crm_ids_for_domain(domain: str) -> list[str]:
    """Lookup atlas.website to find crm_ids matching a domain."""
    if domain in _atlas_crm_cache:
        return _atlas_crm_cache[domain]

    try:
        result = (
            supabase.table("atlas")
            .select("crm_id")
            .ilike("website", f"%{domain}%")
            .execute()
        )
        crm_ids = [r["crm_id"] for r in (result.data or []) if r.get("crm_id")]
    except Exception:
        crm_ids = []

    _atlas_crm_cache[domain] = crm_ids
    return crm_ids


def _filter_open(rows: list[dict]) -> list[dict]:
    matches = []
    for row in rows:
        stage = (row.get("deal_stage") or "").lower()
        if stage in EXCLUDE_STAGES:
            continue
        matches.append({
            "deal_id": row["id"],
            "hs_deal_id": row["deal_id"],
            "deal_name": row.get("deal_name") or "",
            "deal_stage": row.get("deal_stage") or "",
        })
    return matches


def resolve_domain(domain: str) -> list[dict]:
    """Find open deals in Supabase matching a prospect domain.

    Strategy:
      1. Search deals.contacts_info for @domain (covers ~89% of deals)
      2. Fallback: search atlas.website for domain → crm_id → deals

    Returns list of {deal_id (uuid), hs_deal_id, deal_name, deal_stage}.
    """
    if domain in _domain_cache:
        return _domain_cache[domain]

    # Step 1: direct match via contacts_info email
    try:
        result = (
            supabase.table("deals")
            .select("id, deal_id, deal_name, deal_stage")
            .ilike("contacts_info", f"%@{domain}%")
            .execute()
        )
        matches = _filter_open(result.data or [])
    except Exception as e:
        print(f"    [resolver] Supabase query failed for @{domain}: {e}")
        matches = []

    # Step 2: fallback via atlas website → crm_id
    if not matches:
        crm_ids = _crm_ids_for_domain(domain)
        for crm_id in crm_ids:
            try:
                result = (
                    supabase.table("deals")
                    .select("id, deal_id, deal_name, deal_stage")
                    .eq("crm_id", crm_id)
                    .execute()
                )
                matches.extend(_filter_open(result.data or []))
            except Exception:
                pass

    # Safety net: if too many matches, domain is probably too generic
    if len(matches) > MAX_DEALS_PER_DOMAIN:
        print(f"    [resolver] @{domain} matched {len(matches)} deals — too generic, skipping")
        matches = []

    _domain_cache[domain] = matches
    return matches


def resolve_event(attendees: list[dict]) -> list[dict]:
    """Resolve a calendar event to deal(s) via attendee domains.

    Returns list of {deal_id, hs_deal_id, deal_name, deal_stage}.
    Empty list if no match or all attendees are internal/partner.
    """
    domains = prospect_domains(attendees)
    if not domains:
        return []

    all_matches = []
    seen_deal_ids = set()
    for domain in domains:
        for match in resolve_domain(domain):
            if match["deal_id"] not in seen_deal_ids:
                all_matches.append(match)
                seen_deal_ids.add(match["deal_id"])

    return all_matches


def clear_cache():
    _domain_cache.clear()
    _atlas_crm_cache.clear()
