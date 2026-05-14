"""Send weekly demo coaching PDF or no-demos notice to Slack."""

import os

import requests
from slack_sdk import WebClient

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
_client = WebClient(token=SLACK_BOT_TOKEN)


def send_demo_report(
    pdf_bytes: bytes,
    pae_name: str,
    week_range: str,
    demo_count: int,
    mrr_total: str,
    channel: str,
) -> bool:
    intro = (
        f":bar_chart: *Weekly Demo Coaching — {pae_name}*\n"
        f"Semana {week_range} · {demo_count} demos · {mrr_total}"
    )

    filename = f"demo-coaching-{pae_name.lower().replace(' ', '-')}.pdf"

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


def send_no_demos_notice(pae_name: str, week_range: str, channel: str) -> bool:
    text = (
        f":bar_chart: Weekly Demo Coaching — {pae_name}\n"
        f"No se han registrado demos en la semana {week_range}."
    )
    try:
        _client.chat_postMessage(channel=channel, text=text)
        print(f"  Slack: no-demos notice sent to {channel}")
        return True
    except Exception as e:
        print(f"  Slack error: {e}")
        return False
