"""
Module: champion_pack (CONDITIONAL)
Output: PDF slide — materials for champion to sell internally to DM.
"""

from src.pipelines.pae_followup.modules._html import (
    _esc, _allow_bold, slide_page, render_slide_pdf,
)


def render(section_data: dict, data: dict, brief: dict) -> dict:
    company = data["company"]
    champion = section_data.get("champion_name", "Champion")
    dm = section_data.get("dm_name", "Decision Maker")

    args_html = ""
    for i, arg in enumerate(section_data.get("arguments", []), 1):
        args_html += (
            f'<tr>'
            f'<td class="p2-num">{i}.</td>'
            f'<td><div class="p2-q">{_esc(arg.get("point", ""))}</div>'
            f'<div class="p2-why">{_allow_bold(arg.get("evidence", ""))}</div></td>'
            f'</tr>'
        )

    concerns_html = ""
    for c in section_data.get("dm_likely_concerns", []):
        concerns_html += (
            f'<tr><td class="bi-dash">&mdash;</td>'
            f'<td><b>{_esc(c.get("concern", ""))}</b> · {_allow_bold(c.get("response", ""))}</td></tr>'
        )

    body = f'''
    <div class="stit stit-first">Stakeholder map</div>
    <div class="p2-block">
      <b>Champion:</b> {_esc(champion)} · <b>Decision Maker:</b> {_esc(dm)}<br>
      {_allow_bold(section_data.get("stakeholder_context", ""))}
    </div>

    <div class="stit">Argumentario para {_esc(champion)}</div>
    <table class="p2-numbered">{args_html}</table>

    <div class="stit">Preocupaciones probables del DM</div>
    <table class="bi-table">{concerns_html}</table>

    <div class="note-block red"><b>Ask al champion.</b> {_esc(section_data.get("champion_ask", ""))}</div>
    <div class="note-block blue"><b>Objetivo.</b> {_esc(section_data.get("objective", ""))}</div>
    '''

    page = slide_page(
        label="Champion Enablement",
        title=f"Pack de venta interna",
        subtitle=f"{champion} → {dm} · {company}",
        body_html=body,
    )

    slug = company.lower().replace(" ", "-")
    return {
        "type": "pdf",
        "pdf_bytes": render_slide_pdf(page, f"champion-{slug}.pdf"),
        "filename": f"champion-pack-{slug}.pdf",
        "intro": f":dart: *Champion pack* — argumentario para que {champion} venda internamente a {dm}",
    }
