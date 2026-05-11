"""
Fetch all emails for a single deal from HubSpot and upsert to Supabase.
Triggered by: trg_deal_emails_changed on deals table.
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


def _clean_body(raw: str) -> str:
    if not raw:
        return ""
    text = _HTML_TAGS.sub(" ", raw)
    chain_match = _CHAIN_MARKERS.search(text)
    sig_match = _SIGNATURE_MARKERS.search(text)
    cutoffs = [m.start() for m in [chain_match, sig_match] if m]
    if cutoffs:
        text = text[: min(cutoffs)]
    return _WHITESPACE.sub("\n\n", text).strip()[:8000]


def _normalize_subject(subject: str) -> str:
    if not subject:
        return ""
    cleaned = re.sub(r"^(re|fwd?|rv|tr)[\s:]+", "", subject.strip(), flags=re.IGNORECASE)
    return cleaned.strip().lower()[:200]


def _parse_direction(raw: str) -> str:
    if not raw:
        return ""
    return (
        raw.replace("_EMAIL", "")
        .replace("INCOMING", "inbound")
        .replace("OUTGOING", "outbound")
        .lower()
    )


def _parse_date(raw: str) -> str | None:
    if not raw:
        return None
    return raw.replace("Z", "+00:00") if "T" in raw else None


def _fetch_email_ids_for_deal(hs_deal_id: str) -> list[str]:
    email_ids: list[str] = []
    after = None
    while True:
        url = f"/crm/v4/objects/deals/{hs_deal_id}/associations/emails"
        params = {"limit": "500"}
        if after:
            params["after"] = after
        data = hubspot.get(url, params)
        for item in data.get("results", []):
            eid = str(item.get("toObjectId", ""))
            if eid:
                email_ids.append(eid)
        after = data.get("paging", {}).get("next", {}).get("after")
        if not after:
            break
    return email_ids


def _fetch_email_properties(email_ids: list[str]) -> list[dict]:
    results: list[dict] = []
    for i in range(0, len(email_ids), 100):
        batch = email_ids[i : i + 100]
        data = hubspot.post(
            "/crm/v3/objects/emails/batch/read",
            {"inputs": [{"id": eid} for eid in batch], "properties": EMAIL_PROPS},
        )
        results.extend(data.get("results", []))
    return results


def _existing_engagement_ids(hs_deal_id: str) -> set[str]:
    result = (
        supabase.table("emails")
        .select("hs_engagement_id")
        .eq("hs_deal_id", hs_deal_id)
        .execute()
    )
    return {r["hs_engagement_id"] for r in (result.data or [])}


def run(deal_uuid: str, hs_deal_id: str):
    print(f"1. Fetching email associations for deal {hs_deal_id} ...")
    email_ids = _fetch_email_ids_for_deal(hs_deal_id)
    print(f"   {len(email_ids)} emails found in HubSpot")

    if not email_ids:
        print("   No emails — done.")
        return

    print("2. Checking existing emails in Supabase ...")
    existing = _existing_engagement_ids(hs_deal_id)
    new_ids = [eid for eid in email_ids if eid not in existing]
    print(f"   {len(existing)} existing, {len(new_ids)} new")

    if not new_ids:
        print("   All emails already synced — done.")
        return

    print(f"3. Fetching properties for {len(new_ids)} new emails ...")
    email_objects = _fetch_email_properties(new_ids)
    print(f"   {len(email_objects)} objects returned")

    # Resolve crm_id from the deal
    deal_result = (
        supabase.table("deals")
        .select("crm_id")
        .eq("id", deal_uuid)
        .maybe_single()
        .execute()
    )
    crm_id = deal_result.data["crm_id"] if deal_result.data else None

    print("4. Upserting to Supabase ...")
    rows = []
    skipped = 0
    for obj in email_objects:
        p = obj.get("properties", {})
        hs_id = str(obj.get("id", ""))

        body_raw = p.get("hs_email_text") or p.get("hs_email_html") or ""
        body_clean = _clean_body(body_raw)

        row = {
            "hs_engagement_id": hs_id,
            "deal_id": deal_uuid,
            "hs_deal_id": hs_deal_id,
            "crm_id": crm_id,
            "date": _parse_date(p.get("hs_timestamp") or p.get("hs_createdate")),
            "direction": _parse_direction(p.get("hs_email_direction")),
            "from_email": p.get("hs_email_from_email") or "",
            "subject": p.get("hs_email_subject") or "",
            "body": body_raw[:50000],
            "thread_key": _normalize_subject(p.get("hs_email_subject")),
            "body_clean": body_clean,
        }

        if not body_clean:
            skipped += 1
            row["email_summary"] = ""
            row["email_type"] = "admin"
            row["key_people"] = ""

        rows.append(row)

    if rows:
        result = (
            supabase.table("emails")
            .upsert(rows, on_conflict="hs_engagement_id")
            .execute()
        )
        print(f"   {len(result.data)} emails upserted, {skipped} skipped (empty body)")
    else:
        print(f"   No emails with content to write ({skipped} skipped)")

    print(f"   HubSpot API requests: {hubspot.total_requests()}")
