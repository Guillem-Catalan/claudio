"""Send demo evaluation PDF to Slack."""

import os

import requests
from slack_sdk import WebClient

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
_client = WebClient(token=SLACK_BOT_TOKEN)


def send_demo_report(
    pdf_bytes: bytes,
    company: str,
    pae: str,
    partner: str,
    amount_str: str,
    channel: str,
) -> bool:
    intro = (
        f":bar_chart: Demo Evaluation — {company}\n"
        f"PAE: {pae} · Partner: {partner} · {amount_str}"
    )

    filename = f"demo-eval-{company.lower().replace(' ', '-')}.pdf"

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
