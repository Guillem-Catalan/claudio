"""
Send PAE demo brief to Slack: single message with intro text + PDF.
Uses raw API calls instead of files_upload_v2 to avoid double-message bug.
"""

import os

import requests
from slack_sdk import WebClient

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
_client = WebClient(token=SLACK_BOT_TOKEN)


def send_demo_brief(
    pdf_bytes: bytes,
    company: str,
    demo_time: str,
    amount_str: str,
    partner: str,
    contact: dict,
    channel: str | None = None,
) -> bool:
    if not channel:
        print("  No Slack channel configured — skipping")
        return False

    intro = (
        f":handshake: Demo mañana — {company} · {demo_time}\n"
        f"Contacto: {contact.get('name', '?')} · {contact.get('jobtitle', '')} · {contact.get('email', '')}"
    )
    if contact.get("phone"):
        intro += f" · {contact['phone']}"
    intro += f"\nDeal: {amount_str} | Partner: {partner}"

    filename = f"demo-brief-{company.lower().replace(' ', '-')}.pdf"

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
