"""
Module: poc_plan (CONDITIONAL)
Output: PDF slide — POC/trial plan with KPIs, timeline, success criteria.
"""

from src.pipelines.pae_followup.modules._html import (
    _esc, _allow_bold, slide_page, render_slide_pdf,
)


def render(section_data: dict, data: dict, brief: dict) -> dict:
    company = data["company"]

    kpis_html = ""
    for i, kpi in enumerate(section_data.get("kpis", []), 1):
        kpis_html += (
            f'<tr>'
            f'<td class="p2-num">{i}.</td>'
            f'<td><div class="p2-q">{_esc(kpi.get("metric", ""))}</div>'
            f'<div class="p2-why">Target: {_allow_bold(kpi.get("target", ""))}</div></td>'
            f'</tr>'
        )

    phases_html = ""
    for i, phase in enumerate(section_data.get("phases", []), 1):
        phases_html += (
            f'<tr>'
            f'<td class="p2-num">{i}.</td>'
            f'<td class="p2-time">{_esc(phase.get("duration", ""))}</td>'
            f'<td><div class="p2-q">{_esc(phase.get("phase", ""))}</div>'
            f'<div class="p2-why">{_allow_bold(phase.get("detail", ""))}</div></td>'
            f'</tr>'
        )

    body = f'''
    <div class="stit stit-first">Objetivo del POC</div>
    <div class="p2-block">{_allow_bold(section_data.get("objective", ""))}</div>

    <div class="stit">KPIs de éxito</div>
    <table class="p2-numbered">{kpis_html}</table>

    <div class="stit">Timeline</div>
    <table class="p2-numbered">{phases_html}</table>

    <div class="stit">Participantes</div>
    <div class="p2-block">{_allow_bold(section_data.get("participants", ""))}</div>

    <div class="note-block red"><b>Criterio de conversión.</b> {_esc(section_data.get("conversion_criteria", ""))}</div>
    <div class="note-block amber"><b>Riesgo.</b> {_esc(section_data.get("risk", ""))}</div>
    '''

    page = slide_page(
        label="Plan POC / Trial",
        title=f"Proof of Concept — {company}",
        subtitle=section_data.get("suggested_duration", "2-4 semanas"),
        body_html=body,
    )

    slug = company.lower().replace(" ", "-")
    return {
        "type": "pdf",
        "pdf_bytes": render_slide_pdf(page, f"poc-{slug}.pdf"),
        "filename": f"poc-plan-{slug}.pdf",
        "intro": f":test_tube: *Plan POC* — criterios de éxito y timeline para {company}",
    }
