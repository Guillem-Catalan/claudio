"""
Generate a single-page follow-up PDF from Claude's structured output.
Sections: header, KPI bar, 2-column body (resumen/temas/tono/error/señales | MEDDIC/objeciones/probabilidad).

All layout uses display:table for WeasyPrint compatibility.
Design adapted from Factorial follow-up brief template.
"""

import weasyprint

_CSS = """\
@page { size: A4; margin: 0; }

* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    font-size: 12.5px;
    line-height: 1.55;
    color: #1a1a18;
    background: #faf9f6;
    -webkit-font-smoothing: antialiased;
}
.page { background: #fff; width: 100%; }

/* ── TABLE LAYOUT ── */
.tbl { display: table; width: 100%; }
.tbl-cell { display: table-cell; vertical-align: top; }

/* ── HEADER ── */
.hdr { padding: 28px 40px 0; }
.hdr-left { width: 65%; }
.hdr-right { text-align: right; vertical-align: top; }
.brand { font-size: 13px; font-weight: 600; color: #c8102e; letter-spacing: .3px; }
.type { font-size: 10px; text-transform: uppercase; letter-spacing: 2px; color: #8e8d88; margin-top: 1px; }
.name { font-size: 32px; font-weight: 700; letter-spacing: -.5px; margin-top: 2px; }
.dates { font-size: 14px; font-weight: 500; line-height: 1.4; }
.dates .sub { font-size: 10.5px; color: #8e8d88; font-weight: 400; }

/* ── KPI BAR ── */
.kpi { border-top: 1.5px solid #1a1a18; border-bottom: 1.5px solid #e4e3de; margin-top: 16px; }
.kpi table { width: 100%; border-collapse: collapse; }
.kpi td { padding: 10px 14px; vertical-align: top; width: 20%; }
.kpi-lbl { font-size: 8.5px; text-transform: uppercase; letter-spacing: 1.5px; color: #8e8d88; font-weight: 600; }
.kpi-val { font-size: 16px; font-weight: 600; margin-top: 1px; }
.kpi-val.red { color: #c8102e; }
.kpi-val.amb { color: #a86400; }

/* ── BODY 2-COL ── */
.body-grid { padding: 0 40px 40px; }
.col-l { width: 50%; padding-right: 32px; padding-top: 24px; border-right: .5px solid #e4e3de; }
.col-r { width: 50%; padding-left: 32px; padding-top: 24px; }

/* ── SECTION TITLES ── */
.stit {
    font-family: 'Courier New', Courier, monospace;
    font-size: 9px; font-weight: 500; text-transform: uppercase;
    letter-spacing: 2px; color: #c8102e;
    margin-bottom: 10px; margin-top: 24px;
}
.stit-first { margin-top: 0; }

/* ── BULLET ITEMS ── */
.bi-table { width: 100%; border-collapse: collapse; }
.bi-table td { font-size: 11.5px; line-height: 1.6; color: #5c5b57; padding: 3px 0; vertical-align: top; }
.bi-dash { width: 14px; color: #8e8d88; }
.bi-table b { color: #1a1a18; font-weight: 600; }

/* ── MEDDIC ── */
.meddic-table { width: 100%; border-collapse: collapse; }
.meddic-table tr { border-bottom: .5px solid #f0efe9; }
.meddic-table tr:last-child { border-bottom: none; }
.meddic-table td { padding: 10px 0; vertical-align: top; }
.meddic-label {
    font-family: 'Courier New', Courier, monospace;
    font-size: 10px; font-weight: 500; text-transform: uppercase;
    letter-spacing: 1px; color: #8e8d88; width: 100px; padding-top: 12px;
}
.meddic-icon { font-size: 14px; width: 24px; padding-top: 11px; }
.meddic-txt { font-size: 11px; line-height: 1.6; color: #5c5b57; }
.meddic-txt b { color: #1a1a18; font-weight: 600; }

/* ── HIGHLIGHT BOX (error critico) ── */
.hbox {
    border-left: 3px solid #c8102e; background: #fdf0f0;
    padding: 12px 16px; margin-top: 12px;
}
.hbox .ht {
    font-size: 10px; font-weight: 600; text-transform: uppercase;
    letter-spacing: 1px; color: #c8102e; margin-bottom: 4px;
}
.hbox p { font-size: 11px; line-height: 1.6; color: #5c5b57; }
.hbox p b { color: #1a1a18; font-weight: 600; }

/* ── SIGNALS ── */
.sig-table { width: 100%; border-collapse: collapse; }
.sig-table td { padding: 5px 0; vertical-align: top; }
.sig-tag-cell { width: 60px; padding-right: 6px; }
.sig-tag {
    font-size: 9px; font-weight: 600; text-transform: uppercase;
    letter-spacing: .8px; padding: 2px 8px;
}
.sig-tag-m { background: #edf7f1; color: #12593a; }
.sig-tag-d { background: #fef6e8; color: #7a4900; }
.sig-txt { font-size: 11px; line-height: 1.6; color: #5c5b57; }
.sig-txt b { color: #1a1a18; font-weight: 600; }

/* ── OBJECTIONS ── */
.obj-card {
    background: #faf9f6; padding: 12px 16px; margin-top: 10px;
}
.obj-q { font-size: 11.5px; font-weight: 600; color: #1a1a18; margin-bottom: 6px; }
.obj-a { font-size: 10.5px; line-height: 1.6; color: #5c5b57; }
.obj-a b { color: #1a1a18; font-weight: 500; }

/* ── PROBABILITY ── */
.prob {
    background: #fdf0f0; padding: 16px 20px; margin-top: 16px;
}
.prob-num { font-size: 36px; font-weight: 700; color: #c8102e; line-height: 1; width: 70px; }
.prob-num small { font-size: 16px; }
.prob-txt { font-size: 11px; line-height: 1.6; color: #5c5b57; }
.prob-txt b { color: #1a1a18; font-weight: 600; }
"""


def _esc(text) -> str:
    if not text:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _allow_bold(text) -> str:
    """Escape HTML but preserve <b>...</b> tags."""
    if not text:
        return ""
    s = str(text)
    s = s.replace("<b>", "\x00B\x00").replace("</b>", "\x00/B\x00")
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    s = s.replace("\x00B\x00", "<b>").replace("\x00/B\x00", "</b>")
    return s


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


def generate_pdf(
    brief: dict,
    company: str,
    demo_datetime: str,
    next_step: str,
    amount_str: str,
    partner: str,
    pae_name: str,
) -> bytes:
    esc_company = _esc(company)
    esc_demo_dt = _esc(demo_datetime)
    esc_next_step = _esc(next_step)
    esc_amount = _esc(amount_str)
    esc_partner = _esc(partner)

    probabilidad = _esc(brief.get("probabilidad", "?"))
    engagement = _esc(brief.get("engagement", "?"))
    etapa = _esc(brief.get("etapa", "?"))

    resumen_html = _render_bullets(brief.get("resumen", []))
    temas_html = _render_bullets(brief.get("temas", []))
    tono_html = _render_bullets(brief.get("tono", []))
    senales_html = _render_signals(brief.get("senales", []))
    meddic_html = _render_meddic(brief.get("meddic", []))
    objeciones_html = _render_objeciones(brief.get("objeciones", []))

    prob_num = _esc(brief.get("prob_num", "?"))
    prob_texto = _allow_bold(brief.get("prob_texto", ""))

    error_critico = brief.get("error_critico")
    error_html = ""
    if error_critico:
        error_html = (
            f'<div class="stit" style="color:#c8102e;">Error crítico en demo</div>'
            f'<div class="hbox">'
            f'<div class="ht">A resolver en el follow-up</div>'
            f'<p>{_allow_bold(error_critico)}</p>'
            f'</div>'
        )

    page = f'''<div class="page">

  <div class="hdr">
    <div class="tbl">
      <div class="tbl-cell hdr-left">
        <div class="brand">Factorial</div>
        <div class="type">Follow-up Brief</div>
        <div class="name">{esc_company}</div>
      </div>
      <div class="tbl-cell hdr-right">
        <div class="dates">
          {esc_demo_dt}<br>
          <span class="sub">Next step · {esc_next_step}</span>
        </div>
      </div>
    </div>
  </div>

  <div class="kpi"><table>
    <tr>
      <td style="padding-left:40px"><div class="kpi-lbl">MRR</div><div class="kpi-val red">{esc_amount}</div></td>
      <td><div class="kpi-lbl">Probabilidad</div><div class="kpi-val amb">{probabilidad}</div></td>
      <td><div class="kpi-lbl">Engagement</div><div class="kpi-val">{engagement}</div></td>
      <td><div class="kpi-lbl">Partner</div><div class="kpi-val">{esc_partner}</div></td>
      <td><div class="kpi-lbl">Etapa</div><div class="kpi-val">{etapa}</div></td>
    </tr>
  </table></div>

  <div class="body-grid tbl">
    <div class="tbl-cell col-l">

      <div class="stit stit-first">Resumen de la demo</div>
      {resumen_html}

      <div class="stit">Temas cubiertos</div>
      {temas_html}

      <div class="stit">Tono general</div>
      {tono_html}

      {error_html}

      <div class="stit" style="color:#c8102e;">Señales de compra</div>
      {senales_html}

    </div>

    <div class="tbl-cell col-r">

      <div class="stit stit-first" style="color:#c8102e;">Estado MEDDIC</div>
      {meddic_html}

      <div class="stit" style="color:#c8102e;">Objeciones · Ángulos de respuesta</div>
      {objeciones_html}

      <div class="stit" style="color:#c8102e;">Probabilidad y riesgo</div>
      <div class="prob tbl">
        <div class="tbl-cell prob-num">{prob_num}<small>%</small></div>
        <div class="tbl-cell prob-txt">{prob_texto}</div>
      </div>

    </div>
  </div>

</div>'''

    html = (
        '<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><style>'
        + _CSS
        + "</style></head><body>"
        + page
        + "</body></html>"
    )

    return weasyprint.HTML(string=html).write_pdf()
