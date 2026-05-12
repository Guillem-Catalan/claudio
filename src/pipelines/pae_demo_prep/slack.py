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
    """Upload PDF to Slack via getUploadURLExternal + completeUploadExternal."""
    r = requests.post(
        "https://slack.com/api/files.getUploadURLExternal",
        headers=_headers(),
        json={"filename": filename, "length": len(pdf_bytes)},
    )
    data = r.json()
    if not data.get("ok"):
        print(f"  getUploadURLExternal failed: {data.get('error')}")
        return None

    upload_url = data["upload_url"]
    file_id = data["file_id"]

    r = requests.put(
        upload_url,
        data=pdf_bytes,
        headers={"Content-Type": "application/pdf"},
    )
    if r.status_code != 200:
        print(f"  PUT upload failed: {r.status_code} {r.text[:200]}")
        return None

    r = requests.post(
        "https://slack.com/api/files.completeUploadExternal",
        headers=_headers(),
        json={
            "files": [{"id": file_id, "title": filename}],
            "channel_id": channel,
        },
    )
    result = r.json()
    if not result.get("ok"):
        print(f"  completeUploadExternal failed: {result.get('error')}")
        return None

    files = result.get("files", [])
    if files:
        return files[0].get("permalink")
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
