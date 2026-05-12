"""
Temporary backfill: load missing auditable calls from HubSpot into Supabase.
Only inserts calls with role (PBD/PAE) + transcript >= 200 chars.
Does NOT audit — just loads data so future audit backfills can process them.
"""

import re
import time

from src.config import PAE_TAGS, PBD_TAGS, get_role, get_subteam
from src.db.client import supabase
from src.integrations import hubspot

CALL_PROPS = [
    "hs_timestamp",
    "hs_call_body",
    "hs_call_duration",
    "hs_call_title",
    "hubspot_owner_id",
]

_HTML_RE = re.compile(r"<[^>]+>")
_MODJO_RE = re.compile(r"app\.modjo\.ai/call-details/(\d+)")
_TAG_RE = re.compile(r"Tags?\s*:\s*(.+)", re.IGNORECASE)

BATCH = 1000


def _strip_html(text: str) -> str:
    clean = _HTML_RE.sub("", text)
    clean = clean.replace("&nbsp;", " ").replace("&amp;", "&")
    clean = clean.replace("&lt;", "<").replace("&gt;", ">")
    lines = [line.strip() for line in clean.splitlines()]
    return "\n".join(line for line in lines if line)


def _parse_date(raw: str) -> str | None:
    if not raw:
        return None
    return raw.replace("Z", "+00:00") if "T" in raw else None


def _fetch_associations(hs_deal_id: str) -> list[str]:
    ids: list[str] = []
    after = None
    while True:
        params = {"limit": "500"}
        if after:
            params["after"] = after
        data = hubspot.get(
            f"/crm/v4/objects/deals/{hs_deal_id}/associations/calls", params
        )
        for item in data.get("results", []):
            oid = str(item.get("toObjectId", ""))
            if oid:
                ids.append(oid)
        after = data.get("paging", {}).get("next", {}).get("after")
        if not after:
            break
    return ids


def _batch_read(ids: list[str]) -> list[dict]:
    results: list[dict] = []
    for i in range(0, len(ids), 100):
        batch = ids[i : i + 100]
        data = hubspot.post(
            "/crm/v3/objects/calls/batch/read",
            {"inputs": [{"id": oid} for oid in batch], "properties": CALL_PROPS},
        )
        results.extend(data.get("results", []))
    return results


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
        url = next_link.replace(hubspot.BASE, "") if next_link else ""
    return owners


def _load_existing_hs_call_ids() -> set[str]:
    print("  Loading existing hs_call_ids from calls table ...")
    ids: set[str] = set()
    offset = 0
    while True:
        r = (
            supabase.table("calls")
            .select("hs_call_id")
            .not_.is_("hs_call_id", "null")
            .range(offset, offset + BATCH - 1)
            .execute()
        )
        for row in r.data or []:
            ids.add(row["hs_call_id"])
        if len(r.data or []) < BATCH:
            break
        offset += BATCH
    return ids


def _load_existing_modjo_ids() -> set[str]:
    print("  Loading existing Modjo call_ids ...")
    ids: set[str] = set()
    offset = 0
    while True:
        r = (
            supabase.table("calls")
            .select("call_id")
            .eq("source", "modjo")
            .range(offset, offset + BATCH - 1)
            .execute()
        )
        for row in r.data or []:
            ids.add(row["call_id"])
        if len(r.data or []) < BATCH:
            break
        offset += BATCH
    return ids


def _load_deals_with_gap() -> list[dict]:
    print("  Loading deals with call gaps ...")
    offset = 0
    deals_map: dict[str, dict] = {}
    while True:
        r = (
            supabase.table("deals")
            .select("id, deal_id, deal_name, crm_id, numero_de_calls")
            .not_.is_("deal_id", "null")
            .gt("numero_de_calls", 0)
            .order("deal_id")
            .range(offset, offset + BATCH - 1)
            .execute()
        )
        for row in r.data or []:
            deals_map[row["deal_id"]] = row
        if len(r.data or []) < BATCH:
            break
        offset += BATCH

    # Count actual calls per hs_deal_id
    call_counts: dict[str, int] = {}
    offset = 0
    while True:
        r = (
            supabase.table("calls")
            .select("hs_deal_id")
            .not_.is_("hs_deal_id", "null")
            .range(offset, offset + BATCH - 1)
            .execute()
        )
        for row in r.data or []:
            hid = row["hs_deal_id"]
            call_counts[hid] = call_counts.get(hid, 0) + 1
        if len(r.data or []) < BATCH:
            break
        offset += BATCH

    gaps = []
    for hs_id, deal in deals_map.items():
        expected = deal.get("numero_de_calls") or 0
        actual = call_counts.get(hs_id, 0)
        if expected > actual:
            deal["_gap"] = expected - actual
            gaps.append(deal)

    gaps.sort(key=lambda d: -(d.get("_gap") or 0))
    return gaps


def main():
    print("1. Loading existing state ...")
    existing_hs_ids = _load_existing_hs_call_ids()
    existing_modjo_ids = _load_existing_modjo_ids()
    print(f"   {len(existing_hs_ids)} hs_call_ids, {len(existing_modjo_ids)} modjo ids")

    print("\n2. Finding deals with gaps ...")
    gap_deals = _load_deals_with_gap()
    total_gap = sum(d.get("_gap", 0) for d in gap_deals)
    print(f"   {len(gap_deals)} deals with gaps, ~{total_gap} calls missing")

    print("\n3. Fetching HubSpot owners ...")
    owners = _fetch_owners()
    print(f"   {len(owners)} owners")

    inserted = 0
    skipped_exists = 0
    skipped_modjo_link = 0
    skipped_not_auditable = 0
    errors = 0

    print(f"\n4. Processing {len(gap_deals)} deals ...")

    for i, deal in enumerate(gap_deals, 1):
        hs_deal_id = deal["deal_id"]
        deal_uuid = deal["id"]
        crm_id = deal.get("crm_id")
        deal_name = (deal.get("deal_name") or "?")[:50]

        if i % 100 == 0 or i == 1:
            print(
                f"\n   [{i}/{len(gap_deals)}] Processing {deal_name} "
                f"(gap={deal.get('_gap', '?')}) — "
                f"inserted={inserted}, skipped_na={skipped_not_auditable}"
            )

        try:
            hs_call_ids = _fetch_associations(hs_deal_id)
        except Exception as e:
            print(f"   ERROR fetching associations for {hs_deal_id}: {e}")
            errors += 1
            time.sleep(2)
            continue

        new_ids = [cid for cid in hs_call_ids if cid not in existing_hs_ids]
        if not new_ids:
            continue

        try:
            call_objects = _batch_read(new_ids)
        except Exception as e:
            print(f"   ERROR batch reading calls for {hs_deal_id}: {e}")
            errors += 1
            time.sleep(2)
            continue

        rows_to_insert: list[dict] = []

        for obj in call_objects:
            p = obj.get("properties", {})
            hs_id = str(obj.get("id", ""))
            body_raw = p.get("hs_call_body") or ""
            body_clean = _strip_html(body_raw)

            modjo_id = _MODJO_RE.search(body_raw)
            modjo_id = modjo_id.group(1) if modjo_id else None

            tags_match = _TAG_RE.search(body_raw)
            tags = (
                [t.strip() for t in tags_match.group(1).split(",") if t.strip()]
                if tags_match
                else []
            )

            owner_id = p.get("hubspot_owner_id") or ""
            owner_info = owners.get(owner_id, {})
            owner_email = owner_info.get("email", "")
            owner_name = owner_info.get("name", "")

            rol = get_role(owner_email, tags) if owner_email else None
            if rol is None and tags:
                if any(t in PBD_TAGS for t in tags):
                    rol = "PBD"
                elif any(t in PAE_TAGS for t in tags):
                    rol = "PAE"

            transcript = body_clean[:50000] if body_clean else None
            has_real_transcript = transcript and len(transcript) >= 200

            if not (has_real_transcript and rol):
                skipped_not_auditable += 1
                existing_hs_ids.add(hs_id)
                continue

            if modjo_id and modjo_id in existing_modjo_ids:
                skipped_modjo_link += 1
                existing_hs_ids.add(hs_id)
                continue

            duration_ms = p.get("hs_call_duration")
            duration_s = int(float(duration_ms) / 1000) if duration_ms else None
            fecha = _parse_date(p.get("hs_timestamp"))
            sub = get_subteam(owner_email) if owner_email else None

            rows_to_insert.append({
                "call_id": modjo_id if modjo_id else f"hs_{hs_id}",
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
                "team": "Partners",
                "duracion_segundos": duration_s,
                "transcript": transcript,
                "subteam": sub,
                "source": "modjo" if modjo_id else "hubspot",
            })
            existing_hs_ids.add(hs_id)

        if rows_to_insert:
            try:
                supabase.table("calls").upsert(
                    rows_to_insert, on_conflict="call_id"
                ).execute()
                inserted += len(rows_to_insert)
            except Exception as e:
                print(f"   ERROR inserting {len(rows_to_insert)} calls for {hs_deal_id}: {e}")
                errors += 1

    print(f"\n{'='*60}")
    print(f"DONE")
    print(f"  Inserted:            {inserted}")
    print(f"  Skipped (not audit): {skipped_not_auditable}")
    print(f"  Skipped (exists):    {skipped_exists}")
    print(f"  Skipped (modjo):     {skipped_modjo_link}")
    print(f"  Errors:              {errors}")
    print(f"  HubSpot requests:    {hubspot.total_requests()}")


if __name__ == "__main__":
    main()
