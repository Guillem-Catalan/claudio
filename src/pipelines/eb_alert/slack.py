"""Slack client for EB alerts — posts Block Kit payloads."""

import logging
import os

import requests

logger = logging.getLogger(__name__)

SLACK_BASE = "https://slack.com/api"


class SlackClient:
    def __init__(self, token: str | None = None) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {"Authorization": f"Bearer {token or os.environ.get('SLACK_BOT_TOKEN', '')}"}
        )
        self._user_cache: dict[str, str | None] = {}

    def lookup_user_by_email(self, email: str) -> str | None:
        if email in self._user_cache:
            return self._user_cache[email]
        try:
            resp = self.session.get(
                f"{SLACK_BASE}/users.lookupByEmail", params={"email": email}
            )
            data = resp.json()
            if not data.get("ok"):
                logger.warning(f"Slack user lookup failed for {email}: {data.get('error')}")
                self._user_cache[email] = None
                return None
            user_id: str = data["user"]["id"]
            self._user_cache[email] = user_id
            return user_id
        except Exception as exc:
            logger.warning(f"Slack user lookup exception for {email}: {exc}")
            self._user_cache[email] = None
            return None

    def post_message(self, channel: str, payload: dict) -> str:
        body = {"channel": channel, **payload}
        resp = self.session.post(f"{SLACK_BASE}/chat.postMessage", json=body)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Slack post failed: {data.get('error')}")
        return str(data["ts"])
