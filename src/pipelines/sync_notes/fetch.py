"""
Fetch all notes for a single deal from HubSpot and upsert to Supabase.
Triggered by: trg_deal_notes_changed on deals table.
"""

from src.db.client import supabase
from src.integrations import hubspot

NOTE_PROPS = [
    "hs_timestamp",
    "hs_createdate",
    "hs_note_body",
    "hubspot_owner_id",
]


def _fetch_note_ids_for_deal(hs_deal_id: str) -> list[str]:
    note_ids: list[str] = []
    after = None
    while True:
        url = f"/crm/v4/objects/deals/{hs_deal_id}/associations/notes"
        params = {"limit": "500"}
        if after:
            params["after"] = after
        data = hubspot.get(url, params)
        for item in data.get("results", []):
            nid = str(item.get("toObjectId", ""))
            if nid:
                note_ids.append(nid)
        after = data.get("paging", {}).get("next", {}).get("after")
        if not after:
            break
    return note_ids


def _fetch_note_properties(note_ids: list[str]) -> list[dict]:
    results: list[dict] = []
    for i in range(0, len(note_ids), 100):
        batch = note_ids[i : i + 100]
        data = hubspot.post(
            "/crm/v3/objects/notes/batch/read",
            {"inputs": [{"id": nid} for nid in batch], "properties": NOTE_PROPS},
        )
        results.extend(data.get("results", []))
    return results


def _existing_engagement_ids(hs_deal_id: str) -> set[str]:
    result = (
        supabase.table("notes")
        .select("hs_engagement_id")
        .eq("hs_deal_id", hs_deal_id)
        .execute()
    )
    return {r["hs_engagement_id"] for r in (result.data or [])}


def _fetch_owners() -> dict[str, str]:
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


def _parse_date(raw: str) -> str | None:
    if not raw:
        return None
    return raw.replace("Z", "+00:00") if "T" in raw else None


def run(deal_uuid: str, hs_deal_id: str):
    print(f"1. Fetching note associations for deal {hs_deal_id} ...")
    note_ids = _fetch_note_ids_for_deal(hs_deal_id)
    print(f"   {len(note_ids)} notes found in HubSpot")

    if not note_ids:
        print("   No notes — done.")
        return

    print("2. Checking existing notes in Supabase ...")
    existing = _existing_engagement_ids(hs_deal_id)
    new_ids = [nid for nid in note_ids if nid not in existing]
    print(f"   {len(existing)} existing, {len(new_ids)} new")

    if not new_ids:
        print("   All notes already synced — done.")
        return

    print(f"3. Fetching properties for {len(new_ids)} new notes ...")
    note_objects = _fetch_note_properties(new_ids)
    print(f"   {len(note_objects)} objects returned")

    print("4. Fetching owners ...")
    owners = _fetch_owners()

    deal_result = (
        supabase.table("deals")
        .select("crm_id")
        .eq("id", deal_uuid)
        .maybe_single()
        .execute()
    )
    crm_id = deal_result.data["crm_id"] if deal_result.data else None

    print("5. Upserting to Supabase ...")
    rows = []
    for obj in note_objects:
        p = obj.get("properties", {})
        hs_id = str(obj.get("id", ""))
        content = p.get("hs_note_body") or ""
        if not content.strip():
            continue

        owner_id = p.get("hubspot_owner_id") or ""
        owner_name = owners.get(owner_id, "")

        rows.append({
            "hs_engagement_id": hs_id,
            "deal_id": deal_uuid,
            "hs_deal_id": hs_deal_id,
            "crm_id": crm_id,
            "date": _parse_date(p.get("hs_timestamp") or p.get("hs_createdate")),
            "owner": owner_name,
            "content": content[:50000],
        })

    if rows:
        result = (
            supabase.table("notes")
            .upsert(rows, on_conflict="hs_engagement_id")
            .execute()
        )
        print(f"   {len(result.data)} notes upserted")
    else:
        print("   No notes with content to write")

    print(f"   HubSpot API requests: {hubspot.total_requests()}")
