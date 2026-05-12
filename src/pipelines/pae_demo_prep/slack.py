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
    """Upload PDF to Slack, return permalink or None."""
    auth_header = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}

    r = requests.post(
        "https://slack.com/api/files.getUploadURLExternal",
        headers=auth_header,
        data={"filename": filename, "length": len(pdf_bytes)},
    )
    meta = r.json()
    if not meta.get("ok"):
        print(f"  Upload URL failed: {meta.get('error')}")
        return None

    r2 = requests.put(
        meta["upload_url"],
        data=pdf_bytes,
        headers={"Content-Type": "application/pdf"},
    )
    if r2.status_code not in (200, 201):
        print(f"  PDF PUT failed: {r2.status_code}")
        return None

    r3 = requests.post(
        "https://slack.com/api/files.completeUploadExternal",
        headers=auth_header,
        json={"files": [{"id": meta["file_id"]}], "channel_id": channel},
    )
    result = r3.json()
    if not result.get("ok"):
        print(f"  Complete upload failed: {result.get('error')}")
        return None

    files_info = result.get("files", [])
    return files_info[0].get("permalink", "") if files_info else None


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
