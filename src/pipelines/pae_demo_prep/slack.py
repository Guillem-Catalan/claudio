"""
Send PAE demo brief to Slack: intro message + PDF attachment.
"""

import os

import requests

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")


def _headers():
    return {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/json",
    }


def _upload_pdf(pdf_bytes: bytes, filename: str, channel: str) -> str | None:
    """Upload PDF to Slack via legacy files.upload, return permalink or None."""
    r = requests.post(
        "https://slack.com/api/files.upload",
        headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
        data={
            "channels": channel,
            "filename": filename,
            "filetype": "pdf",
            "title": filename,
        },
        files={"file": (filename, pdf_bytes, "application/pdf")},
    )
    result = r.json()
    if not result.get("ok"):
        print(f"  Upload failed: {result.get('error')}")
        return None

    return result.get("file", {}).get("permalink")


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

    r = requests.post(
        "https://slack.com/api/chat.postMessage",
        headers=_headers(),
        json={"channel": channel, "text": text, "unfurl_links": True},
    )
    data = r.json()
    if data.get("ok"):
        print(f"  Slack: sent to {channel}")
        return True

    print(f"  Slack error: {data.get('error')}")
    return False
