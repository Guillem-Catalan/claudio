import os
import threading
import time

import requests

TOKEN = os.environ.get("HUBSPOT_TOKEN", "")
BASE = "https://api.hubapi.com"
_MIN_INTERVAL = 0.12
_last_request_at = 0.0
_request_count = 0
_lock = threading.Lock()


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    }


def _throttle():
    global _last_request_at, _request_count
    with _lock:
        now = time.monotonic()
        wait = _MIN_INTERVAL - (now - _last_request_at)
        if wait > 0:
            time.sleep(wait)
        _last_request_at = time.monotonic()
        _request_count += 1


_RETRYABLE = {401, 429, 500, 502, 503}
_MAX_RETRIES = 3


def _retry_wait(resp: requests.Response, attempt: int) -> float:
    if resp.status_code == 429:
        return float(resp.headers.get("Retry-After", 10))
    return 2 ** attempt


def get(path: str, params: dict | None = None) -> dict:
    for attempt in range(_MAX_RETRIES):
        _throttle()
        resp = requests.get(f"{BASE}{path}", headers=_headers(), params=params)
        if resp.status_code in _RETRYABLE and attempt < _MAX_RETRIES - 1:
            wait = _retry_wait(resp, attempt)
            print(f"  [hubspot {resp.status_code}] retry {attempt+1}/{_MAX_RETRIES} in {wait:.0f}s ...")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.json()


def post(path: str, body: dict) -> dict:
    for attempt in range(_MAX_RETRIES):
        _throttle()
        resp = requests.post(f"{BASE}{path}", headers=_headers(), json=body)
        if resp.status_code in _RETRYABLE and attempt < _MAX_RETRIES - 1:
            wait = _retry_wait(resp, attempt)
            print(f"  [hubspot {resp.status_code}] retry {attempt+1}/{_MAX_RETRIES} in {wait:.0f}s ...")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.json()


def total_requests() -> int:
    return _request_count
