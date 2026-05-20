"""
Discover all Santander / Telefonica deal IDs from HubSpot.

Three complementary sources are unioned:
  S1  dealname CONTAINS_TOKEN santander | telefonica
  S2  partner_name = Santander | Telefonica
  S3  current_hubspot_team__string_ = Partners - PAE ES Santander | Telefonica
"""

from src.integrations import hubspot

SEARCH_URL = "/crm/v3/objects/deals/search"

_PARTNER_NAMES = ["Santander", "Telefónica", "Telefonica"]
_TEAM_VALUES = [
    "Partners - PAE ES Santander",
    "Partners - PAE ES Telefónica",
    "Partners - PAE ES Telefonica",
    "Partners - PAE ES",
]
_DEALNAME_TOKENS = ["santander", "telefonica", "telefónica"]


def _search_all(filter_groups: list[dict]) -> set[str]:
    ids: set[str] = set()
    after = None
    while True:
        body: dict = {
            "filterGroups": filter_groups,
            "properties": ["hs_object_id"],
            "limit": 100,
        }
        if after:
            body["after"] = after
        data = hubspot.post(SEARCH_URL, body)
        for r in data.get("results", []):
            ids.add(r["id"])
        after = data.get("paging", {}).get("next", {}).get("after")
        if not after:
            break
    return ids


def _search_by_dealname() -> set[str]:
    return _search_all([
        {"filters": [{"propertyName": "dealname", "operator": "CONTAINS_TOKEN", "value": t}]}
        for t in _DEALNAME_TOKENS
    ])


def _search_by_partner_name() -> set[str]:
    return _search_all([
        {"filters": [{"propertyName": "partner_name", "operator": "EQ", "value": p}]}
        for p in _PARTNER_NAMES
    ])


def _search_by_team(team: str) -> set[str]:
    return _search_all([
        {"filters": [{"propertyName": "current_hubspot_team__string_", "operator": "EQ", "value": team}]},
    ])


def find_all_deal_ids() -> set[str]:
    print("  S1: searching by dealname ...")
    s1 = _search_by_dealname()
    print(f"      {len(s1)} deals")

    print("  S2: searching by partner_name ...")
    s2 = _search_by_partner_name()
    print(f"      {len(s2)} deals")

    s3: set[str] = set()
    for team in _TEAM_VALUES:
        print(f"  S3: searching by team '{team}' ...")
        batch = _search_by_team(team)
        print(f"      {len(batch)} deals")
        s3 |= batch

    union = s1 | s2 | s3
    print(f"  Union: {len(union)} unique deals")
    return union


def find_modified_deal_ids(since_ms: int) -> set[str]:
    """Same 3 sources but filtered by hs_lastmodifieddate >= since_ms."""
    mod_filter = {
        "propertyName": "hs_lastmodifieddate",
        "operator": "GTE",
        "value": str(since_ms),
    }

    print("  S1: searching by dealname (incremental) ...")
    s1 = _search_all([
        {"filters": [{"propertyName": "dealname", "operator": "CONTAINS_TOKEN", "value": t}, mod_filter]}
        for t in _DEALNAME_TOKENS
    ])
    print(f"      {len(s1)} deals")

    print("  S2: searching by partner_name (incremental) ...")
    s2 = _search_all([
        {"filters": [{"propertyName": "partner_name", "operator": "EQ", "value": p}, mod_filter]}
        for p in _PARTNER_NAMES
    ])
    print(f"      {len(s2)} deals")

    s3: set[str] = set()
    for team in _TEAM_VALUES:
        print(f"  S3: searching by team '{team}' (incremental) ...")
        batch = _search_all([
            {"filters": [
                {"propertyName": "current_hubspot_team__string_", "operator": "EQ", "value": team},
                mod_filter,
            ]},
        ])
        print(f"      {len(batch)} deals")
        s3 |= batch

    union = s1 | s2 | s3
    print(f"  Union (incremental): {len(union)} unique deals")
    return union
