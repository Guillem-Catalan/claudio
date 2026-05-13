"""
Send PAE follow-up brief to Slack: single message with intro text + PDF.
"""

import os

import requests
from slack_sdk import WebClient

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
_client = WebClient(token=SLACK_BOT_TOKEN)


def send_followup_brief(
    pdf_bytes: bytes,
    company: str,
    demo_date_short: str,
    amount_str: str,
    partner: str,
    contact: dict,
    channel: str | None = None,
) -> bool:
    if not channel:
        print("  No Slack channel configured — skipping")
        return False

    intro = (
        f":calendar: Follow-up — {company} · demo {demo_date_short}\n"
        f"Contacto: {contact.get('name', '?')} · {contact.get('jobtitle', '')} · {contact.get('email', '')}"
    )
    if contact.get("phone"):
        intro += f" · {contact['phone']}"
    intro += f"\nDeal: {amount_str} | Partner: {partner}"

    filename = f"followup-brief-{company.lower().replace(' ', '-')}.pdf"

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

        print(f"  Slack: sent to {channel}")
        return True
    except Exception as e:
        print(f"  Slack error: {e}")
        return False
