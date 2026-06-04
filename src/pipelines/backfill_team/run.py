"""
Backfill pipeline for new teams.
Runs independently from run_deals — won't compete with Sant/Tel queue.

Phases:
  sync     — search HubSpot + upsert to Supabase (skip closed + excluded pipelines)
  context  — build deal_context for deals without one (atlas + HubSpot + Modjo + audits)
  snapshot — generate front_deal_snapshots for deals with context
  all      — sync → context → snapshot
"""

import traceback

from src.config import TEAMS
from src.db.client import supabase
from src.pipelines.sync_deals.sync import (
    run as sync_deals_run,
    CLOSED_STAGES,
    EXCLUDE_PIPELINES,
)
from src.pipelines.sync_deals.search import find_tim_deal_ids, find_tim_modified_ids
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
from src.pipelines.sync_deal_context.run import run as sync_deal_context
from src.pipelines.front_deals.run import run as front_deals_snapshot
from src.pipelines.atlas.run import generate as atlas_generate
from src.pipelines.audit.run import run_single as audit_call

TEAM_SEARCH = {
    "TIM": {
        "find_all": find_tim_deal_ids,
    },
}

ACTIVE_STAGES = {
    "Factorial Project Alignment started",
    "Demo Booked", "Meeting Booked",
    "MEDDPICC Criteria Validation Started",
    "Economical Allignment Started",
    "Pricing and Packaging", "Pricing & Packaging",
    "Contract Sent",
    "Discovery", "Product Alignment",
    "Pre-qualified", "Engaged", "Attempting to contact",
    "Associating the partner", "Research & Outreach",
    "New", "New Deals", "Opportunity detected",
    "On Hold", "Nurturing", "To reschedule",
    "Sales Nurturing", "Connected - Not Engaged",
    "Long Nurturing", "Hot Nurturing",
    "Attempted to contact", "Meeting scheduled",
    "Contract negotiation (Ongoing) ",
}


def _resolve_pbd_pae(owner_id: str, owners: dict) -> tuple[str, str]:
    from src.config import ALL_PBD_EMAILS, ALL_PAE_EMAILS
    if not owner_id or owner_id not in owners:
        return "", ""
    owner = owners[owner_id]
    email = owner["email"]
    name = owner["name"]
    pbd = name if email in ALL_PBD_EMAILS else ""
    pae = name if email in ALL_PAE_EMAILS else ""
    return pbd, pae


def _resolve_atlas_ids(crm_ids: set[str]) -> dict[str, str]:
    if not crm_ids:
        return {}
    atlas_map: dict[str, str] = {}
    crm_list = list(crm_ids)
    for i in range(0, len(crm_list), 100):
        batch = crm_list[i:i + 100]
        result = supabase.table("atlas").select("id, crm_id").in_("crm_id", batch).execute()
        for row in (result.data or []):
            atlas_map[row["crm_id"]] = row["id"]
    return atlas_map


def run_sync(team: str):
    """Phase 1: Search HubSpot for team deals, filter, upsert."""
    search_config = TEAM_SEARCH.get(team)
    if not search_config:
        print(f"  No search config for team '{team}'")
        return 0

    print(f"  Searching {team} deals in HubSpot ...")
    deal_ids = search_config["find_all"]()
    if not deal_ids:
        print("  No deals found.")
        return 0

    deal_id_list = sorted(deal_ids)

    print(f"  Fetching pipeline stages ...")
    stages, pipeline_labels = fetch_pipeline_stages()

    print(f"  Fetching owners ...")
    owners = fetch_owners()

    print(f"  Reading properties for {len(deal_id_list)} deals ...")
    deals = fetch_deal_properties(deal_id_list, stages, pipeline_labels)

    print(f"  Fetching associations ...")
    company_map = fetch_company_associations(deal_id_list)
    contact_map = fetch_contact_associations(deal_id_list)
    all_contact_ids = list({cid for ids in contact_map.values() for cid in ids})
    contacts = fetch_contacts_info(all_contact_ids)
    engagement_counts = fetch_engagement_counts(deal_id_list)
    meeting_details = fetch_meeting_details(deal_id_list)

    crm_ids = {company_map[did] for did in deal_id_list if did in company_map}
    atlas_map = _resolve_atlas_ids(crm_ids)

    from datetime import datetime, timezone
    now_str = datetime.now(timezone.utc).isoformat()

    rows = []
    for deal in deals:
        did = deal["deal_id"]
        owner_id = deal.pop("_owner_id")
        deal.pop("_partner_name")
        pipeline_name = deal.pop("_pipeline", "")
        pbd, pae = _resolve_pbd_pae(owner_id, owners)

        crm_id = company_map.get(did)
        atlas_id = atlas_map.get(crm_id) if crm_id else None

        deal["crm_id"] = crm_id
        deal["atlas_id"] = atlas_id
        deal["pbd"] = pbd
        deal["pae"] = pae
        deal["last_synced"] = now_str
        deal["contacts_info"] = format_contacts_info(contact_map.get(did, []), contacts)

        eng = engagement_counts.get(did, {})
        deal["numero_de_notas"] = eng.get("numero_de_notas", 0)
        deal["numero_de_emails"] = eng.get("numero_de_emails", 0)
        deal["numero_de_calls"] = eng.get("numero_de_calls", 0)
        deal["numero_de_meetings"] = eng.get("numero_de_meetings", 0)

        deal["_pipeline"] = pipeline_name
        rows.append(deal)

    # Filter: skip new closed + excluded pipelines
    existing_ids = set()
    for i in range(0, len(rows), 200):
        batch = [r["deal_id"] for r in rows[i:i + 200]]
        result = supabase.table("deals").select("deal_id").in_("deal_id", batch).execute()
        existing_ids |= {r["deal_id"] for r in (result.data or [])}

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

    if skipped_closed:
        print(f"  Skipped {skipped_closed} closed deals")
    if skipped_pipeline:
        print(f"  Skipped {skipped_pipeline} deals in excluded pipelines")

    # Upsert
    print(f"  Upserting {len(filtered)} deals ...")
    written = 0
    upserted_ids = []
    for i in range(0, len(filtered), 500):
        batch = filtered[i:i + 500]
        result = supabase.table("deals").upsert(batch, on_conflict="deal_id").execute()
        written += len(result.data or [])
        upserted_ids.extend(r["id"] for r in (result.data or []) if r.get("id"))
    print(f"  {written} deals upserted")

    # Reset context_stale so run_deals doesn't pick these up
    for i in range(0, len(upserted_ids), 200):
        batch = upserted_ids[i:i + 200]
        supabase.table("deals").update({"context_stale": False}).in_("id", batch).execute()
    print(f"  Reset context_stale on {len(upserted_ids)} deals")

    # Upsert meetings
    total_meetings = sum(len(v) for v in meeting_details.values())
    if total_meetings:
        print(f"  Upserting {total_meetings} meetings ...")
        deal_uuid_map: dict[str, str] = {}
        hs_ids_with_meetings = list(meeting_details.keys())
        for i in range(0, len(hs_ids_with_meetings), 200):
            batch = hs_ids_with_meetings[i:i + 200]
            existing = supabase.table("deals").select("id, deal_id").in_("deal_id", batch).execute()
            for r in (existing.data or []):
                deal_uuid_map[r["deal_id"]] = r["id"]

        meeting_rows = []
        for hs_deal_id, meetings in meeting_details.items():
            deal_uuid = deal_uuid_map.get(hs_deal_id)
            if not deal_uuid:
                continue
            for m in meetings:
                m["deal_id"] = deal_uuid
                if not m.get("hs_deal_id"):
                    m["hs_deal_id"] = hs_deal_id
                meeting_rows.append(m)

        seen_ids = set()
        deduped = []
        for m in meeting_rows:
            mid = m.get("hs_meeting_id")
            if mid and mid not in seen_ids:
                seen_ids.add(mid)
                deduped.append(m)

        for i in range(0, len(deduped), 500):
            batch = deduped[i:i + 500]
            supabase.table("deal_meetings").upsert(batch, on_conflict="hs_meeting_id").execute()
        print(f"  {len(deduped)} meetings upserted (deduped from {len(meeting_rows)})")

    return written


def run_context(team: str, limit: int = 50):
    """Phase 2: Build deal_context for team deals without one."""
    team_cfg = TEAMS.get(team)
    if not team_cfg:
        return

    all_emails = team_cfg.get("pbd", set()) | team_cfg.get("pae", set())
    all_names = set()
    for email in all_emails:
        name = email.split("@")[0].replace(".", " ").title()
        all_names.add(name)

    partner_names = team_cfg.get("partner_names", set())
    stages = list(ACTIVE_STAGES)

    # Get all team deals in active stages, then filter to those needing context
    all_team = []
    for pn in partner_names:
        r = (
            supabase.table("deals")
            .select("id, deal_id, deal_name, deal_stage, atlas_id, crm_id, deal_context")
            .ilike("deal_name", f"%{pn}%")
            .in_("deal_stage", stages)
            .order("amount", desc=True)
            .limit(500)
            .execute()
        )
        all_team.extend(r.data or [])

    seen = set()
    all_team = [d for d in all_team if d["id"] not in seen and not seen.add(d["id"])]

    team_deals = [
        d for d in all_team
        if not d.get("deal_context") or len(d.get("deal_context") or "") < 100
    ][:limit]

    if not team_deals:
        print(f"  No deals without context for {team}")
        return

    print(f"  {len(team_deals)} deals to process")

    ok = 0
    failed = 0
    for i, deal in enumerate(team_deals, 1):
        deal_uuid = deal["id"]
        hs_deal_id = deal["deal_id"]
        print(f"\n  [{i}/{len(team_deals)}] {deal.get('deal_name', '?')[:50]}")

        try:
            if deal.get("atlas_id"):
                atlas_check = (
                    supabase.table("atlas")
                    .select("last_generated")
                    .eq("id", deal["atlas_id"])
                    .maybe_single()
                    .execute()
                )
                if atlas_check.data and atlas_check.data.get("last_generated") is None:
                    print(f"    Generating atlas ...")
                    atlas_generate(deal["atlas_id"], deal.get("crm_id"))

            print(f"    Building context ...")
            sync_deal_context(deal_uuid, hs_deal_id)

            # Audit pending calls
            calls_result = (
                supabase.table("calls")
                .select("id, call_id, rol")
                .eq("deal_id", deal_uuid)
                .not_.is_("transcript", "null")
                .not_.is_("rol", "null")
                .execute()
            )
            for c in (calls_result.data or []):
                audit_table = "pbd_audits" if c["rol"] == "PBD" else "pae_audits"
                existing = (
                    supabase.table(audit_table)
                    .select("win_rate_score")
                    .eq("call_id", c["id"])
                    .not_.is_("win_rate_score", "null")
                    .limit(1)
                    .execute()
                )
                if not existing.data:
                    print(f"    Auditing call {c['call_id']} ...")
                    try:
                        audit_call(c["id"])
                    except Exception as e:
                        print(f"    Audit failed: {e}")

            ok += 1
        except Exception as e:
            failed += 1
            print(f"    FAILED: {e}")
            traceback.print_exc()

    print(f"\n  Context done: {ok} OK, {failed} failed")


def run_snapshot(team: str, limit: int = 50):
    """Phase 3: Generate snapshots for team deals with context."""
    team_cfg = TEAMS.get(team)
    if not team_cfg:
        return

    partner_names = team_cfg.get("partner_names", set())
    stages = list(ACTIVE_STAGES)

    all_team = []
    for pn in partner_names:
        r = (
            supabase.table("deals")
            .select("id, deal_id, deal_name, deal_context")
            .ilike("deal_name", f"%{pn}%")
            .in_("deal_stage", stages)
            .order("amount", desc=True)
            .limit(500)
            .execute()
        )
        all_team.extend(r.data or [])

    seen = set()
    all_team = [d for d in all_team if d["id"] not in seen and not seen.add(d["id"])]

    team_deals = [
        d for d in all_team
        if d.get("deal_context") and len(d["deal_context"]) > 100
    ]

    # Check which already have recent snapshot
    needs_snapshot = []
    for d in team_deals:
        snap = (
            supabase.table("front_deal_snapshots")
            .select("snapshot_date")
            .eq("deal_id", d["id"])
            .order("snapshot_date", desc=True)
            .limit(1)
            .execute()
        )
        if not snap.data:
            needs_snapshot.append(d)

    needs_snapshot = needs_snapshot[:limit]

    if not needs_snapshot:
        print(f"  No deals need snapshots for {team}")
        return

    print(f"  {len(needs_snapshot)} deals to snapshot")

    ok = 0
    failed = 0
    for i, deal in enumerate(needs_snapshot, 1):
        print(f"\n  [{i}/{len(needs_snapshot)}] {deal.get('deal_name', '?')[:50]}")
        try:
            front_deals_snapshot(deal["id"], deal["deal_id"])
            ok += 1
        except Exception as e:
            failed += 1
            print(f"    FAILED: {e}")
            traceback.print_exc()

    print(f"\n  Snapshots done: {ok} OK, {failed} failed")


def run(team: str, phase: str = "all", limit: int = 50):
    print("=" * 60)
    print(f"BACKFILL TEAM — {team} — phase={phase} — limit={limit}")
    print("=" * 60)

    if team not in TEAMS:
        print(f"Unknown team: {team}")
        return

    if phase in ("sync", "all"):
        print(f"\n▸ PHASE: SYNC")
        run_sync(team)

    if phase in ("context", "all"):
        print(f"\n▸ PHASE: CONTEXT")
        run_context(team, limit=limit)

    if phase in ("snapshot", "all"):
        print(f"\n▸ PHASE: SNAPSHOT")
        run_snapshot(team, limit=limit)

    print(f"\n{'=' * 60}")
    print("BACKFILL COMPLETE")
    print("=" * 60)
