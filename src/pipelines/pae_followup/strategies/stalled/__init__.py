"""
Stalled strategy — deal is on hold or needs reschedule after demo.
Generates re-engagement plan for the PAE.
"""

from src.pipelines.pae_followup.strategies.stalled.generate import generate_brief
from src.pipelines.pae_followup.strategies.stalled.pdf import generate_pdf


def run(subtype: str, data: dict) -> tuple[bytes, dict]:
    brief = generate_brief(subtype=subtype, data=data)
    pdf_bytes = generate_pdf(brief=brief, data=data)
    return pdf_bytes, brief
