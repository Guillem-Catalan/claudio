"""
Orchestrator: search deals → read properties → resolve associations → upsert to Supabase.
"""

from datetime import datetime, timezone, timedelta

from src.config import ALL_PBD_EMAILS, ALL_PAE_EMAILS
from src.db.client import supabase
from src.integrations import hubspot
from src.pipelines.sync_deals.search import find_all_deal_ids, find_modified_deal_ids
from src.pipelines.sync_deals.properties import (
    fetch_pipeline_stages,
    fetch_owners,
    fetch_deal_properties,
    fetch_company_associations,
    fetch_contact_associations,
    fetch_contacts_info,
    fetch_engagement_counts,
    format_contacts_info,
)

UPSERT_BATCH = 500


def _resolve_atlas_ids(crm_ids: set[str]) -> dict[str, str]:
    if not crm_ids:
        return {}
    atlas_map: dict[str, str] = {}
    crm_list = list(crm_ids)
    for i in range(0, len(crm_list), 100):
        batch = crm_list[i : i + 100]
        result = (
            supabase.table("atlas")
            .select("id, crm_id")
            .in_("crm_id", batch)
            .execute()
        )
        for row in result.data or []:
            atlas_map[row["crm_id"]] = row["id"]
    return atlas_map


def _resolve_pbd_pae(owner_id: str, owners: dict) -> tuple[str, str]:
    if not owner_id or owner_id not in owners:
        return "", ""
    owner = owners[owner_id]
    email = owner["email"]
    name = owner["name"]
    pbd = name if email in ALL_PBD_EMAILS else ""
    pae = name if email in ALL_PAE_EMAILS else ""
    return pbd, pae


def _upsert(rows: list[dict]) -> int:
    written = 0
    for i in range(0, len(rows), UPSERT_BATCH):
        batch = rows[i : i + UPSERT_BATCH]
        result = (
            supabase.table("deals")
            .upsert(batch, on_conflict="deal_id")
            .execute()
        )
        written += len(result.data or [])
    return written


def run(full: bool = False, since_hours: int = 48):
    now = datetime.now(timezone.utc)

    # 1. Find deal IDs
    print("1. Searching for deals ...")
    if full:
        deal_ids = find_all_deal_ids()
    else:
        since_ms = int((now - timedelta(hours=since_hours)).timestamp() * 1000)
        deal_ids = find_modified_deal_ids(since_ms)

    if not deal_ids:
        print("   No deals found.")
        return

    deal_id_list = sorted(deal_ids)

    # 2. Fetch reference data
    print("\n2. Fetching pipeline stages ...")
    stages = fetch_pipeline_stages()
    print(f"   {len(stages)} stages loaded")

    print("\n3. Fetching owners ...")
    owners = fetch_owners()
    print(f"   {len(owners)} owners loaded")

    # 3. Batch read deal properties
    print(f"\n4. Reading properties for {len(deal_id_list)} deals ...")
    deals = fetch_deal_properties(deal_id_list, stages)
    print(f"   {len(deals)} deals read")

    # 4. Fetch associations
    print(f"\n5. Fetching company associations ...")
    company_map = fetch_company_associations(deal_id_list)
    print(f"   {len(company_map)} company links")

    print("\n6. Fetching contact associations ...")
    contact_map = fetch_contact_associations(deal_id_list)
    all_contact_ids = list({cid for ids in contact_map.values() for cid in ids})
    print(f"   {len(contact_map)} deals with contacts ({len(all_contact_ids)} unique contacts)")

    print("\n7. Fetching contact details ...")
    contacts = fetch_contacts_info(all_contact_ids)
    print(f"   {len(contacts)} contacts read")

    print("\n8. Counting engagements (notes, emails, calls) ...")
    engagement_counts = fetch_engagement_counts(deal_id_list)

    # 5. Resolve atlas IDs
    crm_ids = {company_map[did] for did in deal_id_list if did in company_map}
    print(f"\n9. Resolving atlas IDs for {len(crm_ids)} companies ...")
    atlas_map = _resolve_atlas_ids(crm_ids)
    print(f"   {len(atlas_map)} atlas matches")

    # 6. Build rows
    print("\n10. Building rows ...")
    now_str = now.isoformat()
    rows = []
    for deal in deals:
        did = deal["deal_id"]
        owner_id = deal.pop("_owner_id")
        deal.pop("_partner_name")
        pbd, pae = _resolve_pbd_pae(owner_id, owners)

        crm_id = company_map.get(did)
        atlas_id = atlas_map.get(crm_id) if crm_id else None

        deal["crm_id"] = crm_id
        deal["atlas_id"] = atlas_id
        deal["pbd"] = pbd
        deal["pae"] = pae
        deal["last_synced"] = now_str
        deal["contacts_info"] = format_contacts_info(
            contact_map.get(did, []), contacts
        )

        eng = engagement_counts.get(did, {})
        deal["numero_de_notas"] = eng.get("numero_de_notas", 0)
        deal["numero_de_emails"] = eng.get("numero_de_emails", 0)
        deal["numero_de_calls"] = eng.get("numero_de_calls", 0)

        rows.append(deal)

    # 7. Upsert
    print(f"\n11. Upserting {len(rows)} deals to Supabase ...")
    written = _upsert(rows)
    print(f"    {written} deals upserted")

    print(f"\n    HubSpot API requests: {hubspot.total_requests()}")
