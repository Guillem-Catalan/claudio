"""
Module: battlecard (CONDITIONAL)
Output: PDF slide — competitive positioning vs named competitor.
"""

from src.pipelines.pae_followup.modules._html import (
    _esc, _allow_bold, slide_page, render_slide_pdf,
)


def render(section_data: dict, data: dict, brief: dict) -> dict:
    company = data["company"]
    competitor = section_data.get("competitor", "Competidor")

    diffs_html = ""
    for i, d in enumerate(section_data.get("differentiators", []), 1):
        diffs_html += (
            f'<tr>'
            f'<td class="p2-num">{i}.</td>'
            f'<td><div class="p2-q">{_esc(d.get("area", ""))}</div>'
            f'<div class="p2-why">Factorial: {_allow_bold(d.get("factorial", ""))} · '
            f'{_esc(competitor)}: {_allow_bold(d.get("competitor_position", ""))}</div></td>'
            f'</tr>'
        )

    attacks_html = ""
    for item in section_data.get("attack_points", []):
        attacks_html += f'<tr><td class="bi-dash">&mdash;</td><td>{_allow_bold(item)}</td></tr>'

    body = f'''
    <div class="stit stit-first">Diferenciadores clave</div>
    <table class="p2-numbered">{diffs_html}</table>

    <div class="stit">Puntos de ataque</div>
    <table class="bi-table">{attacks_html}</table>

    <div class="stit">Qué NO decir</div>
    <div class="p2-block">{_allow_bold(section_data.get("avoid", ""))}</div>

    <div class="note-block red"><b>Win theme.</b> {_esc(section_data.get("win_theme", ""))}</div>
    '''

    page = slide_page(
        label=f"Battlecard vs {competitor}",
        title=f"Posicionamiento competitivo",
        subtitle=f"{company} — {competitor} detectado en la demo",
        body_html=body,
    )

    slug = company.lower().replace(" ", "-")
    comp_slug = competitor.lower().replace(" ", "-")
    return {
        "type": "pdf",
        "pdf_bytes": render_slide_pdf(page, f"battlecard-{slug}.pdf"),
        "filename": f"battlecard-{comp_slug}-{slug}.pdf",
        "intro": f":crossed_swords: *Battlecard vs {competitor}* — diferenciadores para {company}",
    }
