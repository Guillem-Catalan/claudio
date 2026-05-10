import os
import time

import requests

TOKEN = os.environ.get("HUBSPOT_TOKEN", "")
BASE = "https://api.hubapi.com"
_MIN_INTERVAL = 0.12
_last_request_at = 0.0
_request_count = 0


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    }


def _throttle():
    global _last_request_at, _request_count
    now = time.monotonic()
    wait = _MIN_INTERVAL - (now - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.monotonic()
    _request_count += 1


def get(path: str, params: dict | None = None) -> dict:
    _throttle()
    resp = requests.get(f"{BASE}{path}", headers=_headers(), params=params)
    if resp.status_code == 429:
        wait = int(resp.headers.get("Retry-After", 10))
        print(f"  [rate-limit] waiting {wait}s ...")
        time.sleep(wait)
        return get(path, params)
    resp.raise_for_status()
    return resp.json()


def post(path: str, body: dict) -> dict:
    _throttle()
    resp = requests.post(f"{BASE}{path}", headers=_headers(), json=body)
    if resp.status_code == 429:
        wait = int(resp.headers.get("Retry-After", 10))
        print(f"  [rate-limit] waiting {wait}s ...")
        time.sleep(wait)
        return post(path, body)
    resp.raise_for_status()
    return resp.json()


def total_requests() -> int:
    return _request_count
