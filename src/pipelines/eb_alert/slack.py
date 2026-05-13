"""Send EB alert to Slack when a deal enters Pricing and Packaging."""

import os

from slack_sdk import WebClient

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
EB_ALERT_CHANNEL = "C0ATY3V8CN4"

_client = WebClient(token=SLACK_BOT_TOKEN)


def _resolve_slack_user_ids() -> dict[str, str]:
    """Build name → Slack user ID map from workspace users."""
    name_map: dict[str, str] = {}
    try:
        cursor = None
        while True:
            resp = _client.users_list(cursor=cursor, limit=200)
            for member in resp.get("members", []):
                if member.get("deleted") or member.get("is_bot"):
                    continue
                uid = member["id"]
                profile = member.get("profile", {})
                real_name = profile.get("real_name_normalized", "") or member.get("real_name", "")
                display_name = profile.get("display_name_normalized", "")
                if real_name:
                    name_map[real_name.strip().lower()] = uid
                if display_name:
                    name_map[display_name.strip().lower()] = uid
            cursor = resp.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
    except Exception as e:
        print(f"  Warning: could not fetch Slack users: {e}")
    return name_map


def _mention(name: str | None, user_map: dict[str, str]) -> str:
    if not name:
        return "—"
    uid = user_map.get(name.strip().lower())
    if uid:
        return f"<@{uid}>"
    return name


def _format_amount(amount) -> str:
    if amount is None:
        return "—"
    try:
        return f"{float(amount):,.0f} EUR"
    except (ValueError, TypeError):
        return str(amount)


def send_eb_alert(
    deal_name: str,
    deal_id: str,
    pae: str | None,
    pbd: str | None,
    amount,
    close_date: str | None,
    partner: str | None,
    eb_status_text: str | None,
    eb_score: float | None,
) -> bool:
    user_map = _resolve_slack_user_ids()

    if eb_score is not None and eb_score >= 3:
        eb_label = "IDENTIFIED"
    elif eb_status_text:
        eb_label = "NOT IDENTIFIED"
    else:
        eb_label = "UNKNOWN"

    header_text = f":fire::red_circle: Deal sent to P&P with EB {eb_label}: {deal_name}"
    if partner:
        header_text += f" - from {partner}"

    eb_display = eb_status_text or "No EB assessment available"

    hs_url = f"https://app.hubspot.com/contacts/7865098/deal/{deal_id}"

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": header_text[:150], "emoji": True},
        },
        {"type": "divider"},
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Deal:*\n{deal_name or '—'}"},
                {"type": "mrkdwn", "text": f"*ID:*\n{deal_id}"},
                {"type": "mrkdwn", "text": f"*Owner:*\n{_mention(pae, user_map)}"},
                {"type": "mrkdwn", "text": f"*Lead:*\n{_mention(pbd, user_map)}"},
                {"type": "mrkdwn", "text": f"*Amount:*\n{_format_amount(amount)}"},
                {"type": "mrkdwn", "text": f"*Close date:*\n{close_date or '—'}"},
                {"type": "mrkdwn", "text": f"*Partner:*\n{partner or '—'}"},
            ],
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f":bar_chart: *EB Status*\n{eb_display}",
            },
        },
        {"type": "divider"},
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Open in HubSpot", "emoji": True},
                    "url": hs_url,
                    "action_id": "open_hubspot",
                }
            ],
        },
    ]

    try:
        _client.chat_postMessage(
            channel=EB_ALERT_CHANNEL,
            text=header_text,
            blocks=blocks,
        )
        print(f"  Slack: EB alert sent to {EB_ALERT_CHANNEL}")
        return True
    except Exception as e:
        print(f"  Slack error: {e}")
        return False
