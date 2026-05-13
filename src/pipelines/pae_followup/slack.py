"""
Send PAE follow-up bundle to Slack.

Active/Stalled: one parent message with text blocks + PDF files in thread.
Closed: single message with PDF (TL report).
"""

import os

import requests
from slack_sdk import WebClient

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
_client = WebClient(token=SLACK_BOT_TOKEN)


def _upload_pdf(pdf_bytes: bytes, filename: str, channel: str, thread_ts: str, intro: str):
    resp = _client.files_getUploadURLExternal(
        filename=filename,
        length=len(pdf_bytes),
    )
    requests.post(
        resp["upload_url"],
        data=pdf_bytes,
        headers={"Content-Type": "application/pdf"},
    )
    _client.files_completeUploadExternal(
        files=[{"id": resp["file_id"], "title": filename}],
        channel_id=channel,
        thread_ts=thread_ts,
        initial_comment=intro,
    )


def send_bundle(
    outputs: list[dict],
    company: str,
    demo_date_short: str,
    amount_str: str,
    partner: str,
    channel: str,
) -> bool:
    """
    Sends the full follow-up bundle as a Slack thread.
    Parent message has summary + text modules.
    Each PDF module goes as a threaded reply.
    """
    if not channel:
        print("  No Slack channel — skipping")
        return False

    text_blocks = []
    pdf_outputs = []
    for out in outputs:
        if out["type"] == "text":
            text_blocks.append(out)
        elif out["type"] == "pdf":
            pdf_outputs.append(out)

    module_names = [o["module"] for o in outputs]
    header = (
        f":clipboard: *Follow-up completo — {company}* · demo {demo_date_short}\n"
        f"Deal: {amount_str} | Partner: {partner}\n"
        f"Módulos generados: {len(outputs)} ({', '.join(module_names)})\n"
    )

    body_parts = [header]
    for block in text_blocks:
        emoji = block.get("emoji", ":memo:")
        title = block.get("title", block["module"])
        body_parts.append(f"\n{emoji} *{title}*\n{block['text']}")

    full_text = "\n".join(body_parts)

    try:
        msg = _client.chat_postMessage(
            channel=channel,
            text=full_text,
            unfurl_links=False,
            unfurl_media=False,
        )
        thread_ts = msg["ts"]

        for pdf_out in pdf_outputs:
            _upload_pdf(
                pdf_bytes=pdf_out["pdf_bytes"],
                filename=pdf_out["filename"],
                channel=channel,
                thread_ts=thread_ts,
                intro=pdf_out.get("intro", ""),
            )

        print(f"  Slack: sent {len(text_blocks)} text blocks + {len(pdf_outputs)} PDFs to {channel}")
        return True

    except Exception as e:
        print(f"  Slack error: {e}")
        return False


def send_report_closed(
    pdf_bytes: bytes,
    company: str,
    demo_date_short: str,
    amount_str: str,
    partner: str,
    pae_name: str,
    channel: str,
    report_label: str,
) -> bool:
    """Sends a TL close report — single message with PDF."""
    if not channel:
        print("  No TL channel — skipping")
        return False

    intro = (
        f":bar_chart: *{report_label}* — {company} · demo {demo_date_short}\n"
        f"PAE: {pae_name} | Deal: {amount_str} | Partner: {partner}"
    )

    slug = company.lower().replace(" ", "-")
    filename = f"{report_label.lower().replace(' ', '-')}-{slug}.pdf"

    try:
        resp = _client.files_getUploadURLExternal(
            filename=filename,
            length=len(pdf_bytes),
        )
        requests.post(
            resp["upload_url"],
            data=pdf_bytes,
            headers={"Content-Type": "application/pdf"},
        )
        _client.files_completeUploadExternal(
            files=[{"id": resp["file_id"], "title": filename}],
            channel_id=channel,
            initial_comment=intro,
        )
        print(f"  Slack: sent {report_label} to {channel}")
        return True
    except Exception as e:
        print(f"  Slack error: {e}")
        return False
