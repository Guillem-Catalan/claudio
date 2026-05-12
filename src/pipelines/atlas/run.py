"""
Atlas: generate company historical context for audit enrichment.

Steps:
    1. Fetch company info from HubSpot (name, industry, size, etc.)
    2. Fetch all deals for this company from HubSpot
    3. Fetch all contacts for this company from HubSpot
    4. Build formatted breakdowns
    5. Call Claude to synthesize deal_history, contacts_map, company_context
    6. Write everything to atlas table + set last_generated
"""

import json
import re
from datetime import datetime, timezone

from src.db.client import supabase
from src.integrations import claude, hubspot
from src.pipelines.atlas.hubspot_fetcher import (
    fetch_company,
    fetch_contact_ids,
    fetch_contact_properties,
    fetch_deal_ids,
    fetch_deal_properties,
    fetch_owners,
)
from src.pipelines.atlas.prompt_builder import (
    build_user_prompt,
    format_company_info,
    format_contacts_breakdown,
    format_deals_breakdown,
    load_system_prompt,
)


def generate(atlas_id: str, crm_id: str, owners: dict[str, str] | None = None):
    print(f"1. Fetching company {crm_id} from HubSpot ...")
    company = fetch_company(crm_id)
    company_name = company.get("name") or ""
    print(f"   Company: {company_name}")

    if owners is None:
        print("2. Fetching owners ...")
        owners = fetch_owners()
    else:
        print("2. Owners (cached)")

    print("3. Fetching deals for this company ...")
    deal_ids = fetch_deal_ids(crm_id)
    print(f"   {len(deal_ids)} deals found")

    deals = fetch_deal_properties(deal_ids, owners) if deal_ids else []

    print("4. Fetching contacts for this company ...")
    contact_ids = fetch_contact_ids(crm_id)
    print(f"   {len(contact_ids)} contacts found")

    contacts = fetch_contact_properties(contact_ids) if contact_ids else []

    print("5. Building prompts ...")
    company_info_text = format_company_info(company)
    deals_breakdown_text = format_deals_breakdown(deals)
    contacts_breakdown_text = format_contacts_breakdown(contacts)

    system_prompt = load_system_prompt()
    user_prompt = build_user_prompt(
        company_info=company_info_text,
        deals_breakdown=deals_breakdown_text,
        contacts_breakdown=contacts_breakdown_text,
        n_deals=len(deals),
        n_contacts=len(contacts),
    )

    print("6. Calling Claude ...")
    raw_response = claude.analyze(system_prompt, user_prompt)

    print("7. Parsing response ...")
    text = re.sub(r"^```(?:json)?\s*", "", raw_response)
    text = re.sub(r"\s*```$", "", text).strip()
    if not text:
        raise ValueError(f"Empty response from Claude (raw length={len(raw_response)})")
    parsed = json.loads(text)
    deal_history = parsed.get("deal_history", "")
    contacts_map = parsed.get("contacts_map", "")
    company_context = parsed.get("company_context", "")

    print("8. Writing to Supabase ...")
    supabase.table("atlas").update({
        "company_name": company_name,
        "industry": company.get("industry") or None,
        "company_size": company.get("numberofemployees") or None,
        "country": company.get("country") or None,
        "website": company.get("website") or None,
        "description": company.get("description") or None,
        "company_info": company_info_text,
        "deals_breakdown": deals_breakdown_text,
        "contacts_breakdown": contacts_breakdown_text,
        "deal_history": deal_history,
        "contacts_map": contacts_map,
        "company_context": company_context,
        "last_generated": datetime.now(timezone.utc).isoformat(),
    }).eq("id", atlas_id).execute()

    print(f"   Atlas generated for {company_name}")
    print(f"   HubSpot API requests: {hubspot.total_requests()}")
