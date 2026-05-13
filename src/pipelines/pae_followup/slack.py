"""
Send PAE follow-up reports to Slack.
Routes to PAE channel (active/stalled) or TL channel (closed).
"""

import os

import requests
from slack_sdk import WebClient

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
_client = WebClient(token=SLACK_BOT_TOKEN)

_STRATEGY_EMOJI = {
    "active": ":calendar:",
    "stalled": ":hourglass_flowing_sand:",
    "closed": ":bar_chart:",
}

_STRATEGY_LABEL = {
    "active": "Follow-up Brief",
    "stalled": "Re-engagement Plan",
    "closed": "Close Report",
}


def send_report(
    pdf_bytes: bytes,
    company: str,
    demo_date_short: str,
    amount_str: str,
    partner: str,
    contact: dict,
    channel: str,
    report_label: str,
    strategy: str,
    subtype: str,
    pae_name: str,
) -> bool:
    if not channel:
        print("  No Slack channel configured — skipping")
        return False

    emoji = _STRATEGY_EMOJI.get(strategy, ":memo:")
    label = _STRATEGY_LABEL.get(strategy, "Report")

    intro = f"{emoji} {label} — {company} · demo {demo_date_short}\n"

    if strategy == "closed":
        intro += f"PAE: {pae_name} · Resultado: {report_label}\n"
    else:
        intro += (
            f"Contacto: {contact.get('name', '?')} · "
            f"{contact.get('jobtitle', '')} · {contact.get('email', '')}"
        )
        if contact.get("phone"):
            intro += f" · {contact['phone']}"
        intro += "\n"

    intro += f"Deal: {amount_str} | Partner: {partner} | Tipo: {subtype}"

    slug = company.lower().replace(" ", "-")
    filename = f"{strategy}-{subtype}-{slug}.pdf"

    try:
        resp = _client.files_getUploadURLExternal(
            filename=filename,
            length=len(pdf_bytes),
        )
        upload_url = resp["upload_url"]
        file_id = resp["file_id"]

        requests.post(upload_url, data=pdf_bytes, headers={"Content-Type": "application/pdf"})

        _client.files_completeUploadExternal(
            files=[{"id": file_id, "title": filename}],
            channel_id=channel,
            initial_comment=intro,
        )

        print(f"  Slack: sent {strategy}/{subtype} to {channel}")
        return True
    except Exception as e:
        print(f"  Slack error: {e}")
        return False
