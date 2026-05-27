"""
Batch-read deal properties, associations and engagement counts from HubSpot.
"""

from datetime import datetime, timezone

from src.integrations import hubspot

# ── HubSpot property → Supabase column mapping ─────────────────────────────

CORE_PROPS = [
    "dealname",
    "amount",
    "dealstage",
    "hs_manual_forecast_category",
    "closedate",
    "createdate",
    "hs_lastmodifieddate",
    "notes_last_contacted",
    "num_associated_contacts",
    "hs_next_step",
    "hs_forecast_probability",
    "hs_deal_stage_probability",
    "hubspot_owner_id",
    "partner_name",
    "first_meeting_at",
    "hs_next_meeting_start_time",
]

PIPELINE_DATE_MAP: dict[str, str] = {
    # SDR Partner Opportunities Pipeline
    "hs_v2_date_entered_1002830265": "sdr_prequalified_entered",
    "hs_v2_date_exited_1002830265": "sdr_prequalified_exited",
    "hs_v2_date_entered_1002830336": "sdr_attempting_to_contact_entered",
    "hs_v2_date_exited_1002830336": "sdr_attempting_to_contact_exited",
    "hs_v2_date_entered_1002830337": "sdr_associating_the_partner_entered",
    "hs_v2_date_exited_1002830337": "sdr_associating_the_partner_exited",
    "hs_v2_date_entered_1002830338": "sdr_engaged_entered",
    "hs_v2_date_exited_1002830338": "sdr_engaged_exited",
    "hs_v2_date_entered_1002830339": "sdr_demo_booked_entered",
    "hs_v2_date_exited_1002830339": "sdr_demo_booked_exited",
    "hs_v2_date_entered_1002830340": "sdr_nurturing_entered",
    "hs_v2_date_exited_1002830340": "sdr_nurturing_exited",
    "hs_v2_date_entered_1002830341": "sdr_opportunity_lost_entered",
    "hs_v2_date_exited_1002830341": "sdr_opportunity_lost_exited",
    "hs_v2_date_entered_1002829480": "sdr_to_reschedule_entered",
    "hs_v2_date_exited_1002829480": "sdr_to_reschedule_exited",
    # Partners Distribution Pipeline
    "hs_v2_date_entered_35070729": "dist_new_deals_entered",
    "hs_v2_date_exited_35070729": "dist_new_deals_exited",
    "hs_v2_date_entered_35070730": "dist_demo_booked_entered",
    "hs_v2_date_exited_35070730": "dist_demo_booked_exited",
    "hs_v2_date_entered_35070731": "dist_product_alignment_entered",
    "hs_v2_date_exited_35070731": "dist_product_alignment_exited",
    "hs_v2_date_entered_35070732": "dist_do_not_use_entered",
    "hs_v2_date_exited_35070732": "dist_do_not_use_exited",
    "hs_v2_date_entered_35118878": "dist_pricing_and_packaging_entered",
    "hs_v2_date_exited_35118878": "dist_pricing_and_packaging_exited",
    "hs_v2_date_entered_35118879": "dist_contracting_entered",
    "hs_v2_date_exited_35118879": "dist_contracting_exited",
    "hs_v2_date_entered_104503991": "dist_closed_pending_payment_entered",
    "hs_v2_date_exited_104503991": "dist_closed_pending_payment_exited",
    "hs_v2_date_entered_35118880": "dist_closed_won_entered",
    "hs_v2_date_exited_35118880": "dist_closed_won_exited",
    "hs_v2_date_entered_1008401982": "dist_on_hold_entered",
    "hs_v2_date_exited_1008401982": "dist_on_hold_exited",
    "hs_v2_date_entered_35119283": "dist_closed_lost_entered",
    "hs_v2_date_exited_35119283": "dist_closed_lost_exited",
    "hs_v2_date_entered_4977567965": "dist_to_reschedule_entered",
    "hs_v2_date_exited_4977567965": "dist_to_reschedule_exited",
    "hs_v2_date_entered_5366023400": "dist_meddpicc_validation_entered",
    "hs_v2_date_exited_5366023400": "dist_meddpicc_validation_exited",
    # Sales Pipeline
    "hs_v2_date_entered_96e820da_7bc1_4ea3_81a2_bc533ed26934_2127198906": "sales_meeting_booked_entered",
    "hs_v2_date_exited_96e820da_7bc1_4ea3_81a2_bc533ed26934_2127198906": "sales_meeting_booked_exited",
    "hs_v2_date_entered_49b7ad85_a23e_426c_9b3b_d44607d1c3af_2009251351": "sales_discovery_entered",
    "hs_v2_date_exited_49b7ad85_a23e_426c_9b3b_d44607d1c3af_2009251351": "sales_discovery_exited",
    "hs_v2_date_entered_f26b487d_e715_49c8_add3_9fa86aef79da_127692047": "sales_to_reschedule_entered",
    "hs_v2_date_exited_f26b487d_e715_49c8_add3_9fa86aef79da_127692047": "sales_to_reschedule_exited",
    "hs_v2_date_entered_appointmentscheduled": "sales_product_alignment_entered",
    "hs_v2_date_exited_appointmentscheduled": "sales_product_alignment_exited",
    "hs_v2_date_entered_qualifiedtobuy": "sales_pricing_and_packaging_entered",
    "hs_v2_date_exited_qualifiedtobuy": "sales_pricing_and_packaging_exited",
    "hs_v2_date_entered_15738025": "sales_contracting_entered",
    "hs_v2_date_exited_15738025": "sales_contracting_exited",
    "hs_v2_date_entered_51389338": "sales_closed_pending_payment_entered",
    "hs_v2_date_exited_51389338": "sales_closed_pending_payment_exited",
    "hs_v2_date_entered_closedwon": "sales_closed_won_entered",
    "hs_v2_date_exited_closedwon": "sales_closed_won_exited",
    "hs_v2_date_entered_closedlost": "sales_closed_lost_entered",
    "hs_v2_date_exited_closedlost": "sales_closed_lost_exited",
}

ALL_PROPS = CORE_PROPS + list(PIPELINE_DATE_MAP.keys())


# ── Pipeline stages ─────────────────────────────────────────────────────────

def fetch_pipeline_stages() -> dict[str, str]:
    data = hubspot.get("/crm/v3/pipelines/deals")
    stages: dict[str, str] = {}
    for pipeline in data.get("results", []):
        for stage in pipeline.get("stages", []):
            stages[stage["id"]] = stage["label"]
    return stages


# ── Owners ──────────────────────────────────────────────────────────────────

def fetch_owners() -> dict[str, dict]:
    owners: dict[str, dict] = {}
    url = "/crm/v3/owners?limit=100"
    while url:
        data = hubspot.get(url)
        for o in data.get("results", []):
            first = o.get("firstName") or ""
            last = o.get("lastName") or ""
            name = f"{first} {last}".strip() or o.get("email", "")
            owners[o["id"]] = {"name": name, "email": (o.get("email") or "").lower()}
        next_link = data.get("paging", {}).get("next", {}).get("link")
        if next_link:
            url = next_link.replace(hubspot.BASE, "")
        else:
            url = ""
    return owners


# ── Batch read deal properties ──────────────────────────────────────────────

def _to_date(val: str | None) -> str | None:
    if not val:
        return None
    if val.isdigit():
        ts = int(val)
        if ts > 1e12:
            ts = ts / 1000
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        except (ValueError, OSError):
            return None
    return val[:10]


def fetch_deal_properties(deal_ids: list[str], stages: dict[str, str]) -> list[dict]:
    deals = []
    today = datetime.now(timezone.utc).date()

    for i in range(0, len(deal_ids), 100):
        batch = deal_ids[i : i + 100]
        data = hubspot.post(
            "/crm/v3/objects/deals/batch/read",
            {"inputs": [{"id": did} for did in batch], "properties": ALL_PROPS},
        )
        for result in data.get("results", []):
            p = result.get("properties", {})

            create_date = _to_date(p.get("createdate"))
            deal_age_days = None
            if create_date:
                try:
                    deal_age_days = (today - datetime.fromisoformat(create_date).date()).days
                except Exception:
                    pass

            rep_prob = p.get("hs_forecast_probability")
            stage_prob = p.get("hs_deal_stage_probability")
            stage_id = p.get("dealstage", "")

            row: dict = {
                "deal_id": result["id"],
                "deal_name": p.get("dealname") or "",
                "amount": float(p["amount"]) if p.get("amount") else None,
                "deal_stage": stages.get(stage_id, stage_id),
                "forecast_category": p.get("hs_manual_forecast_category") or "",
                "close_date": _to_date(p.get("closedate")),
                "createdate": create_date,
                "deal_age_days": deal_age_days,
                "last_hs_modified": _to_date(p.get("hs_lastmodifieddate")),
                "last_contacted_hs": _to_date(p.get("notes_last_contacted")),
                "contact_count": int(p["num_associated_contacts"]) if p.get("num_associated_contacts") else 0,
                "rep_next_step": p.get("hs_next_step") or "",
                "rep_probability": float(rep_prob) if rep_prob else None,
                "stage_probability_hs": float(stage_prob) if stage_prob else None,
                "_owner_id": p.get("hubspot_owner_id") or "",
                "_partner_name": p.get("partner_name") or "",
                "first_meeting_at": _to_date(p.get("first_meeting_at")),
                "hs_next_meeting_start_time": _to_date(p.get("hs_next_meeting_start_time")),
            }

            for hs_prop, col in PIPELINE_DATE_MAP.items():
                row[col] = _to_date(p.get(hs_prop))

            deals.append(row)

    return deals


# ── Associations ────────────────────────────────────────────────────────────

def _batch_associations(deal_ids: list[str], to_object: str) -> dict[str, list[str]]:
    result_map: dict[str, list[str]] = {}
    for i in range(0, len(deal_ids), 100):
        batch = deal_ids[i : i + 100]
        data = hubspot.post(
            f"/crm/v4/associations/deals/{to_object}/batch/read",
            {"inputs": [{"id": did} for did in batch]},
        )
        for item in data.get("results", []):
            deal_id = str(item.get("from", {}).get("id", ""))
            to_ids = [str(c.get("toObjectId", "")) for c in item.get("to", [])]
            if to_ids:
                result_map[deal_id] = to_ids
    return result_map


def fetch_company_associations(deal_ids: list[str]) -> dict[str, str]:
    raw = _batch_associations(deal_ids, "companies")
    return {did: ids[0] for did, ids in raw.items()}


def fetch_contact_associations(deal_ids: list[str]) -> dict[str, list[str]]:
    return _batch_associations(deal_ids, "contacts")


# ── Engagement counts ───────────────────────────────────────────────────────

def _count_associations(deal_ids: list[str], to_object: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for i in range(0, len(deal_ids), 100):
        batch = deal_ids[i : i + 100]
        data = hubspot.post(
            f"/crm/v4/associations/deals/{to_object}/batch/read",
            {"inputs": [{"id": did} for did in batch]},
        )
        for item in data.get("results", []):
            deal_id = str(item.get("from", {}).get("id", ""))
            counts[deal_id] = len(item.get("to", []))
    return counts


def fetch_engagement_counts(deal_ids: list[str]) -> dict[str, dict[str, int]]:
    print("    counting notes ...")
    notes = _count_associations(deal_ids, "notes")
    print("    counting emails ...")
    emails = _count_associations(deal_ids, "emails")
    print("    counting calls ...")
    calls = _count_associations(deal_ids, "calls")
    print("    counting meetings ...")
    meetings = _count_associations(deal_ids, "meetings")
    return {
        did: {
            "numero_de_notas": notes.get(did, 0),
            "numero_de_emails": emails.get(did, 0),
            "numero_de_calls": calls.get(did, 0),
            "numero_de_meetings": meetings.get(did, 0),
        }
        for did in deal_ids
    }


# ── Contacts info ───────────────────────────────────────────────────────────

def fetch_contacts_info(contact_ids: list[str]) -> dict[str, dict]:
    contacts: dict[str, dict] = {}
    props = ["firstname", "lastname", "email", "jobtitle"]

    for i in range(0, len(contact_ids), 100):
        batch = contact_ids[i : i + 100]
        data = hubspot.post(
            "/crm/v3/objects/contacts/batch/read",
            {"inputs": [{"id": cid} for cid in batch], "properties": props},
        )
        for result in data.get("results", []):
            p = result.get("properties", {})
            first = p.get("firstname") or ""
            last = p.get("lastname") or ""
            name = f"{first} {last}".strip() or "(sin nombre)"
            contacts[result["id"]] = {
                "name": name,
                "email": p.get("email") or "",
                "jobtitle": p.get("jobtitle") or "",
            }
    return contacts


MEETING_PROPS = [
    "hs_meeting_start_time",
    "hs_meeting_end_time",
    "hs_meeting_title",
    "hs_meeting_outcome",
]


def fetch_meeting_details(deal_ids: list[str]) -> dict[str, list[dict]]:
    """Fetch meeting associations per deal, then batch-read meeting properties."""
    print("    fetching meeting associations ...")
    meeting_assocs = _batch_associations(deal_ids, "meetings")

    all_meeting_ids = list({mid for mids in meeting_assocs.values() for mid in mids})
    if not all_meeting_ids:
        return {}

    print(f"    reading properties for {len(all_meeting_ids)} meetings ...")
    meetings_by_id: dict[str, dict] = {}
    for i in range(0, len(all_meeting_ids), 100):
        batch = all_meeting_ids[i : i + 100]
        data = hubspot.post(
            "/crm/v3/objects/meetings/batch/read",
            {"inputs": [{"id": mid} for mid in batch], "properties": MEETING_PROPS},
        )
        for result in data.get("results", []):
            p = result.get("properties", {})
            meetings_by_id[result["id"]] = {
                "hs_meeting_id": result["id"],
                "meeting_start": p.get("hs_meeting_start_time"),
                "meeting_end": p.get("hs_meeting_end_time"),
                "title": p.get("hs_meeting_title") or "",
                "outcome": p.get("hs_meeting_outcome") or "SCHEDULED",
            }

    result: dict[str, list[dict]] = {}
    for did, meeting_ids in meeting_assocs.items():
        result[did] = [meetings_by_id[mid] for mid in meeting_ids if mid in meetings_by_id]
    return result


def format_contacts_info(contact_ids: list[str], contacts: dict[str, dict]) -> str:
    if not contact_ids:
        return ""
    lines = []
    for cid in contact_ids:
        c = contacts.get(cid)
        if not c:
            continue
        parts = [c["name"]]
        if c["jobtitle"]:
            parts.append(c["jobtitle"])
        if c["email"]:
            parts.append(c["email"])
        lines.append(" | ".join(parts))
    return "\n".join(lines)
