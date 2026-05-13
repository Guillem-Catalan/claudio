"""
Generate a 2-page follow-up PDF from Claude's structured output.
Page 1: One-pager analysis (resumen, temas, tono, error, señales, MEDDIC, objeciones, probabilidad)
Page 2: Next step — dynamic layout based on type (email / llamada / reunión)

All layout uses display:table for WeasyPrint compatibility.
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
}
.page { background: #fff; width: 100%; height: 1123px; overflow: hidden; }
.page-2 { page-break-before: always; }

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
.col-l { width: 50%; padding-right: 32px; padding-top: 24px; border-right: .5px solid #e4e3de; overflow: hidden; }
.col-r { width: 50%; padding-left: 32px; padding-top: 24px; overflow: hidden; }

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
.meddic-table td { padding: 8px 0; vertical-align: top; }
.meddic-label {
    font-family: 'Courier New', Courier, monospace;
    font-size: 10px; font-weight: 500; text-transform: uppercase;
    letter-spacing: 1px; color: #8e8d88; width: 90px; padding-top: 10px;
}
.meddic-icon { font-size: 14px; width: 22px; padding-top: 9px; }
.meddic-txt { font-size: 11px; line-height: 1.6; color: #5c5b57; }
.meddic-txt b { color: #1a1a18; font-weight: 600; }

/* ── HIGHLIGHT BOX ── */
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
.sig-tag-cell { width: 55px; padding-right: 6px; }
.sig-tag {
    font-size: 9px; font-weight: 600; text-transform: uppercase;
    letter-spacing: .8px; padding: 2px 8px;
}
.sig-tag-m { background: #edf7f1; color: #12593a; }
.sig-tag-d { background: #fef6e8; color: #7a4900; }
.sig-txt { font-size: 11px; line-height: 1.6; color: #5c5b57; }
.sig-txt b { color: #1a1a18; font-weight: 600; }

/* ── OBJECTIONS ── */
.obj-card { background: #faf9f6; padding: 12px 16px; margin-top: 10px; }
.obj-q { font-size: 11.5px; font-weight: 600; color: #1a1a18; margin-bottom: 6px; }
.obj-a { font-size: 10.5px; line-height: 1.6; color: #5c5b57; }
.obj-a b { color: #1a1a18; font-weight: 500; }

/* ── PROBABILITY ── */
.prob { background: #fdf0f0; padding: 16px 20px; margin-top: 16px; }
.prob-num { font-size: 36px; font-weight: 700; color: #c8102e; line-height: 1; width: 70px; }
.prob-num small { font-size: 16px; }
.prob-txt { font-size: 11px; line-height: 1.6; color: #5c5b57; }
.prob-txt b { color: #1a1a18; font-weight: 600; }

/* ── PAGE 2 HEADER ── */
.p2-head { padding: 18px 32px 14px; border-bottom: 1px solid #e4e3de; }
.p2h-left { width: 75%; }
.p2h-right { text-align: right; vertical-align: bottom; }
.p2h-label { font-size: 8px; font-weight: 600; letter-spacing: 2px; text-transform: uppercase; color: #c8102e; margin-bottom: 5px; }
.p2h-title { font-size: 22px; font-weight: 600; letter-spacing: -.04em; color: #1a1a18; line-height: 1; }
.p2h-sub { font-size: 11px; color: #8e8d88; font-weight: 300; margin-top: 4px; }
.p2h-badge { background: #fdf0f0; border: 1px solid #ffccd4; padding: 5px 12px; font-size: 10px; font-weight: 500; color: #c8102e; }

/* ── EMAIL MOCK ── */
.email-wrap { padding: 14px 32px 0; }
.mail-window { border: 1px solid #dddde8; overflow: hidden; }
.mail-bar { background: #f5f5f8; border-bottom: 1px solid #dddde8; padding: 7px 14px; }
.mail-dot { width: 10px; height: 10px; display: inline-block; margin-right: 4px; }
.mail-bar-text { font-size: 11px; color: #8888a8; margin-left: 6px; }
.mail-fields { border-bottom: 1px solid #ebebeb; }
.mf { border-bottom: 1px solid #f0f0f5; }
.mf table { width: 100%; border-collapse: collapse; }
.mf td { padding: 6px 14px; font-size: 10.5px; }
.mf-k { color: #9999aa; width: 52px; }
.mf-v { color: #1a1a18; }
.mf-v.subj { font-weight: 500; }
.mail-body { padding: 13px 16px; }
.mail-body p { font-size: 11px; line-height: 1.6; color: #2a2a3c; margin-bottom: 8px; font-weight: 300; }
.mail-body p:last-child { margin-bottom: 0; }
.mail-body p strong { font-weight: 500; color: #1a1a18; }
.mail-body ul { list-style: none; margin: 0 0 8px; padding: 0; }
.mail-body li { font-size: 11px; line-height: 1.6; color: #2a2a3c; font-weight: 300; padding-left: 14px; }

/* ── CALL/MEETING SECTIONS ── */
.p2-body { padding: 20px 32px; }
.p2-stit {
    font-family: 'Courier New', Courier, monospace;
    font-size: 9px; font-weight: 500; text-transform: uppercase;
    letter-spacing: 2px; color: #c8102e;
    margin-bottom: 8px; margin-top: 20px;
}
.p2-stit-first { margin-top: 0; }
.p2-block { background: #faf9f6; padding: 14px 18px; margin-bottom: 8px; font-size: 11.5px; line-height: 1.6; color: #5c5b57; }
.p2-block b { color: #1a1a18; font-weight: 600; }
.p2-numbered { width: 100%; border-collapse: collapse; }
.p2-numbered td { padding: 8px 0; vertical-align: top; border-bottom: .5px solid #f0efe9; font-size: 11px; line-height: 1.55; color: #5c5b57; }
.p2-numbered tr:last-child td { border-bottom: none; }
.p2-num { width: 28px; font-size: 14px; font-weight: 600; color: #c8102e; }
.p2-q { font-weight: 500; color: #1a1a18; }
.p2-why { font-size: 10.5px; color: #8e8d88; margin-top: 2px; }
.p2-obj-handle { font-size: 10.5px; color: #5c5b57; margin-top: 2px; }
.p2-time { width: 55px; font-size: 10px; font-weight: 600; color: #c8102e; letter-spacing: .5px; }

/* ── NOTE BLOCKS ── */
.note-block { margin: 10px 32px 0; padding: 9px 14px; font-size: 10.5px; line-height: 1.5; font-weight: 300; }
.note-block.blue { background: #f0f7ff; border-left: 3px solid #3b82f6; color: #1e3a5f; }
.note-block.red { background: #fdf0f0; border-left: 3px solid #c8102e; color: #3a1a22; }
.note-block strong, .note-block b { font-weight: 500; color: #1a1a18; }
"""


def _esc(text) -> str:
    if not text:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _allow_bold(text) -> str:
    if not text:
        return ""
    s = str(text)
    s = s.replace("<b>", "\x00B\x00").replace("</b>", "\x00/B\x00")
    s = s.replace("<strong>", "\x00S\x00").replace("</strong>", "\x00/S\x00")
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    s = s.replace("\x00B\x00", "<b>").replace("\x00/B\x00", "</b>")
    s = s.replace("\x00S\x00", "<strong>").replace("\x00/S\x00", "</strong>")
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


def _render_page1(brief, company, demo_datetime, next_step, amount_str, partner) -> str:
    esc_company = _esc(company)
    probabilidad = _esc(brief.get("probabilidad", "?"))
    engagement = _esc(brief.get("engagement", "?"))
    etapa = _esc(brief.get("etapa", "?"))
    prob_num = _esc(brief.get("prob_num", "?"))

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

    return f'''<div class="page">
  <div class="hdr">
    <div class="tbl">
      <div class="tbl-cell hdr-left">
        <div class="brand">Factorial</div>
        <div class="type">Follow-up Brief</div>
        <div class="name">{esc_company}</div>
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
      {_render_bullets(brief.get("resumen", []))}
      <div class="stit">Temas cubiertos</div>
      {_render_bullets(brief.get("temas", []))}
      <div class="stit">Tono general</div>
      {_render_bullets(brief.get("tono", []))}
      {error_html}
      <div class="stit" style="color:#c8102e;">Señales de compra</div>
      {_render_signals(brief.get("senales", []))}
    </div>
    <div class="tbl-cell col-r">
      <div class="stit stit-first" style="color:#c8102e;">Estado MEDDIC</div>
      {_render_meddic(brief.get("meddic", []))}
      <div class="stit" style="color:#c8102e;">Objeciones · Ángulos de respuesta</div>
      {_render_objeciones(brief.get("objeciones", []))}
      <div class="stit" style="color:#c8102e;">Probabilidad y riesgo</div>
      <div class="prob tbl">
        <div class="tbl-cell prob-num">{prob_num}<small>%</small></div>
        <div class="tbl-cell prob-txt">{_allow_bold(brief.get("prob_texto", ""))}</div>
      </div>
    </div>
  </div>
</div>'''


def _render_page2_email(brief, company, pae_name, contact) -> str:
    email_to = _esc(brief.get("email_to") or contact.get("email") or "")
    p2_sub = f"Quién · {_esc(pae_name)} → {_esc(contact.get('name', '?'))} &nbsp;&middot;&nbsp; Canal · Email &nbsp;&middot;&nbsp; Cuándo · {_esc(brief.get('next_step_badge', '48h post-demo'))}"
    return f'''<div class="page page-2">
  <div class="p2-head tbl">
    <div class="tbl-cell p2h-left">
      <div class="p2h-label">Email de follow-up</div>
      <div class="p2h-title">Listo para copy-paste</div>
      <div class="p2h-sub">{p2_sub}</div>
    </div>
    <div class="tbl-cell p2h-right">
      <span class="p2h-badge">{_esc(brief.get("next_step_badge", "48h post-demo"))}</span>
    </div>
  </div>
  <div class="email-wrap">
    <div class="mail-window">
      <div class="mail-bar">
        <span class="mail-dot" style="background:#FF5F57;">&nbsp;</span>
        <span class="mail-dot" style="background:#FEBC2E;">&nbsp;</span>
        <span class="mail-dot" style="background:#28C840;">&nbsp;</span>
        <span class="mail-bar-text">Nuevo mensaje</span>
      </div>
      <div class="mail-fields">
        <div class="mf"><table><tr><td class="mf-k">De</td><td class="mf-v">{_esc(pae_name)} · Factorial</td></tr></table></div>
        <div class="mf"><table><tr><td class="mf-k">Para</td><td class="mf-v">{email_to}</td></tr></table></div>
        <div class="mf"><table><tr><td class="mf-k">Asunto</td><td class="mf-v subj">{_esc(brief.get("email_subject", ""))}</td></tr></table></div>
      </div>
      <div class="mail-body">{brief.get("email_body", "")}</div>
    </div>
  </div>
  <div class="note-block red"><b>Objetivo del email.</b> {_esc(brief.get("email_objetivo", ""))}</div>
  <div class="note-block blue"><b>Tono.</b> {_esc(brief.get("email_tono", ""))}</div>
</div>'''


def _render_page2_llamada(brief, company, pae_name, contact) -> str:
    p2_sub = f"Quién · {_esc(pae_name)} → {_esc(contact.get('name', '?'))} &nbsp;&middot;&nbsp; Canal · Llamada &nbsp;&middot;&nbsp; Cuándo · {_esc(brief.get('next_step_badge', ''))}"

    preguntas_html = ""
    for i, p in enumerate(brief.get("call_preguntas", []), 1):
        preguntas_html += (
            f'<tr>'
            f'<td class="p2-num">{i}.</td>'
            f'<td><div class="p2-q">{_esc(p.get("pregunta", ""))}</div>'
            f'<div class="p2-why">{_esc(p.get("por_que", ""))}</div></td>'
            f'</tr>'
        )

    objeciones_html = ""
    for o in brief.get("call_objeciones", []):
        objeciones_html += (
            f'<div class="obj-card">'
            f'<div class="obj-q">«{_esc(o.get("objecion", ""))}»</div>'
            f'<div class="obj-a">{_allow_bold(o.get("manejo", ""))}</div>'
            f'</div>'
        )

    return f'''<div class="page page-2">
  <div class="p2-head tbl">
    <div class="tbl-cell p2h-left">
      <div class="p2h-label">Guión de llamada</div>
      <div class="p2h-title">Preparación para la llamada</div>
      <div class="p2h-sub">{p2_sub}</div>
    </div>
    <div class="tbl-cell p2h-right">
      <span class="p2h-badge">{_esc(brief.get("next_step_badge", ""))}</span>
    </div>
  </div>
  <div class="p2-body">
    <div class="p2-stit p2-stit-first">Objetivo</div>
    <div class="p2-block">{_allow_bold(brief.get("call_objetivo", ""))}</div>

    <div class="p2-stit">Apertura</div>
    <div class="p2-block">«{_allow_bold(brief.get("call_apertura", ""))}»</div>

    <div class="p2-stit">Preguntas clave (por orden de prioridad)</div>
    <table class="p2-numbered">{preguntas_html}</table>

    <div class="p2-stit">Objeciones probables</div>
    {objeciones_html}

    <div class="p2-stit">Cierre</div>
    <div class="p2-block">{_allow_bold(brief.get("call_cierre", ""))}</div>
  </div>
  <div class="note-block red"><b>Objetivo de la llamada.</b> {_esc(brief.get("call_objetivo_nota", ""))}</div>
  <div class="note-block blue"><b>Tono.</b> {_esc(brief.get("call_tono", ""))}</div>
</div>'''


def _render_page2_reunion(brief, company, pae_name, contact) -> str:
    p2_sub = f"Quién · {_esc(pae_name)} → {_esc(contact.get('name', '?'))} &nbsp;&middot;&nbsp; Canal · Presencial &nbsp;&middot;&nbsp; Cuándo · {_esc(brief.get('next_step_badge', ''))}"

    agenda_html = ""
    for i, a in enumerate(brief.get("meeting_agenda", []), 1):
        agenda_html += (
            f'<tr>'
            f'<td class="p2-num">{i}.</td>'
            f'<td class="p2-time">[{_esc(a.get("tiempo", ""))}]</td>'
            f'<td><div class="p2-q">{_esc(a.get("punto", ""))}</div>'
            f'<div class="p2-why">{_esc(a.get("detalle", ""))}</div></td>'
            f'</tr>'
        )

    preguntas_html = ""
    for i, p in enumerate(brief.get("meeting_preguntas", []), 1):
        preguntas_html += (
            f'<tr>'
            f'<td class="p2-num">{i}.</td>'
            f'<td><div class="p2-q">{_esc(p.get("pregunta", ""))}</div>'
            f'<div class="p2-why">{_esc(p.get("por_que", ""))}</div></td>'
            f'</tr>'
        )

    materiales_rows = ""
    for m in brief.get("meeting_materiales", []):
        materiales_rows += f'<tr><td class="bi-dash">&mdash;</td><td>{_esc(m)}</td></tr>'
    materiales_html = f'<table class="bi-table">{materiales_rows}</table>' if materiales_rows else ""

    return f'''<div class="page page-2">
  <div class="p2-head tbl">
    <div class="tbl-cell p2h-left">
      <div class="p2h-label">Prep reunión</div>
      <div class="p2h-title">Preparación para la reunión</div>
      <div class="p2h-sub">{p2_sub}</div>
    </div>
    <div class="tbl-cell p2h-right">
      <span class="p2h-badge">{_esc(brief.get("next_step_badge", ""))}</span>
    </div>
  </div>
  <div class="p2-body">
    <div class="p2-stit p2-stit-first">Objetivo</div>
    <div class="p2-block">{_allow_bold(brief.get("meeting_objetivo", ""))}</div>

    <div class="p2-stit">Agenda</div>
    <table class="p2-numbered">{agenda_html}</table>

    <div class="p2-stit">Preguntas clave</div>
    <table class="p2-numbered">{preguntas_html}</table>

    <div class="p2-stit">Materiales</div>
    {materiales_html}
  </div>
  <div class="note-block red"><b>Objetivo.</b> {_esc(brief.get("meeting_objetivo_nota", ""))}</div>
  <div class="note-block blue"><b>Tono.</b> {_esc(brief.get("meeting_tono", ""))}</div>
</div>'''


def generate_pdf(
    brief: dict,
    company: str,
    demo_datetime: str,
    next_step: str,
    amount_str: str,
    partner: str,
    pae_name: str,
    contact: dict | None = None,
) -> bytes:
    contact = contact or {"name": "?", "email": "", "jobtitle": "", "phone": ""}

    page1 = _render_page1(brief, company, demo_datetime, next_step, amount_str, partner)

    step_type = brief.get("next_step_type", "email")
    if step_type == "llamada":
        page2 = _render_page2_llamada(brief, company, pae_name, contact)
    elif step_type == "reunión":
        page2 = _render_page2_reunion(brief, company, pae_name, contact)
    else:
        page2 = _render_page2_email(brief, company, pae_name, contact)

    html = (
        '<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><style>'
        + _CSS
        + "</style></head><body>"
        + page1
        + page2
        + "</body></html>"
    )

    return weasyprint.HTML(string=html).write_pdf()
