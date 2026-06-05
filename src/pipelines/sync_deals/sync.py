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
    fetch_meeting_details,
    format_contacts_info,
)

UPSERT_BATCH = 500

EXCLUDE_PIPELINES = {
    "brazil sales pipeline", "churn pipeline", "upselling pipeline",
    "it sdr pipeline", "xl account pipeline", "onboarding pipeline",
}

CLOSED_STAGES = {
    "closed won", "closed lost", "opportunity lost",
    "closed won - finance only", "closed - pending finance validation",
    "closed pending payment",
    "onboarding completed - converted", "onboarding completed - pending conversion",
    "onboarding failed", "onboarding on hold",
    "> 75% sessions done", "51-75% sessions done", "26-50% sessions done",
    "≤ 25% sessions done", "1st session scheduled", "client pending to launch",
    "churned (closed)", "retained (closed)", "preventive churn risk (new)",
    "requested churn (new)", "(do not use) churn confirmed",
    "product related process (ongoing)", "pending approval because low joined rate",
    "wrongly created ticket (closed)", "spam",
    "(do not use) pending post-mortem analysis", "(do not use) action plan",
}


def _resolve_atlas_ids(crm_ids: set[str]) -> dict[str, str]:
    if not crm_ids:
        return {}
    atlas_map: dict[str, str] = {}
    crm_list = list(crm_ids)
    try:
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
    except Exception:
        pass
    return atlas_map


def _resolve_pbd_pae(owner_id: str, all_owner_ids: list[str], owners: dict) -> tuple[str, str]:
    pae = ""
    pbd = ""

    # Current owner → PAE if in PAE list, else PBD
    if owner_id and owner_id in owners:
        owner = owners[owner_id]
        if owner["email"] in ALL_PAE_EMAILS:
            pae = owner["name"]
        elif owner["email"] in ALL_PBD_EMAILS:
            pbd = owner["name"]

    # First historical owner that's a PBD → PBD (deal creator)
    if not pbd:
        for oid in all_owner_ids:
            oid = oid.strip()
            if oid and oid in owners:
                o = owners[oid]
                if o["email"] in ALL_PBD_EMAILS:
                    pbd = o["name"]
                    break

    # If still no PAE, check all owners for first PAE
    if not pae:
        for oid in all_owner_ids:
            oid = oid.strip()
            if oid and oid in owners:
                o = owners[oid]
                if o["email"] in ALL_PAE_EMAILS:
                    pae = o["name"]
                    break

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
        # Use last successful sync as cutoff instead of fixed 48h window
        last_synced_result = (
            supabase.table("deals")
            .select("last_synced")
            .not_.is_("last_synced", "null")
            .order("last_synced", desc=True)
            .limit(1)
            .execute()
        )
        if last_synced_result.data and last_synced_result.data[0].get("last_synced"):
            last = datetime.fromisoformat(last_synced_result.data[0]["last_synced"])
            since_ms = int((last - timedelta(minutes=30)).timestamp() * 1000)
            print(f"   Using last_synced cutoff: {last.isoformat()} (- 30min overlap)")
        else:
            since_ms = int((now - timedelta(hours=since_hours)).timestamp() * 1000)
            print(f"   No last_synced found — falling back to {since_hours}h window")
        deal_ids = find_modified_deal_ids(since_ms)

    if not deal_ids:
        print("   No deals found.")
        return

    deal_id_list = sorted(deal_ids)

    # 2. Fetch reference data
    print("\n2. Fetching pipeline stages ...")
    stages, pipeline_labels = fetch_pipeline_stages()
    print(f"   {len(stages)} stages loaded")

    print("\n3. Fetching owners ...")
    owners = fetch_owners()
    print(f"   {len(owners)} owners loaded")

    # 3. Batch read deal properties
    print(f"\n4. Reading properties for {len(deal_id_list)} deals ...")
    deals = fetch_deal_properties(deal_id_list, stages, pipeline_labels)
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

    print("\n8b. Fetching meeting details ...")
    meeting_details = fetch_meeting_details(deal_id_list)
    total_meetings = sum(len(v) for v in meeting_details.values())
    print(f"    {total_meetings} meetings across {len(meeting_details)} deals")

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
        all_owner_ids = deal.pop("_all_owner_ids", [])
        partner_name = deal.pop("_partner_name")
        pipeline_name = deal.pop("_pipeline", "")
        pbd, pae = _resolve_pbd_pae(owner_id, all_owner_ids, owners)

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
        deal["numero_de_meetings"] = eng.get("numero_de_meetings", 0)

        deal["_pipeline"] = pipeline_name
        rows.append(deal)

    # 6b. Filter out new deals in excluded pipelines or closed stages
    existing_ids = set()
    for i in range(0, len(rows), 200):
        batch = [r["deal_id"] for r in rows[i:i + 200]]
        result = supabase.table("deals").select("deal_id").in_("deal_id", batch).execute()
        existing_ids |= {r["deal_id"] for r in (result.data or [])}

    before = len(rows)
    filtered = []
    skipped_closed = 0
    skipped_pipeline = 0
    for r in rows:
        is_new = r["deal_id"] not in existing_ids
        if is_new:
            if (r.get("deal_stage") or "").lower() in CLOSED_STAGES:
                skipped_closed += 1
                continue
            if (r.get("_pipeline") or "").lower() in EXCLUDE_PIPELINES:
                skipped_pipeline += 1
                continue
        r.pop("_pipeline", None)
        filtered.append(r)
    rows = filtered

    if skipped_closed:
        print(f"   Skipped {skipped_closed} new closed deals")
    if skipped_pipeline:
        print(f"   Skipped {skipped_pipeline} new deals in excluded pipelines")

    # 7. Upsert
    print(f"\n11. Upserting {len(rows)} deals to Supabase ...")
    written = _upsert(rows)
    print(f"    {written} deals upserted")

    # 8. Upsert meetings
    if meeting_details:
        print(f"\n12. Upserting {total_meetings} meetings to Supabase ...")

        hs_deal_ids_with_meetings = list(meeting_details.keys())
        deal_uuid_map: dict[str, str] = {}
        for i in range(0, len(hs_deal_ids_with_meetings), 200):
            batch = hs_deal_ids_with_meetings[i : i + 200]
            existing = (
                supabase.table("deals")
                .select("id, deal_id")
                .in_("deal_id", batch)
                .execute()
            )
            for r in existing.data or []:
                deal_uuid_map[r["deal_id"]] = r["id"]

        seen_meetings: set[str] = set()
        meeting_rows: list[dict] = []
        for hs_did, meetings in meeting_details.items():
            deal_uuid = deal_uuid_map.get(hs_did)
            for m in meetings:
                mid = m.get("hs_meeting_id")
                if not mid or mid in seen_meetings:
                    continue
                seen_meetings.add(mid)
                row = {
                    "hs_deal_id": hs_did,
                    "hs_meeting_id": mid,
                    "meeting_start": m.get("meeting_start"),
                    "meeting_end": m.get("meeting_end"),
                    "title": m.get("title", ""),
                    "outcome": m.get("outcome", "SCHEDULED"),
                }
                if deal_uuid:
                    row["deal_id"] = deal_uuid
                meeting_rows.append(row)

        written_meetings = 0
        for i in range(0, len(meeting_rows), 500):
            batch = meeting_rows[i : i + 500]
            result = (
                supabase.table("deal_meetings")
                .upsert(batch, on_conflict="hs_meeting_id")
                .execute()
            )
            written_meetings += len(result.data or [])
        print(f"    {written_meetings} meetings upserted")

    print(f"\n    HubSpot API requests: {hubspot.total_requests()}")
