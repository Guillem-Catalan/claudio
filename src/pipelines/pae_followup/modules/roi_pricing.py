"""
Module: roi_pricing (CONDITIONAL)
Output: PDF slide — ROI framework, cost justification, pricing strategy.
"""

from src.pipelines.pae_followup.modules._html import (
    _esc, _allow_bold, slide_page, render_slide_pdf,
)


def render(section_data: dict, data: dict, brief: dict) -> dict:
    company = data["company"]
    amount_str = data["amount_str"]

    items_html = ""
    for i, item in enumerate(section_data.get("roi_items", []), 1):
        items_html += (
            f'<tr>'
            f'<td class="p2-num">{i}.</td>'
            f'<td><div class="p2-q">{_esc(item.get("metric", ""))}</div>'
            f'<div class="p2-why">{_allow_bold(item.get("value", ""))}</div></td>'
            f'</tr>'
        )

    body = f'''
    <div class="stit stit-first">Inversión</div>
    <div class="p2-block"><b>{_esc(amount_str)}</b> · {_allow_bold(section_data.get("investment_context", ""))}</div>

    <div class="stit">ROI Framework</div>
    <table class="p2-numbered">{items_html}</table>

    <div class="stit">Argumento de valor</div>
    <div class="p2-block">{_allow_bold(section_data.get("value_argument", ""))}</div>

    <div class="note-block red"><b>Pricing strategy.</b> {_esc(section_data.get("pricing_strategy", ""))}</div>
    <div class="note-block blue"><b>Comparativa.</b> {_esc(section_data.get("comparison", ""))}</div>
    '''

    page = slide_page(
        label="ROI & Pricing",
        title=f"Justificación de inversión — {company}",
        subtitle=f"Deal: {amount_str}",
        body_html=body,
    )

    slug = company.lower().replace(" ", "-")
    return {
        "type": "pdf",
        "pdf_bytes": render_slide_pdf(page, f"roi-{slug}.pdf"),
        "filename": f"roi-pricing-{slug}.pdf",
        "intro": f":moneybag: *ROI & Pricing* — framework de justificación para {company}",
    }
