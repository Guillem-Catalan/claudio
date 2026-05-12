"""
Send PAE demo brief to Slack: intro message + PDF attachment in a single post.
"""

import os

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
        _client.files_upload_v2(
            channel=channel,
            content=pdf_bytes,
            filename=filename,
            title=filename,
            initial_comment=intro,
        )
        print(f"  Slack: sent to {channel}")
        return True
    except Exception as e:
        print(f"  Slack error: {e}")
        return False
