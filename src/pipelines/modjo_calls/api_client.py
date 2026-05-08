import os
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

BASE_URL = "https://api.modjo.ai/v1"
MAX_WORKERS = 2


def _headers() -> dict:
    return {
        "X-API-KEY": os.environ["MODJO_API_KEY"],
        "Content-Type": "application/json",
    }


def _post(payload: dict, timeout: int = 30) -> dict:
    for _ in range(5):
        r = requests.post(
            f"{BASE_URL}/calls/exports",
            headers=_headers(),
            json=payload,
            timeout=timeout,
        )
        if r.status_code == 429:
            print("   [rate limit] Waiting 310s...")
            time.sleep(310)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError("Modjo API: max retries exceeded")


# ── Resolve emails → Modjo user IDs ─────────────────────────────────────────

def fetch_user_ids(target_emails: set[str]) -> dict[int, str]:
    """Returns {modjo_user_id: email} for every target email found in Modjo."""
    email_to_id: dict[str, int] = {}
    page = 1
    while True:
        r = requests.get(
            f"{BASE_URL}/users",
            headers=_headers(),
            params={"page": page, "perPage": 100},
        )
        r.raise_for_status()
        users = r.json().get("values", [])
        if not users:
            break
        for u in users:
            email_to_id[u["email"]] = u["id"]
        if len(users) < 100:
            break
        page += 1

    id_to_email: dict[int, str] = {}
    missing = []
    for email in target_emails:
        uid = email_to_id.get(email)
        if uid:
            id_to_email[uid] = email
        else:
            missing.append(email)

    if missing:
        print(f"   [!] Not found in Modjo: {missing}")

    return id_to_email


# ── Pass 1: scan pages to find call IDs from target users ────────────────────

def _scan_page(page: int, start: str, end: str, target_ids: set[int]) -> list[int]:
    payload = {
        "pagination": {"page": page, "perPage": 50},
        "filters": {"callStartDateRange": {"start": start, "end": end}},
        "relations": {"users": True},
    }
    try:
        calls = _post(payload).get("values", [])
    except Exception as e:
        print(f"   [!] Page {page} failed: {e}")
        return []

    matched = []
    for call in calls:
        rels = call.get("relations") or {}
        call_user_ids = {u["userId"] for u in rels.get("users", [])}
        if call_user_ids & target_ids:
            matched.append(call["callId"])
    return matched


def scan_call_ids(target_ids: set[int], since: datetime) -> list[int]:
    """Find all call IDs involving target users since a given date."""
    start = since.isoformat()
    end = datetime.now(timezone.utc).isoformat()

    probe = _post({
        "pagination": {"page": 1, "perPage": 50},
        "filters": {"callStartDateRange": {"start": start, "end": end}},
        "relations": {"users": True},
    })
    pagination = probe.get("pagination", {})
    total_pages = pagination.get("lastPage", 1)
    total_calls = pagination.get("totalValues", 0)
    print(f"   {total_calls} calls in range ({total_pages} pages)")

    matching_ids: list[int] = []
    completed = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(_scan_page, p, start, end, target_ids): p
            for p in range(1, total_pages + 1)
        }
        for future in as_completed(futures):
            matching_ids.extend(future.result())
            completed += 1
            if completed % 100 == 0 or completed == total_pages:
                print(f"   Scanned {completed}/{total_pages} — {len(matching_ids)} matching")

    return matching_ids


# ── Pass 2: fetch full data + transcripts ────────────────────────────────────

def fetch_call_details(call_ids: list[int]) -> list[dict]:
    """Fetch full call data (transcript, tags, contacts, deal, account) by ID."""
    all_calls: list[dict] = []
    batch_size = 50

    for i in range(0, len(call_ids), batch_size):
        batch = call_ids[i : i + batch_size]
        payload = {
            "pagination": {"page": 1, "perPage": batch_size},
            "filters": {"callIds": batch},
            "relations": {
                "transcript": True,
                "users": True,
                "tags": True,
                "contacts": True,
                "deal": True,
                "account": True,
            },
        }
        try:
            calls = _post(payload, timeout=60).get("values", [])
            all_calls.extend(calls)
            print(f"   Batch {i // batch_size + 1}: {len(calls)} calls fetched")
        except Exception as e:
            print(f"   [!] Batch failed: {e}")

    return all_calls
