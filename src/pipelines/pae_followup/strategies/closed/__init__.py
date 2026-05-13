"""
Closed strategy — deal is won or lost after demo.
Generates close report for the TL.
"""

from src.pipelines.pae_followup.strategies.closed.generate import generate_brief
from src.pipelines.pae_followup.strategies.closed.pdf import generate_pdf


def run(subtype: str, data: dict) -> tuple[bytes, dict]:
    brief = generate_brief(subtype=subtype, data=data)
    pdf_bytes = generate_pdf(brief=brief, data=data)
    return pdf_bytes, brief
