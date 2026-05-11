"""One-shot migration: copy email_summary, email_type, key_people from Airtable to Supabase.

Matches by hs_engagement_id. Only updates Supabase emails that have email_summary IS NULL.
Does NOT call Claude — pure data copy.
"""

import os
import time
import requests

from src.db.client import supabase

AIRTABLE_TOKEN = os.environ["AIRTABLE_TOKEN"]
AIRTABLE_BASE_ID = os.environ["AIRTABLE_BASE_ID"]
AIRTABLE_EMAILS_TABLE = "tbltDfeem4cNwMSH5"

HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_TOKEN}",
    "Content-Type": "application/json",
}

BASE_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_EMAILS_TABLE}"

BATCH = 500


def _fetch_airtable_processed() -> dict[str, dict]:
    """Read all emails from Airtable that have Email_Summary filled. Returns {hs_engagement_id: {summary, type, key_people}}."""
    print("1. Reading processed emails from Airtable ...")
    result: dict[str, dict] = {}
    offset = None
    page = 0

    while True:
        params = {
            "filterByFormula": 'NOT({Email_Summary}="")',
            "fields[]": ["HS_ENGAGEMENT_ID", "Email_Summary", "Email_Type", "Key_People"],
            "pageSize": 100,
        }
        if offset:
            params["offset"] = offset

        resp = requests.get(BASE_URL, headers=HEADERS, params=params)
        if resp.status_code == 429:
            print("   Rate limited, waiting 30s ...")
            time.sleep(30)
            continue
        resp.raise_for_status()

        data = resp.json()
        records = data.get("records", [])
        for r in records:
            f = r.get("fields", {})
            hs_id = str(f.get("HS_ENGAGEMENT_ID", "")).strip()
            if not hs_id:
                continue
            summary = f.get("Email_Summary", "")
            if not summary:
                continue
            result[hs_id] = {
                "email_summary": summary,
                "email_type": f.get("Email_Type", "other") or "other",
                "key_people": f.get("Key_People", "") or "",
            }

        page += 1
        if page % 10 == 0:
            print(f"   {len(result)} processed emails read ({page} pages) ...")

        offset = data.get("offset")
        if not offset:
            break

    print(f"   Total: {len(result)} processed emails from Airtable")
    return result


def _fetch_supabase_pending() -> dict[str, str]:
    """Read Supabase emails where email_summary IS NULL. Returns {hs_engagement_id: supabase_id}."""
    print("2. Reading pending emails from Supabase ...")
    result: dict[str, str] = {}
    offset = 0

    while True:
        resp = (
            supabase.table("emails")
            .select("id, hs_engagement_id")
            .is_("email_summary", "null")
            .not_.is_("hs_engagement_id", "null")
            .range(offset, offset + BATCH - 1)
            .execute()
        )
        rows = resp.data or []
        for r in rows:
            hs_id = str(r["hs_engagement_id"]).strip()
            if hs_id:
                result[hs_id] = r["id"]
        if len(rows) < BATCH:
            break
        offset += BATCH

    print(f"   Total: {len(result)} pending emails in Supabase")
    return result


def main():
    airtable_data = _fetch_airtable_processed()
    supabase_pending = _fetch_supabase_pending()

    matches = set(airtable_data.keys()) & set(supabase_pending.keys())
    print(f"\n3. Matched: {len(matches)} emails to update")

    if not matches:
        print("Nothing to do.")
        return

    updated = 0
    errors = 0
    match_list = sorted(matches)

    for i in range(0, len(match_list), BATCH):
        batch = match_list[i : i + BATCH]
        for hs_id in batch:
            try:
                supabase_id = supabase_pending[hs_id]
                fields = airtable_data[hs_id]
                supabase.table("emails").update(fields).eq("id", supabase_id).execute()
                updated += 1
            except Exception as e:
                print(f"   ERROR on {hs_id}: {e}")
                errors += 1

        if (i + BATCH) % 2000 == 0 or i + BATCH >= len(match_list):
            print(f"   [{min(i + BATCH, len(match_list))}/{len(match_list)}] updated")

    print(f"\nDone: {updated} updated, {errors} errors")
    remaining = len(supabase_pending) - len(matches)
    print(f"Remaining without summary: ~{remaining} (will need Claude processing)")


if __name__ == "__main__":
    main()
