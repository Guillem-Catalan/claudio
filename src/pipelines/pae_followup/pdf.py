"""
Generate a 2-page follow-up PDF from Claude's structured output.
Page 1: Demo summary, MEDDIC, signals, objections, action plan
Page 2: Ready-to-send follow-up email draft

All layout uses display:table for bulletproof WeasyPrint rendering.
"""

from datetime import date

import weasyprint

_MESES_CORTO = {
    1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
    7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic",
}

_CSS = """\
@page { size: A4; margin: 0; }

* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    font-size: 11px;
    line-height: 1.5;
    color: #0F0F1A;
    background: #fff;
    overflow-wrap: break-word;
    word-wrap: break-word;
}
.page { background: #fff; width: 100%; }
.page-2 { page-break-before: always; }

/* ── TABLE LAYOUT ── */
.tbl { display: table; width: 100%; }
.tbl-cell { display: table-cell; vertical-align: top; }

/* ── HEADER (dark) ── */
.pg-head { background: #0F0F1A; padding: 20px 32px 22px; }
.pg-head .tbl-cell { vertical-align: bottom; }
.ph-brand { font-size: 11px; font-weight: 500; color: #FF3B5C; }
.ph-type { font-size: 8px; letter-spacing: 0.18em; text-transform: uppercase; color: rgba(255,255,255,0.3); margin-top: 2px; }
.ph-company { font-size: 22px; font-weight: 600; letter-spacing: -0.04em; color: #fff; line-height: 1.1; margin-top: 4px; }
.ph-right { text-align: right; }
.ph-date { font-size: 18px; font-weight: 300; letter-spacing: -0.03em; color: #fff; line-height: 1.1; }
.ph-sub { font-size: 10px; color: rgba(255,255,255,0.35); margin-top: 4px; }

/* ── KPI BAR ── */
.kpi { border-bottom: 1px solid #E8E8F0; }
.kpi table { width: 100%; border-collapse: collapse; }
.kpi td { padding: 8px 14px; border-right: 1px solid #E8E8F0; vertical-align: top; width: 20%; }
.kpi td:last-child { border-right: none; }
.kpi-lbl { font-size: 7.5px; letter-spacing: 0.16em; text-transform: uppercase; color: #AAAABC; font-weight: 600; margin-bottom: 3px; }
.kpi-val { font-size: 11.5px; font-weight: 500; letter-spacing: -0.02em; color: #0F0F1A; }
.kpi-val.red { color: #FF3B5C; }
.kpi-val.warn { color: #D97706; }

/* ── BODY 2-COL ── */
.body-grid { padding: 0; }
.col-left { width: 50%; padding: 14px 16px; border-right: 1px solid #E8E8F0; }
.col-right { width: 50%; padding: 14px 16px; }

/* ── SECTIONS ── */
.sec { margin-bottom: 11px; }
.sec-label {
    font-size: 7.5px; font-weight: 600; letter-spacing: 0.2em;
    text-transform: uppercase; color: #FF3B5C;
    margin-bottom: 7px; padding-bottom: 3px;
    border-bottom: 1px solid #F0F0F5;
}

/* ── BULLET LIST (table-based) ── */
.blist { border-collapse: collapse; width: 100%; }
.blist td { font-size: 10.5px; line-height: 1.45; color: #2A2A3C; font-weight: 300; padding: 2px 0; vertical-align: top; }
.blist .dash { width: 14px; color: #FF3B5C; font-size: 10px; }
.blist strong { font-weight: 500; color: #0F0F1A; }

/* ── MEDDIC STATUS ── */
.status-grid table { width: 100%; border-collapse: separate; border-spacing: 0 3px; }
.status-grid td { padding: 5px 8px; background: #F7F7FB; font-size: 10px; line-height: 1.4; vertical-align: top; }
.sr-k { font-size: 8px; font-weight: 600; letter-spacing: 0.12em; text-transform: uppercase; color: #8888A8; width: 70px; }
.sr-dot { width: 18px; font-size: 10px; text-align: center; }
.sr-v { color: #2A2A3C; font-weight: 300; }
.sr-v strong { font-weight: 500; color: #0F0F1A; }

/* ── ALERT BLOCKS ── */
.alert {
    padding: 8px 11px; margin-bottom: 6px;
    border-left: 3px solid #D97706; background: #FFFBEB;
    font-size: 10.5px; line-height: 1.5; color: #3A3A52; font-weight: 300;
}
.alert.red { border-color: #FF3B5C; background: #FFF2F4; }
.alert-title {
    font-size: 8px; font-weight: 700; letter-spacing: 0.14em;
    text-transform: uppercase; color: #D97706; margin-bottom: 4px;
}
.alert.red .alert-title { color: #FF3B5C; }
.alert strong { font-weight: 500; color: #0F0F1A; }

/* ── OBJECTIONS ── */
.obj { padding: 7px 10px; border: 1px solid #E8E8F0; margin-bottom: 4px; font-size: 10px; line-height: 1.45; }
.obj-q { font-weight: 500; color: #0F0F1A; margin-bottom: 2px; font-size: 10.5px; }
.obj-a { color: #5A5A72; font-weight: 300; }
.obj-a strong { font-weight: 500; color: #0F0F1A; }

/* ── SIGNALS ── */
.sig-table { width: 100%; border-collapse: separate; border-spacing: 0 4px; }
.sig-table td { padding: 6px 9px; background: #F7F7FB; font-size: 10.5px; line-height: 1.4; color: #2A2A3C; font-weight: 300; vertical-align: top; }
.sig-tag { font-size: 8px; font-weight: 600; letter-spacing: 0.1em; text-transform: uppercase; width: 50px; }
.sig-tag-g { background: #DCFCE7; color: #16A34A; padding: 2px 6px; }
.sig-tag-y { background: #FEF9C3; color: #A16207; padding: 2px 6px; }

/* ── PROBABILITY ── */
.prob-row { margin-bottom: 6px; background: #FFFBEB; border: 1px solid #FDE68A; padding: 9px 12px; }
.prob-num { font-size: 28px; font-weight: 600; letter-spacing: -0.04em; color: #D97706; line-height: 1; width: 60px; }
.prob-num small { font-size: 14px; }
.prob-text { font-size: 10.5px; color: #3A3A52; line-height: 1.45; font-weight: 300; }
.prob-text strong { font-weight: 500; color: #0F0F1A; }

/* ── PLAN STEPS ── */
.plan-table { width: 100%; border-collapse: separate; border-spacing: 0 5px; }
.plan-table td { padding: 7px 9px; background: #F7F7FB; font-size: 10.5px; vertical-align: top; }
.plan-when { font-size: 8.5px; font-weight: 700; color: #FF3B5C; letter-spacing: 0.06em; text-transform: uppercase; line-height: 1.4; width: 72px; }
.plan-text { color: #2A2A3C; line-height: 1.45; font-weight: 300; }
.plan-text strong { font-weight: 500; color: #0F0F1A; }

/* ── CONTACTS ── */
.contact-block { background: #F7F7FB; padding: 10px 12px; margin-bottom: 6px; }
.cb-tag { font-size: 8px; font-weight: 600; letter-spacing: 0.1em; text-transform: uppercase; background: #FF3B5C; color: #fff; padding: 2px 6px; }
.cb-tag.dark { background: #0F0F1A; }
.cb-name { font-size: 13px; font-weight: 600; letter-spacing: -0.03em; color: #0F0F1A; margin-top: 4px; }
.cb-role { font-size: 9.5px; color: #8888A8; margin-bottom: 5px; }
.cb-row { font-size: 10px; color: #3A3A52; line-height: 1.6; font-family: 'Courier New', monospace; }

/* ── FOOTER ── */
.pfoot { padding: 8px 32px; border-top: 1px solid #E8E8F0; font-size: 8.5px; color: #AAAABC; letter-spacing: 0.04em; }
.pfoot-left { width: 70%; }
.pfoot-right { text-align: right; }

/* ── PAGE 2 ── */
.p2-head { padding: 18px 32px 14px; border-bottom: 1px solid #E8E8F0; }
.p2h-left { width: 75%; }
.p2h-right { text-align: right; vertical-align: bottom; }
.p2h-label { font-size: 8px; font-weight: 600; letter-spacing: 0.2em; text-transform: uppercase; color: #FF3B5C; margin-bottom: 5px; }
.p2h-title { font-size: 22px; font-weight: 600; letter-spacing: -0.04em; color: #0F0F1A; line-height: 1; }
.p2h-sub { font-size: 11px; color: #8888A8; font-weight: 300; margin-top: 4px; }
.p2h-badge { background: #FFF2F4; border: 1px solid #FFCCD4; padding: 5px 12px; font-size: 10px; font-weight: 500; color: #FF3B5C; }

/* ── EMAIL MOCK ── */
.email-wrap { padding: 14px 32px 0; }
.mail-window { border: 1px solid #DDDDE8; overflow: hidden; }
.mail-bar { background: #F5F5F8; border-bottom: 1px solid #DDDDE8; padding: 7px 14px; }
.mail-dot { width: 10px; height: 10px; display: inline-block; margin-right: 4px; }
.mail-bar-text { font-size: 11px; color: #8888A8; margin-left: 6px; }
.mail-fields { border-bottom: 1px solid #EBEBEB; }
.mf { border-bottom: 1px solid #F0F0F5; }
.mf table { width: 100%; border-collapse: collapse; }
.mf td { padding: 6px 14px; font-size: 10.5px; }
.mf-k { color: #9999AA; width: 52px; }
.mf-v { color: #0F0F1A; }
.mf-v.subj { font-weight: 500; }
.mail-body { padding: 13px 16px; }
.mail-body p { font-size: 11px; line-height: 1.6; color: #2A2A3C; margin-bottom: 8px; font-weight: 300; }
.mail-body p:last-child { margin-bottom: 0; }
.mail-body p strong { font-weight: 500; color: #0F0F1A; }
.mail-body ul { list-style: none; margin: 0 0 8px; padding: 0; }
.mail-body li { font-size: 11px; line-height: 1.6; color: #2A2A3C; font-weight: 300; padding-left: 14px; }

/* ── NOTE BLOCKS ── */
.note-block { margin: 10px 32px 0; padding: 9px 14px; font-size: 10.5px; line-height: 1.5; font-weight: 300; }
.note-block.blue { background: #F0F7FF; border-left: 3px solid #3B82F6; color: #1E3A5F; }
.note-block.red { background: #FFF2F4; border-left: 3px solid #FF3B5C; color: #3A1A22; }
.note-block strong { font-weight: 500; color: #0F0F1A; }
"""


def _esc(text) -> str:
    return (str(text) if text else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _blist(items: list[dict], bold_key: str = "bold", text_key: str = "text") -> str:
    if not items:
        return '<table class="blist"><tr><td class="dash">&mdash;</td><td>No hay información disponible</td></tr></table>'
    rows = ""
    for item in items:
        if isinstance(item, str):
            rows += f'<tr><td class="dash">&mdash;</td><td>{_esc(item)}</td></tr>'
        else:
            bold = item.get(bold_key)
            text = item.get(text_key, "")
            if bold:
                rows += f'<tr><td class="dash">&mdash;</td><td><strong>{_esc(bold)}</strong> · {_esc(text)}</td></tr>'
            else:
                rows += f'<tr><td class="dash">&mdash;</td><td>{_esc(text)}</td></tr>'
    return f'<table class="blist">{rows}</table>'


def _render_meddic(meddic: list[dict]) -> str:
    rows = ""
    for row in meddic:
        rows += (
            f'<tr>'
            f'<td class="sr-k">{_esc(row.get("key", ""))}</td>'
            f'<td class="sr-dot">{row.get("dot", "❓")}</td>'
            f'<td class="sr-v">{_esc(row.get("text", ""))}</td>'
            f'</tr>'
        )
    return f'<div class="status-grid"><table>{rows}</table></div>'


def _render_signals(senales: list[dict]) -> str:
    if not senales:
        return ""
    rows = ""
    for s in senales:
        tag_class = "sig-tag-g" if s.get("tag_class") == "g" else "sig-tag-y"
        rows += (
            f'<tr>'
            f'<td class="sig-tag"><span class="{tag_class}">{_esc(s.get("tag", ""))}</span></td>'
            f'<td>{_esc(s.get("text", ""))}</td>'
            f'</tr>'
        )
    return f'<table class="sig-table">{rows}</table>'


def _render_objeciones(objs: list[dict]) -> str:
    if not objs:
        return '<div class="obj"><div class="obj-q">Sin objeciones identificadas</div></div>'
    html = ""
    for o in objs:
        html += (
            f'<div class="obj">'
            f'<div class="obj-q">{_esc(o.get("q", ""))}</div>'
            f'<div class="obj-a">{_esc(o.get("a", ""))}</div>'
            f'</div>'
        )
    return html


def _render_plan(plan: list[dict]) -> str:
    if not plan:
        return ""
    rows = ""
    for step in plan:
        w1 = _esc(step.get("when_line1", ""))
        w2 = _esc(step.get("when_line2", ""))
        text = _esc(step.get("text", ""))
        rows += (
            f'<tr>'
            f'<td class="plan-when">{w1}<br/>{w2}</td>'
            f'<td class="plan-text">{text}</td>'
            f'</tr>'
        )
    return f'<table class="plan-table">{rows}</table>'


def generate_pdf(
    brief: dict,
    company: str,
    demo_datetime: str,
    followup_datetime: str,
    demo_date_short: str,
    amount_str: str,
    partner: str,
    contact: dict,
    pae_name: str,
) -> bytes:
    today = date.today()
    fecha_sub = f"generado {today.day} {_MESES_CORTO[today.month]} {today.year}"

    esc_company = _esc(company)
    esc_demo_dt = _esc(demo_datetime)
    esc_fu_dt = _esc(followup_datetime)
    esc_amount = _esc(amount_str)
    esc_partner = _esc(partner)
    esc_pae = _esc(pae_name)

    probabilidad = _esc(brief.get("probabilidad", "?"))
    engagement = _esc(brief.get("engagement", "?"))
    etapa = _esc(brief.get("etapa", "?"))

    resumen_html = _blist(brief.get("resumen", []))
    temas_html = _blist(brief.get("temas", []))
    tono_html = _blist(brief.get("tono", []))
    senales_html = _render_signals(brief.get("senales", []))
    meddic_html = _render_meddic(brief.get("meddic", []))
    objeciones_html = _render_objeciones(brief.get("objeciones", []))
    plan_html = _render_plan(brief.get("plan", []))

    prob_num = _esc(brief.get("prob_num", "?"))
    prob_texto = _esc(brief.get("prob_texto", ""))
    palanca = _esc(brief.get("palanca", ""))

    error_critico = brief.get("error_critico")
    error_html = ""
    if error_critico:
        error_html = (
            f'<div class="sec">'
            f'<div class="sec-label">Error crítico en demo</div>'
            f'<div class="alert red">'
            f'<div class="alert-title">A resolver en el follow-up</div>'
            f'{_esc(error_critico)}'
            f'</div></div>'
        )

    prospect = contact
    prospect_html = ""
    if prospect.get("name") and prospect["name"] != "?":
        prospect_html = (
            f'<div class="contact-block">'
            f'<span class="cb-tag">Prospect</span>'
            f'<div class="cb-name">{_esc(prospect["name"])}</div>'
            f'<div class="cb-role">{_esc(prospect.get("jobtitle", ""))}</div>'
            f'<div class="cb-row">'
        )
        if prospect.get("email"):
            prospect_html += _esc(prospect["email"])
        if prospect.get("phone"):
            prospect_html += f'<br/>{_esc(prospect["phone"])}'
        prospect_html += '</div></div>'

    email_to = brief.get("email_to") or contact.get("email") or ""
    email_subject = brief.get("email_subject", "")
    email_body = brief.get("email_body", "")
    objetivo_email = brief.get("objetivo_email", "")
    tono_email = brief.get("tono_email", "")

    page1 = f'''<div class="page">

  <div class="pg-head">
    <div class="tbl">
      <div class="tbl-cell">
        <div class="ph-brand">Factorial</div>
        <div class="ph-type">Follow-up Brief</div>
        <div class="ph-company">{esc_company}</div>
      </div>
      <div class="tbl-cell ph-right">
        <div class="ph-date">{esc_demo_dt}</div>
        <div class="ph-sub">{esc_fu_dt}</div>
      </div>
    </div>
  </div>

  <div class="kpi"><table>
    <tr>
      <td><div class="kpi-lbl">MRR</div><div class="kpi-val red">{esc_amount}</div></td>
      <td><div class="kpi-lbl">Probabilidad</div><div class="kpi-val warn">{probabilidad}</div></td>
      <td><div class="kpi-lbl">Engagement</div><div class="kpi-val">{engagement}</div></td>
      <td><div class="kpi-lbl">Partner</div><div class="kpi-val">{esc_partner}</div></td>
      <td><div class="kpi-lbl">Etapa</div><div class="kpi-val">{etapa}</div></td>
    </tr>
  </table></div>

  <div class="body-grid tbl">
    <div class="tbl-cell col-left">

      <div class="sec">
        <div class="sec-label">Resumen de la demo</div>
        {resumen_html}
      </div>

      <div class="sec">
        <div class="sec-label">Temas cubiertos</div>
        {temas_html}
      </div>

      <div class="sec">
        <div class="sec-label">Tono general</div>
        {tono_html}
      </div>

      {error_html}

      <div class="sec">
        <div class="sec-label">Señales de compra</div>
        {senales_html}
      </div>

    </div>

    <div class="tbl-cell col-right">

      <div class="sec">
        <div class="sec-label">Estado MEDDIC</div>
        {meddic_html}
      </div>

      <div class="sec">
        <div class="sec-label">Objeciones · ángulos de respuesta</div>
        {objeciones_html}
      </div>

      <div class="sec">
        <div class="sec-label">Probabilidad y riesgo</div>
        <div class="prob-row tbl">
          <div class="tbl-cell prob-num">{prob_num}<small>%</small></div>
          <div class="tbl-cell prob-text">{_esc(prob_texto)}</div>
        </div>
        <div class="alert">
          <div class="alert-title">Palanca única</div>
          {_esc(palanca)}
        </div>
      </div>

      <div class="sec">
        <div class="sec-label">Plan operativo</div>
        {plan_html}
      </div>

      <div class="sec">
        <div class="sec-label">Contactos</div>
        {prospect_html}
        <table class="blist"><tr><td class="dash">&mdash;</td><td><strong>PAE asignado</strong> · {esc_pae}</td></tr></table>
      </div>

    </div>
  </div>

  <div class="pfoot tbl">
    <div class="tbl-cell pfoot-left">{esc_company} &middot; Follow-up Brief &middot; Factorial</div>
    <div class="tbl-cell pfoot-right">Página 01 / 02</div>
  </div>

</div>'''

    page2 = f'''<div class="page page-2">

  <div class="p2-head tbl">
    <div class="tbl-cell p2h-left">
      <div class="p2h-label">Email de follow-up</div>
      <div class="p2h-title">Listo para copy-paste</div>
      <div class="p2h-sub">Quién · {esc_pae} → {_esc(prospect.get("name", ""))} &nbsp;&middot;&nbsp; Canal · Email &nbsp;&middot;&nbsp; Cuándo · {esc_fu_dt}</div>
    </div>
    <div class="tbl-cell p2h-right">
      <span class="p2h-badge">48h post-demo</span>
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
        <div class="mf"><table><tr><td class="mf-k">De</td><td class="mf-v">{esc_pae} · Factorial</td></tr></table></div>
        <div class="mf"><table><tr><td class="mf-k">Para</td><td class="mf-v">{_esc(email_to)}</td></tr></table></div>
        <div class="mf"><table><tr><td class="mf-k">Asunto</td><td class="mf-v subj">{_esc(email_subject)}</td></tr></table></div>
      </div>
      <div class="mail-body">
        {email_body}
      </div>
    </div>
  </div>

  <div class="note-block red"><strong>Objetivo del email.</strong> {_esc(objetivo_email)}</div>
  <div class="note-block blue"><strong>Tono.</strong> {_esc(tono_email)}</div>

  <div class="pfoot tbl">
    <div class="tbl-cell pfoot-left">{esc_company} &middot; Follow-up Brief &middot; Factorial</div>
    <div class="tbl-cell pfoot-right">Página 02 / 02</div>
  </div>

</div>'''

    html = (
        '<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><style>'
        + _CSS
        + "</style></head><body>"
        + page1
        + page2
        + "</body></html>"
    )

    return weasyprint.HTML(string=html).write_pdf()
