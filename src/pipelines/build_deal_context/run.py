"""
Build or update deal_context for a single deal.
Fetches emails/notes from HubSpot, formats them, and appends to existing context.
Triggered by: trg_deal_counts_changed on deals table.
"""

import re

from src.db.client import supabase
from src.integrations import hubspot

EMAIL_PROPS = [
    "hs_timestamp",
    "hs_createdate",
    "hs_email_direction",
    "hs_email_from_email",
    "hs_email_subject",
    "hs_email_text",
    "hs_email_html",
]

NOTE_PROPS = [
    "hs_timestamp",
    "hs_createdate",
    "hs_note_body",
    "hubspot_owner_id",
]

_HTML_TAGS = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\n{3,}")
_CHAIN_MARKERS = re.compile(
    r"(^>+ .+$|^-{3,}.*original message.*$|^-{3,}.*forwarded message.*$"
    r"|^On .{5,100} wrote:$|^El .{5,100} escribió:$"
    r"|^De:.*Enviado:.*Para:.*Asunto:|^From:.*Sent:.*To:.*Subject:)",
    re.IGNORECASE | re.MULTILINE,
)
_SIGNATURE_MARKERS = re.compile(
    r"(^--\s*$|^best regards[,.]?\s*$|^kind regards[,.]?\s*$|^saludos[,.]?\s*$"
    r"|^un saludo[,.]?\s*$|^atentamente[,.]?\s*$|^regards[,.]?\s*$"
    r"|^thanks[,.]?\s*$|^gracias[,.]?\s*$|^cheers[,.]?\s*$)",
    re.IGNORECASE | re.MULTILINE,
)
_ENGAGEMENT_ID_RE = re.compile(r"\[hs:(\d+)\]")


def _clean_email_body(raw: str) -> str:
    if not raw:
        return ""
    text = _HTML_TAGS.sub(" ", raw)
    chain_match = _CHAIN_MARKERS.search(text)
    sig_match = _SIGNATURE_MARKERS.search(text)
    cutoffs = [m.start() for m in [chain_match, sig_match] if m]
    if cutoffs:
        text = text[: min(cutoffs)]
    return _WHITESPACE.sub("\n\n", text).strip()[:4000]


def _strip_html(text: str) -> str:
    clean = _HTML_TAGS.sub("", text)
    clean = clean.replace("&nbsp;", " ").replace("&amp;", "&")
    clean = clean.replace("&lt;", "<").replace("&gt;", ">")
    lines = [line.strip() for line in clean.splitlines()]
    return "\n".join(line for line in lines if line)[:4000]


def _parse_date(raw: str) -> str | None:
    if not raw:
        return None
    return raw.replace("Z", "+00:00") if "T" in raw else None


def _parse_direction(raw: str) -> str:
    if not raw:
        return ""
    return (
        raw.replace("_EMAIL", "")
        .replace("INCOMING", "inbound")
        .replace("OUTGOING", "outbound")
        .lower()
    )


def _format_date(raw: str | None) -> str:
    if not raw:
        return "?"
    return raw[:10] if len(raw) >= 10 else raw


def _existing_engagement_ids(deal_context: str) -> set[str]:
    return set(_ENGAGEMENT_ID_RE.findall(deal_context))


def _fetch_associations(hs_deal_id: str, object_type: str) -> list[str]:
    ids: list[str] = []
    after = None
    while True:
        url = f"/crm/v4/objects/deals/{hs_deal_id}/associations/{object_type}"
        params = {"limit": "500"}
        if after:
            params["after"] = after
        data = hubspot.get(url, params)
        for item in data.get("results", []):
            oid = str(item.get("toObjectId", ""))
            if oid:
                ids.append(oid)
        after = data.get("paging", {}).get("next", {}).get("after")
        if not after:
            break
    return ids


def _batch_read(object_type: str, ids: list[str], properties: list[str]) -> list[dict]:
    results: list[dict] = []
    for i in range(0, len(ids), 100):
        batch = ids[i : i + 100]
        data = hubspot.post(
            f"/crm/v3/objects/{object_type}/batch/read",
            {"inputs": [{"id": oid} for oid in batch], "properties": properties},
        )
        results.extend(data.get("results", []))
    return results


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


def _format_email(hs_id: str, p: dict) -> str:
    fecha = _format_date(p.get("hs_timestamp") or p.get("hs_createdate"))
    direction = _parse_direction(p.get("hs_email_direction")).upper()
    subject = p.get("hs_email_subject") or "—"
    body_raw = p.get("hs_email_text") or p.get("hs_email_html") or ""
    body_clean = _clean_email_body(body_raw)
    body_display = body_clean if body_clean else "(sin contenido)"
    return f"[{fecha}] EMAIL {direction} [hs:{hs_id}] — {subject}\n  {body_display}"


def _format_note(hs_id: str, p: dict, owners: dict) -> str:
    fecha = _format_date(p.get("hs_timestamp") or p.get("hs_createdate"))
    owner_id = p.get("hubspot_owner_id") or ""
    author = owners.get(owner_id, "?")
    content = _strip_html(p.get("hs_note_body") or "")[:300]
    return f"[{fecha}] NOTE [hs:{hs_id}] — {author}\n  {content}"


def _build_new_entries(
    hs_deal_id: str,
    existing_ids: set[str],
    context_type: str,
    owners: dict | None = None,
) -> list[tuple[str, str]]:
    """Returns list of (sort_date, formatted_entry) for new interactions."""
    entries: list[tuple[str, str]] = []

    if context_type == "emails":
        all_ids = _fetch_associations(hs_deal_id, "emails")
        new_ids = [eid for eid in all_ids if eid not in existing_ids]
        if not new_ids:
            return entries
        objects = _batch_read("emails", new_ids, EMAIL_PROPS)
        for obj in objects:
            p = obj.get("properties", {})
            hs_id = str(obj.get("id", ""))
            date = p.get("hs_timestamp") or p.get("hs_createdate") or ""
            entries.append((date, _format_email(hs_id, p)))

    elif context_type == "notes":
        if owners is None:
            owners = _fetch_owners()
        all_ids = _fetch_associations(hs_deal_id, "notes")
        new_ids = [nid for nid in all_ids if nid not in existing_ids]
        if not new_ids:
            return entries
        objects = _batch_read("notes", new_ids, NOTE_PROPS)
        for obj in objects:
            p = obj.get("properties", {})
            hs_id = str(obj.get("id", ""))
            content = p.get("hs_note_body") or ""
            if not content.strip():
                entries.append((
                    p.get("hs_timestamp") or p.get("hs_createdate") or "",
                    f"[{_format_date(p.get('hs_timestamp') or p.get('hs_createdate'))}] NOTE [hs:{hs_id}] — (sin contenido)",
                ))
                continue
            date = p.get("hs_timestamp") or p.get("hs_createdate") or ""
            entries.append((date, _format_note(hs_id, p, owners)))

    entries.sort(key=lambda x: x[0])
    return entries


def _build_atlas_header(deal_uuid: str) -> str:
    deal = (
        supabase.table("deals")
        .select("atlas_id, atlas:atlas_id(company_name, company_context, deal_history, contacts_map)")
        .eq("id", deal_uuid)
        .maybe_single()
        .execute()
    )
    if not deal.data:
        return ""

    atlas = deal.data.get("atlas") or {}
    parts = []

    company_name = atlas.get("company_name") or ""
    if company_name:
        parts.append(f"=== ATLAS: {company_name} ===")

    if atlas.get("company_context"):
        parts.append(atlas["company_context"])

    if atlas.get("deal_history"):
        parts += ["", "--- PRIOR DEALS ---", atlas["deal_history"]]

    if atlas.get("contacts_map"):
        parts += ["", "--- CONTACTS MAP ---", atlas["contacts_map"]]

    if parts:
        parts.append("\n=== INTERACCIONES ===")

    return "\n".join(parts)


def run(deal_uuid: str, hs_deal_id: str, context_type: str = "all"):
    print(f"1. Reading current deal_context for deal {deal_uuid} ...")
    deal_result = (
        supabase.table("deals")
        .select("deal_context")
        .eq("id", deal_uuid)
        .maybe_single()
        .execute()
    )
    if not deal_result.data:
        print(f"   Deal {deal_uuid} not found — skipping.")
        return

    current_context = deal_result.data.get("deal_context") or ""

    # First time building context: prepend atlas header
    if not current_context.strip():
        atlas_header = _build_atlas_header(deal_uuid)
        if atlas_header:
            current_context = atlas_header
            print(f"   Atlas header added ({len(atlas_header)} chars)")

    existing_ids = _existing_engagement_ids(current_context)
    print(f"   Current context: {len(current_context)} chars, {len(existing_ids)} tracked IDs")

    owners = None
    types_to_process = []
    if context_type == "all":
        types_to_process = ["emails", "notes"]
    else:
        types_to_process = [context_type]

    all_new_entries: list[tuple[str, str]] = []

    for ctype in types_to_process:
        print(f"2. Fetching new {ctype} from HubSpot ...")
        if ctype == "notes" and owners is None:
            owners = _fetch_owners()
        entries = _build_new_entries(hs_deal_id, existing_ids, ctype, owners)
        print(f"   {len(entries)} new {ctype} found")
        all_new_entries.extend(entries)

    if not all_new_entries:
        print("   No new interactions — updating deal_context to mark complete.")
        supabase.table("deals").update(
            {"deal_context": current_context or " "}
        ).eq("id", deal_uuid).execute()
        return

    all_new_entries.sort(key=lambda x: x[0])
    new_block = "\n\n".join(entry for _, entry in all_new_entries)

    if current_context:
        updated_context = current_context + "\n\n" + new_block
    else:
        updated_context = new_block

    print(f"3. Updating deal_context ({len(updated_context)} chars) ...")
    supabase.table("deals").update(
        {"deal_context": updated_context}
    ).eq("id", deal_uuid).execute()

    print(f"   Done. Added {len(all_new_entries)} interactions.")
    print(f"   HubSpot API requests: {hubspot.total_requests()}")
