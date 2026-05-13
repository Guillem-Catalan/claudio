"""
Module: analysis (CORE — always generated)
Output: PDF — demo analysis one-pager with MEDDIC, señales, probabilidad.
"""

import weasyprint

from src.pipelines.pae_followup.modules._html import _esc, _allow_bold, CSS_BASE


def _render_bullets(items: list[dict]) -> str:
    if not items:
        return ""
    rows = ""
    for item in items:
        if isinstance(item, str):
            rows += f'<tr><td class="bi-dash">&mdash;</td><td>{_allow_bold(item)}</td></tr>'
        else:
            bold = item.get("bold")
            text = item.get("text", "")
            if bold:
                rows += f'<tr><td class="bi-dash">&mdash;</td><td><b>{_esc(bold)}</b> · {_allow_bold(text)}</td></tr>'
            else:
                rows += f'<tr><td class="bi-dash">&mdash;</td><td>{_allow_bold(text)}</td></tr>'
    return f'<table class="bi-table">{rows}</table>'


def _render_meddic(meddic: list[dict]) -> str:
    rows = ""
    for row in meddic:
        rows += (
            f'<tr>'
            f'<td class="meddic-label">{_esc(row.get("key", ""))}</td>'
            f'<td class="meddic-icon">{row.get("icon", "⚠")}</td>'
            f'<td class="meddic-txt">{_allow_bold(row.get("text", ""))}</td>'
            f'</tr>'
        )
    return f'<table class="meddic-table">{rows}</table>'


def _render_signals(senales: list[dict]) -> str:
    if not senales:
        return ""
    rows = ""
    for s in senales:
        tag_class = "sig-tag-m" if s.get("tag_class") == "m" else "sig-tag-d"
        rows += (
            f'<tr>'
            f'<td class="sig-tag-cell"><span class="sig-tag {tag_class}">{_esc(s.get("tag", ""))}</span></td>'
            f'<td class="sig-txt">{_allow_bold(s.get("text", ""))}</td>'
            f'</tr>'
        )
    return f'<table class="sig-table">{rows}</table>'


def _render_objeciones(objs: list[dict]) -> str:
    if not objs:
        return ""
    html = ""
    for o in objs:
        html += (
            f'<div class="obj-card">'
            f'<div class="obj-q">{_esc(o.get("q", ""))}</div>'
            f'<div class="obj-a">{_allow_bold(o.get("a", ""))}</div>'
            f'</div>'
        )
    return html


def render(section_data: dict, data: dict, brief: dict) -> dict:
    company = data["company"]
    demo_datetime = data["demo_datetime"]
    amount_str = data["amount_str"]
    partner = data["partner"]
    next_step = section_data.get("next_step") or brief.get("next_step", {}).get("next_step") or "pendiente"

    probabilidad = _esc(section_data.get("probabilidad", "?"))
    engagement = _esc(section_data.get("engagement", "?"))
    etapa = _esc(section_data.get("etapa", "?"))
    prob_num = _esc(section_data.get("prob_num", "?"))

    error_critico = section_data.get("error_critico")
    error_html = ""
    if error_critico:
        error_html = (
            f'<div class="stit" style="color:#c8102e;">Error crítico en demo</div>'
            f'<div class="hbox">'
            f'<div class="ht">A resolver en el follow-up</div>'
            f'<p>{_allow_bold(error_critico)}</p>'
            f'</div>'
        )

    page_html = f'''<div class="page">
  <div class="hdr">
    <div class="tbl">
      <div class="tbl-cell hdr-left">
        <div class="brand">Factorial</div>
        <div class="type">Follow-up Brief</div>
        <div class="name">{_esc(company)}</div>
      </div>
      <div class="tbl-cell hdr-right">
        <div class="dates">
          {_esc(demo_datetime)}<br>
          <span class="sub">Next step · {_esc(next_step)}</span>
        </div>
      </div>
    </div>
  </div>

  <div class="kpi"><table><tr>
    <td style="padding-left:40px"><div class="kpi-lbl">MRR</div><div class="kpi-val red">{_esc(amount_str)}</div></td>
    <td><div class="kpi-lbl">Probabilidad</div><div class="kpi-val amb">{probabilidad}</div></td>
    <td><div class="kpi-lbl">Engagement</div><div class="kpi-val">{engagement}</div></td>
    <td><div class="kpi-lbl">Partner</div><div class="kpi-val">{_esc(partner)}</div></td>
    <td><div class="kpi-lbl">Etapa</div><div class="kpi-val">{etapa}</div></td>
  </tr></table></div>

  <div class="body-grid tbl">
    <div class="tbl-cell col-l">
      <div class="stit stit-first">Resumen de la demo</div>
      {_render_bullets(section_data.get("resumen", []))}
      <div class="stit">Temas cubiertos</div>
      {_render_bullets(section_data.get("temas", []))}
      <div class="stit">Tono general</div>
      {_render_bullets(section_data.get("tono", []))}
      {error_html}
      <div class="stit" style="color:#c8102e;">Señales de compra</div>
      {_render_signals(section_data.get("senales", []))}
    </div>
    <div class="tbl-cell col-r">
      <div class="stit stit-first" style="color:#c8102e;">Estado MEDDIC</div>
      {_render_meddic(section_data.get("meddic", []))}
      <div class="stit" style="color:#c8102e;">Objeciones · Ángulos de respuesta</div>
      {_render_objeciones(section_data.get("objeciones", []))}
      <div class="stit" style="color:#c8102e;">Probabilidad y riesgo</div>
      <div class="prob tbl">
        <div class="tbl-cell prob-num">{prob_num}<small>%</small></div>
        <div class="tbl-cell prob-txt">{_allow_bold(section_data.get("prob_texto", ""))}</div>
      </div>
    </div>
  </div>
</div>'''

    html = (
        '<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><style>'
        + CSS_BASE
        + "</style></head><body>"
        + page_html
        + "</body></html>"
    )

    slug = company.lower().replace(" ", "-")
    return {
        "type": "pdf",
        "pdf_bytes": weasyprint.HTML(string=html).write_pdf(),
        "filename": f"analisis-demo-{slug}.pdf",
        "intro": f":bar_chart: *Análisis de la demo* — {company} · {data['demo_date_short']}",
    }
