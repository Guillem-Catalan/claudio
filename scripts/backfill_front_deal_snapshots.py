"""Backfill front_deal_snapshots from Airtable front_deals table."""

import os
import requests
from src.db.client import supabase

AT_TOKEN = os.environ["AIRTABLE_TOKEN"]
AT_BASE = os.environ["AIRTABLE_BASE_ID"]
AT_TABLE = "tbldZIIihRbX279v1"
BATCH = 500


def _load_airtable() -> list[dict]:
    headers = {"Authorization": f"Bearer {AT_TOKEN}"}
    records = []
    offset = None
    while True:
        url = f"https://api.airtable.com/v0/{AT_BASE}/{AT_TABLE}?pageSize=100"
        if offset:
            url += f"&offset={offset}"
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        data = r.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
        if len(records) % 5000 == 0:
            print(f"  ...{len(records)} loaded")
    return records


def _load_deal_map() -> dict[str, str]:
    """Map hs_deal_id (deal_id in Supabase) → UUID."""
    result = {}
    offset = 0
    while True:
        r = supabase.table("deals").select("id, deal_id").range(offset, offset + 999).execute()
        rows = r.data or []
        for row in rows:
            if row.get("deal_id"):
                result[str(row["deal_id"])] = row["id"]
        if len(rows) < 1000:
            break
        offset += 1000
    return result


def _to_num(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _to_int(val) -> int | None:
    if val is None:
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def _map_record(f: dict, deal_map: dict[str, str]) -> dict | None:
    hs_deal_id = str(f.get("Deal_id", "")).strip()
    snapshot_date = f.get("Snapshot_date", "")
    if not hs_deal_id or not snapshot_date:
        return None

    return {
        "deal_id": deal_map.get(hs_deal_id),
        "hs_deal_id": hs_deal_id,
        "snapshot_date": snapshot_date,
        "deal_name": f.get("Deal_Name"),
        "crm_id": f.get("crm_id"),
        "deal_age": _to_int(f.get("deal_age")),
        "stage": f.get("Stage"),
        "mrr": _to_num(f.get("MRR")),
        "hs_forecast_category": f.get("HS_forecast_category"),
        "pbd": f.get("PBD"),
        "pae": f.get("PAE"),
        "deal_summary": f.get("Deal_Summary"),
        "m_accumulate": f.get("M_accumulate"),
        "m_score": _to_num(f.get("M_score")),
        "e_accumulate": f.get("E_accumulate"),
        "e_score": _to_num(f.get("E_score")),
        "dc_accumulate": f.get("DC_accumulate"),
        "dc_score": _to_num(f.get("DC_score")),
        "dp_accumulate": f.get("DP_accumulate"),
        "dp_score": _to_num(f.get("DP_score")),
        "i_accumulate": f.get("I_accumulate"),
        "i_score": _to_num(f.get("I_score")),
        "c_accumulate": f.get("C_accumulate"),
        "c_score": _to_num(f.get("C_score")),
        "objections": f.get("objections"),
        "buyer_signals": f.get("buyer_signals"),
        "live_blockers": f.get("live_blockers"),
        "improvements": f.get("improvements"),
        "deal_strengths": f.get("deal_strengths"),
        "next_step": f.get("next_step"),
        "close_probability": _to_num(f.get("close_probability")),
        "claudio_forecast": f.get("claudio_forecast"),
    }


def main():
    print("1. Loading Airtable front_deals ...")
    records = _load_airtable()
    print(f"   {len(records)} records")

    print("2. Loading Supabase deal map ...")
    deal_map = _load_deal_map()
    print(f"   {len(deal_map)} deals mapped")

    print("3. Mapping records ...")
    rows = []
    skipped = 0
    for rec in records:
        mapped = _map_record(rec["fields"], deal_map)
        if mapped:
            rows.append(mapped)
        else:
            skipped += 1
    print(f"   {len(rows)} to upsert, {skipped} skipped (no deal_id or date)")

    print("4. Upserting to Supabase ...")
    ok = 0
    errors = 0
    for i in range(0, len(rows), BATCH):
        batch = rows[i : i + BATCH]
        try:
            supabase.table("front_deal_snapshots").upsert(
                batch, on_conflict="hs_deal_id,snapshot_date"
            ).execute()
            ok += len(batch)
        except Exception as e:
            print(f"   Error at batch {i}: {e}")
            errors += len(batch)
        if ok % 5000 == 0 and ok > 0:
            print(f"   ...{ok} upserted")

    print(f"\nDone: {ok} ok, {errors} errors")


if __name__ == "__main__":
    main()
