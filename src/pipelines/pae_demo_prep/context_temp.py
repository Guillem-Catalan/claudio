"""
Temporary fallback: build deal context from HubSpot when deal_context is empty.
Will stop being called once sync_deal_context backfill populates the column.
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
CALL_PROPS = [
    "hs_timestamp",
    "hs_call_body",
    "hs_call_duration",
    "hs_call_title",
    "hubspot_owner_id",
]

_HTML_RE = re.compile(r"<[^>]+>")
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


def _strip_html(text: str) -> str:
    clean = _HTML_RE.sub("", text)
    clean = clean.replace("&nbsp;", " ").replace("&amp;", "&")
    clean = clean.replace("&lt;", "<").replace("&gt;", ">")
    lines = [line.strip() for line in clean.splitlines()]
    return "\n".join(line for line in lines if line)[:4000]


def _clean_email_body(raw: str) -> str:
    if not raw:
        return ""
    text = _HTML_RE.sub(" ", raw)
    chain_match = _CHAIN_MARKERS.search(text)
    sig_match = _SIGNATURE_MARKERS.search(text)
    cutoffs = [m.start() for m in [chain_match, sig_match] if m]
    if cutoffs:
        text = text[: min(cutoffs)]
    return _WHITESPACE.sub("\n\n", text).strip()[:4000]


def _format_date(raw: str | None) -> str:
    if not raw:
        return "?"
    return raw[:10] if len(raw) >= 10 else raw


def _parse_direction(raw: str) -> str:
    if not raw:
        return ""
    return (
        raw.replace("_EMAIL", "")
        .replace("INCOMING", "inbound")
        .replace("OUTGOING", "outbound")
        .lower()
    )


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


def _fetch_owners() -> dict[str, dict]:
    owners: dict[str, dict] = {}
    url = "/crm/v3/owners?limit=100"
    while True:
        data = hubspot.get(url)
        for o in data.get("results", []):
            first = o.get("firstName") or ""
            last = o.get("lastName") or ""
            name = f"{first} {last}".strip() or o.get("email", "")
            owners[o["id"]] = {"name": name, "email": o.get("email", "")}
        next_link = data.get("paging", {}).get("next", {}).get("link")
        if next_link:
            url = next_link.replace(hubspot.BASE, "")
        else:
            break
    return owners


def build_context_from_hubspot(deal_uuid: str) -> str:
    """Fetch emails, notes, calls from HubSpot and build context text."""

    deal = (
        supabase.table("deals")
        .select("hs_deal_id, atlas:atlas_id(company_name, company_context, deal_history, contacts_map)")
        .eq("id", deal_uuid)
        .maybe_single()
        .execute()
    )
    if not deal.data or not deal.data.get("hs_deal_id"):
        return "No interactions recorded."

    hs_deal_id = deal.data["hs_deal_id"]
    atlas = deal.data.get("atlas") or {}

    parts: list[str] = []

    if atlas.get("company_context"):
        parts.append(f"=== ATLAS: {atlas.get('company_name', '')} ===")
        parts.append(atlas["company_context"])
    if atlas.get("deal_history"):
        parts += ["", "--- PRIOR DEALS ---", atlas["deal_history"]]
    if atlas.get("contacts_map"):
        parts += ["", "--- CONTACTS MAP ---", atlas["contacts_map"]]

    print("   [temp] Fetching from HubSpot ...")
    owners = _fetch_owners()
    items: list[tuple[str, str]] = []

    email_ids = _fetch_associations(hs_deal_id, "emails")
    if email_ids:
        for obj in _batch_read("emails", email_ids, EMAIL_PROPS):
            p = obj.get("properties", {})
            hs_id = str(obj.get("id", ""))
            fecha = _format_date(p.get("hs_timestamp") or p.get("hs_createdate"))
            direction = _parse_direction(p.get("hs_email_direction")).upper()
            subject = p.get("hs_email_subject") or "—"
            body_raw = p.get("hs_email_text") or p.get("hs_email_html") or ""
            body_clean = _clean_email_body(body_raw)
            date_sort = p.get("hs_timestamp") or p.get("hs_createdate") or ""
            items.append((date_sort, f"[{fecha}] EMAIL {direction} — {subject}\n  {body_clean or '(sin contenido)'}"))
    print(f"   [temp] {len(email_ids)} emails")

    note_ids = _fetch_associations(hs_deal_id, "notes")
    if note_ids:
        for obj in _batch_read("notes", note_ids, NOTE_PROPS):
            p = obj.get("properties", {})
            fecha = _format_date(p.get("hs_timestamp") or p.get("hs_createdate"))
            owner_id = p.get("hubspot_owner_id") or ""
            owner_info = owners.get(owner_id, {})
            author = owner_info.get("name", "?") if isinstance(owner_info, dict) else "?"
            content = _strip_html(p.get("hs_note_body") or "")[:300]
            date_sort = p.get("hs_timestamp") or p.get("hs_createdate") or ""
            items.append((date_sort, f"[{fecha}] NOTE — {author}\n  {content or '(sin contenido)'}"))
    print(f"   [temp] {len(note_ids)} notes")

    call_ids = _fetch_associations(hs_deal_id, "calls")
    if call_ids:
        for obj in _batch_read("calls", call_ids, CALL_PROPS):
            p = obj.get("properties", {})
            fecha = _format_date(p.get("hs_timestamp"))
            owner_id = p.get("hubspot_owner_id") or ""
            owner_info = owners.get(owner_id, {})
            owner_name = owner_info.get("name", "?") if isinstance(owner_info, dict) else "?"
            title = p.get("hs_call_title") or "—"
            duration_ms = p.get("hs_call_duration")
            duration_min = round(int(int(duration_ms) / 1000) / 60) if duration_ms else 0
            body_clean = _strip_html(p.get("hs_call_body") or "")
            transcript = f"\n  {body_clean[:500]}" if body_clean and len(body_clean) >= 200 else "\n  (sin transcripción)"
            date_sort = p.get("hs_timestamp") or ""
            items.append((date_sort, f"[{fecha}] CALL — {owner_name} ({duration_min}min) — {title}{transcript}"))
    print(f"   [temp] {len(call_ids)} calls")

    items.sort(key=lambda x: x[0])

    if parts:
        parts.append("\n=== INTERACCIONES ===")
    parts.extend(text for _, text in items)

    if not parts:
        return "No interactions recorded."

    print(f"   [temp] Context built: {len(items)} items, {len(owners)} owners")
    return "\n\n".join(parts)
