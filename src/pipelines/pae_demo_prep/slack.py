"""
Send PAE demo brief to Slack: intro message + PDF attachment.
"""

import os

from slack_sdk import WebClient

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
_client = WebClient(token=SLACK_BOT_TOKEN)


def _upload_pdf(pdf_bytes: bytes, filename: str, channel: str) -> str | None:
    """Upload PDF to Slack via slack_sdk files_upload_v2."""
    try:
        r = _client.files_upload_v2(
            channel=channel,
            content=pdf_bytes,
            filename=filename,
            title=filename,
        )
        return r.get("file", {}).get("permalink")
    except Exception as e:
        print(f"  Upload failed: {e}")
        return None


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
    permalink = _upload_pdf(pdf_bytes, filename, channel)

    text = intro
    if permalink:
        text += f"\n{permalink}"

    try:
        _client.chat_postMessage(channel=channel, text=text, unfurl_links=True)
        print(f"  Slack: sent to {channel}")
        return True
    except Exception as e:
        print(f"  Slack error: {e}")
        return False
