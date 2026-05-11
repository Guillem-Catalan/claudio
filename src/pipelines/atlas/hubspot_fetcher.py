"""
Fetch company info, deals, and contacts from HubSpot for atlas generation.
"""

from src.integrations import hubspot

COMPANY_PROPS = [
    "name",
    "industry",
    "numberofemployees",
    "country",
    "website",
    "description",
    "city",
    "state",
    "annualrevenue",
]

DEAL_PROPS = [
    "dealname",
    "dealstage",
    "amount",
    "closedate",
    "createdate",
    "hs_manual_forecast_category",
    "hubspot_owner_id",
    "hs_lastmodifieddate",
    "hs_is_closed_won",
    "hs_is_closed",
]

CONTACT_PROPS = [
    "firstname",
    "lastname",
    "email",
    "jobtitle",
    "phone",
]


def fetch_company(crm_id: str) -> dict:
    data = hubspot.get(f"/crm/v3/objects/companies/{crm_id}", {"properties": ",".join(COMPANY_PROPS)})
    return data.get("properties", {})


def fetch_deal_ids(crm_id: str) -> list[str]:
    deal_ids: list[str] = []
    after = None
    while True:
        url = f"/crm/v4/objects/companies/{crm_id}/associations/deals"
        params = {"limit": "500"}
        if after:
            params["after"] = after
        data = hubspot.get(url, params)
        for item in data.get("results", []):
            did = str(item.get("toObjectId", ""))
            if did:
                deal_ids.append(did)
        after = data.get("paging", {}).get("next", {}).get("after")
        if not after:
            break
    return deal_ids


def fetch_deal_properties(deal_ids: list[str], owners: dict[str, str]) -> list[dict]:
    results: list[dict] = []
    for i in range(0, len(deal_ids), 100):
        batch = deal_ids[i : i + 100]
        data = hubspot.post(
            "/crm/v3/objects/deals/batch/read",
            {"inputs": [{"id": did} for did in batch], "properties": DEAL_PROPS},
        )
        for obj in data.get("results", []):
            p = obj.get("properties", {})
            owner_id = p.get("hubspot_owner_id") or ""
            results.append({
                "deal_id": obj["id"],
                "name": p.get("dealname") or "",
                "stage": p.get("dealstage") or "",
                "amount": p.get("amount") or "",
                "close_date": (p.get("closedate") or "")[:10],
                "create_date": (p.get("createdate") or "")[:10],
                "forecast_category": p.get("hs_manual_forecast_category") or "",
                "owner": owners.get(owner_id, ""),
                "is_closed": p.get("hs_is_closed") or "false",
                "is_closed_won": p.get("hs_is_closed_won") or "false",
            })
    return results


def fetch_contact_ids(crm_id: str) -> list[str]:
    contact_ids: list[str] = []
    after = None
    while True:
        url = f"/crm/v4/objects/companies/{crm_id}/associations/contacts"
        params = {"limit": "500"}
        if after:
            params["after"] = after
        data = hubspot.get(url, params)
        for item in data.get("results", []):
            cid = str(item.get("toObjectId", ""))
            if cid:
                contact_ids.append(cid)
        after = data.get("paging", {}).get("next", {}).get("after")
        if not after:
            break
    return contact_ids


def fetch_contact_properties(contact_ids: list[str]) -> list[dict]:
    results: list[dict] = []
    for i in range(0, len(contact_ids), 100):
        batch = contact_ids[i : i + 100]
        data = hubspot.post(
            "/crm/v3/objects/contacts/batch/read",
            {"inputs": [{"id": cid} for cid in batch], "properties": CONTACT_PROPS},
        )
        for obj in data.get("results", []):
            p = obj.get("properties", {})
            first = p.get("firstname") or ""
            last = p.get("lastname") or ""
            name = f"{first} {last}".strip() or "(sin nombre)"
            results.append({
                "contact_id": obj["id"],
                "name": name,
                "email": p.get("email") or "",
                "jobtitle": p.get("jobtitle") or "",
                "phone": p.get("phone") or "",
            })
    return results


def fetch_owners() -> dict[str, str]:
    owners: dict[str, str] = {}
    url = "/crm/v3/owners?limit=100"
    while url:
        data = hubspot.get(url)
        for o in data.get("results", []):
            first = o.get("firstName") or ""
            last = o.get("lastName") or ""
            name = f"{first} {last}".strip() or o.get("email", "")
            owners[o["id"]] = name
        next_link = data.get("paging", {}).get("next", {}).get("link")
        if next_link:
            url = next_link.replace(hubspot.BASE, "")
        else:
            url = ""
    return owners
