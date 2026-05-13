"""Slack Block Kit payload builder — cloned from marcsorensen-ctrl/claudio-eb-alerts."""

from datetime import datetime

COLORS = {
    "IDENTIFIED_INVOLVED": "#2eb886",
    "IDENTIFIED_NOT_INVOLVED": "#daa038",
    "NOT_IDENTIFIED": "#e01e5a",
}

PARTNER_CONFIG = {
    "Santander": {"emoji": ":Santander:", "lead_email": "roberto.moran@factorial.co"},
    "Telefonica": {"emoji": ":telefonica:", "lead_email": "carlos.sanchez@factorial.co"},
    "Telefónica": {"emoji": ":telefonica:", "lead_email": "carlos.sanchez@factorial.co"},
}

HEADERS = {
    "IDENTIFIED_INVOLVED": "🟢 Deal sent to P&P with EB IDENTIFIED & INVOLVED",
    "IDENTIFIED_NOT_INVOLVED": "🟡 Deal sent to P&P with EB IDENTIFIED BUT NOT INVOLVED",
    "NOT_IDENTIFIED": "🔴 Deal sent to P&P with EB NOT IDENTIFIED",
}


def _format_date(date_str: str) -> str:
    if not date_str:
        return "N/A"
    try:
        dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
        return dt.strftime("%b %d, %Y")
    except Exception:
        return date_str


def build_missing_frontdeal_blocks(
    deal_id: str,
    deal_name: str,
    partner_name: str = "",
    lead_slack_user_id: str | None = None,
    lead_email: str | None = None,
) -> dict:
    hubspot_url = f"https://app.hubspot.com/contacts/4960096/record/0-3/{deal_id}"
    partner_cfg = PARTNER_CONFIG.get(partner_name, {})
    partner_emoji = partner_cfg.get("emoji", "")
    header_label = f"{partner_emoji} Missing front_deals row" if partner_emoji else "⚫ Missing front_deals row"

    if lead_slack_user_id:
        lead_line = f"\ncc <@{lead_slack_user_id}>"
    elif lead_email:
        lead_line = f"\ncc {lead_email}"
    else:
        lead_line = ""

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": header_label},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*{deal_name}*  ·  ID: `{deal_id}`\n"
                    f"• Populate the front_deals row before EB analysis is meaningful.{lead_line}"
                ),
            },
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "🔗 Open in HubSpot"},
                    "url": hubspot_url,
                }
            ],
        },
    ]
    return {
        "text": f"Missing front_deals row: {deal_name}",
        "attachments": [{"color": "#000000", "blocks": blocks}],
    }


def build_blocks(
    classification: str,
    deal_id: str,
    deal_name: str,
    amount: str,
    closedate: str,
    partner_name: str,
    e_score: float | None,
    eb_name: str | None,
    eb_role: str | None,
    e_accumulate: str,
    gap: str,
    coaching: str,
    slack_user_id: str | None = None,
    ae_email: str | None = None,
    ae_name: str | None = None,
    lead_slack_user_id: str | None = None,
    lead_email: str | None = None,
    lead_name: str | None = None,
) -> dict:
    color = COLORS[classification]
    partner_cfg = PARTNER_CONFIG.get(partner_name, {})
    partner_emoji = partner_cfg.get("emoji", "")
    header_text = f"{partner_emoji} {HEADERS[classification]}" if partner_emoji else HEADERS[classification]

    if slack_user_id:
        owner_part = f"<@{slack_user_id}>"
    elif ae_email:
        owner_part = ae_email
    elif ae_name:
        owner_part = ae_name
    else:
        owner_part = "AE unknown"

    if lead_slack_user_id:
        lead_part = f"  ·  *Lead:* <@{lead_slack_user_id}>"
    elif lead_email:
        lead_part = f"  ·  *Lead:* {lead_email}"
    elif lead_name:
        lead_part = f"  ·  *Lead:* {lead_name}"
    else:
        lead_part = ""

    e_score_part = f"  ·  E-Score {e_score}/10" if e_score is not None else ""
    context = (
        f"*Owner:* {owner_part}{lead_part}  ·  {amount}  ·  Closes {_format_date(closedate)}  "
        f"·  {partner_name or 'Unknown partner'}{e_score_part}"
    )

    hubspot_url = f"https://app.hubspot.com/contacts/4960096/record/0-3/{deal_id}"

    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": header_text},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*{deal_name}*  ·  ID: `{deal_id}`\n{context}"},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": coaching},
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "🔗 Open in HubSpot"},
                    "url": hubspot_url,
                },
            ],
        },
    ]

    return {
        "text": f"{header_text}: {deal_name}",
        "attachments": [{"color": color, "blocks": blocks}],
    }
