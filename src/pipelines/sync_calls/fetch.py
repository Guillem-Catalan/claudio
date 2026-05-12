"""
Sync HubSpot calls for a single deal to Supabase.
Matches calls with existing Modjo records, parses tags from body,
and creates new rows for calls not already tracked.
Calls without transcript or without rol are appended to deal_context only.
"""

import re

from src.config import get_role, get_subteam
from src.db.client import supabase
from src.integrations import hubspot

CALL_PROPS = [
    "hs_timestamp",
    "hs_call_body",
    "hs_call_duration",
    "hs_call_title",
    "hubspot_owner_id",
]

_MODJO_RE = re.compile(r"app\.modjo\.ai/call-details/(\d+)")
_TAG_RE = re.compile(r"Tags?\s*:\s*(.+)", re.IGNORECASE)
_HTML_RE = re.compile(r"<[^>]+>")


def _fetch_call_ids_for_deal(hs_deal_id: str) -> list[str]:
    call_ids: list[str] = []
    after = None
    while True:
        url = f"/crm/v4/objects/deals/{hs_deal_id}/associations/calls"
        params = {"limit": "500"}
        if after:
            params["after"] = after
        data = hubspot.get(url, params)
        for item in data.get("results", []):
            cid = str(item.get("toObjectId", ""))
            if cid:
                call_ids.append(cid)
        after = data.get("paging", {}).get("next", {}).get("after")
        if not after:
            break
    return call_ids


def _fetch_call_properties(call_ids: list[str]) -> list[dict]:
    results: list[dict] = []
    for i in range(0, len(call_ids), 100):
        batch = call_ids[i : i + 100]
        data = hubspot.post(
            "/crm/v3/objects/calls/batch/read",
            {"inputs": [{"id": cid} for cid in batch], "properties": CALL_PROPS},
        )
        results.extend(data.get("results", []))
    return results


def _existing_hs_call_ids(hs_deal_id: str) -> set[str]:
    result = (
        supabase.table("calls")
        .select("hs_call_id")
        .eq("hs_deal_id", hs_deal_id)
        .not_.is_("hs_call_id", "null")
        .execute()
    )
    return {r["hs_call_id"] for r in (result.data or [])}


def _existing_modjo_call_ids(hs_deal_id: str) -> dict[str, str]:
    """Return {call_id: id} for Modjo calls linked to this deal."""
    result = (
        supabase.table("calls")
        .select("id, call_id")
        .eq("hs_deal_id", hs_deal_id)
        .eq("source", "modjo")
        .execute()
    )
    return {r["call_id"]: r["id"] for r in (result.data or [])}


def _fetch_owners() -> dict[str, dict]:
    owners: dict[str, dict] = {}
    url = "/crm/v3/owners?limit=100"
    while url:
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
            url = ""
    return owners


def _strip_html(text: str) -> str:
    clean = _HTML_RE.sub("", text)
    clean = clean.replace("&nbsp;", " ").replace("&amp;", "&")
    clean = clean.replace("&lt;", "<").replace("&gt;", ">")
    lines = [line.strip() for line in clean.splitlines()]
    return "\n".join(line for line in lines if line)


def _parse_modjo_id(body: str) -> str | None:
    m = _MODJO_RE.search(body)
    return m.group(1) if m else None


def _parse_tags(body: str) -> list[str]:
    m = _TAG_RE.search(body)
    if not m:
        return []
    raw = m.group(1)
    tags = [t.strip() for t in raw.split(",")]
    return [t for t in tags if t]


def _parse_date(raw: str) -> str | None:
    if not raw:
        return None
    return raw.replace("Z", "+00:00") if "T" in raw else None


def _format_date(raw: str | None) -> str:
    if not raw:
        return "?"
    return raw[:10] if len(raw) >= 10 else raw


def _append_calls_to_context(deal_uuid: str, context_entries: list[str]):
    if not context_entries:
        return

    deal = (
        supabase.table("deals")
        .select("deal_context")
        .eq("id", deal_uuid)
        .maybe_single()
        .execute()
    )
    if not deal.data:
        return

    current = deal.data.get("deal_context") or ""
    new_block = "\n\n".join(context_entries)

    if current:
        updated = current + "\n\n" + new_block
    else:
        updated = new_block

    supabase.table("deals").update(
        {"deal_context": updated}
    ).eq("id", deal_uuid).execute()


def run(deal_uuid: str, hs_deal_id: str):
    print(f"1. Fetching call associations for deal {hs_deal_id} ...")
    hs_call_ids = _fetch_call_ids_for_deal(hs_deal_id)
    print(f"   {len(hs_call_ids)} calls found in HubSpot")

    if not hs_call_ids:
        print("   No calls — done.")
        return

    print("2. Checking existing calls in Supabase ...")
    existing_hs = _existing_hs_call_ids(hs_deal_id)
    new_hs_ids = [cid for cid in hs_call_ids if cid not in existing_hs]
    print(f"   {len(existing_hs)} already tracked, {len(new_hs_ids)} new")

    if not new_hs_ids:
        print("   All calls already synced — done.")
        return

    print(f"3. Fetching properties for {len(new_hs_ids)} new calls ...")
    call_objects = _fetch_call_properties(new_hs_ids)
    print(f"   {len(call_objects)} objects returned")

    print("4. Fetching owners ...")
    owners = _fetch_owners()

    modjo_map = _existing_modjo_call_ids(hs_deal_id)
    print(f"   {len(modjo_map)} existing Modjo calls for this deal")

    deal_result = (
        supabase.table("deals")
        .select("crm_id")
        .eq("id", deal_uuid)
        .maybe_single()
        .execute()
    )
    crm_id = deal_result.data["crm_id"] if deal_result.data else None

    print("5. Processing calls ...")
    updates = []
    inserts = []
    context_entries = []

    for obj in call_objects:
        p = obj.get("properties", {})
        hs_id = str(obj.get("id", ""))
        body_raw = p.get("hs_call_body") or ""
        body_clean = _strip_html(body_raw)

        modjo_id = _parse_modjo_id(body_raw)
        tags = _parse_tags(body_raw)

        owner_id = p.get("hubspot_owner_id") or ""
        owner_info = owners.get(owner_id, {})
        owner_email = owner_info.get("email", "")
        owner_name = owner_info.get("name", "")

        rol = get_role(owner_email) if owner_email else None
        if rol is None and tags:
            from src.config import PBD_TAGS, PAE_TAGS
            if any(t in PBD_TAGS for t in tags):
                rol = "PBD"
            elif any(t in PAE_TAGS for t in tags):
                rol = "PAE"

        sub = get_subteam(owner_email) if owner_email else None

        duration_ms = p.get("hs_call_duration")
        duration_s = int(int(duration_ms) / 1000) if duration_ms else None
        duration_min = round(duration_s / 60) if duration_s else 0

        fecha = _parse_date(p.get("hs_timestamp"))
        fecha_display = _format_date(fecha)

        if modjo_id and modjo_id in modjo_map:
            updates.append({
                "id": modjo_map[modjo_id],
                "hs_call_id": hs_id,
                "deal_id": deal_uuid,
                "hs_deal_id": hs_deal_id,
                "crm_id": crm_id,
                "tags": tags if tags else None,
            })
        else:
            call_id_val = modjo_id if modjo_id else f"hs_{hs_id}"
            transcript = body_clean[:50000] if body_clean else None
            has_real_transcript = transcript and len(transcript) >= 200

            if has_real_transcript and rol:
                inserts.append({
                    "call_id": call_id_val,
                    "hs_call_id": hs_id,
                    "deal_id": deal_uuid,
                    "hs_deal_id": hs_deal_id,
                    "crm_id": crm_id,
                    "titulo": p.get("hs_call_title") or "",
                    "fecha": fecha,
                    "owner_email": owner_email or None,
                    "owner_nombre": owner_name or None,
                    "rol": rol,
                    "tags": tags if tags else [],
                    "team": "Partners" if rol else None,
                    "duracion_segundos": duration_s,
                    "transcript": transcript,
                    "subteam": sub,
                    "source": "modjo" if modjo_id else "hubspot",
                })
            else:
                title = p.get("hs_call_title") or "—"
                rep_display = owner_name or owner_email or "?"
                if has_real_transcript:
                    entry = f"[{fecha_display}] CALL [hs:{hs_id}] — {rep_display} ({duration_min}min) — {title}\n  {body_clean[:500]}"
                else:
                    entry = f"[{fecha_display}] CALL [hs:{hs_id}] — {rep_display} ({duration_min}min) — {title}\n  (sin transcripción)"
                context_entries.append(entry)

    print(f"   {len(updates)} Modjo calls to link, {len(inserts)} auditable calls to insert, {len(context_entries)} calls to context only")

    if updates:
        for upd in updates:
            row_id = upd.pop("id")
            update_data = {k: v for k, v in upd.items() if v is not None}
            supabase.table("calls").update(update_data).eq("id", row_id).execute()
        print(f"   {len(updates)} Modjo calls linked with hs_call_id")

    if inserts:
        result = (
            supabase.table("calls")
            .upsert(inserts, on_conflict="call_id")
            .execute()
        )
        print(f"   {len(result.data)} calls inserted")
    else:
        print("   No new auditable calls to insert")

    if context_entries:
        print(f"   Appending {len(context_entries)} non-auditable calls to deal_context ...")
        _append_calls_to_context(deal_uuid, context_entries)

    print(f"   HubSpot API requests: {hubspot.total_requests()}")
