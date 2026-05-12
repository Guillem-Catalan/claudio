"""
Generate a 2-page PDF demo brief from Claude's structured output.
Page 1: Company overview, BANT, objections, pre-demo actions
Page 2: Demo roadmap with numbered steps and strategy

All layout uses display:table for bulletproof WeasyPrint rendering.
No floats, no position:absolute — text never overlaps.
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
    color: #1a1a18;
    background: #faf9f6;
    overflow-wrap: break-word;
    word-wrap: break-word;
}
.page { background: #fff; width: 100%; }
.page-2 { page-break-before: always; }

/* ── TABLE LAYOUT UTIL ── */
.tbl { display: table; width: 100%; }
.tbl-cell { display: table-cell; vertical-align: top; }

/* ── HEADER ── */
.hdr { padding: 24px 36px 0; }
.hdr-left { width: 65%; }
.hdr-right { text-align: right; }
.hdr .brand { font-size: 12px; font-weight: 600; color: #c8102e; letter-spacing: .3px; }
.hdr .type { font-size: 9px; text-transform: uppercase; letter-spacing: 2px; color: #8e8d88; margin-top: 1px; }
.hdr .name { font-size: 26px; font-weight: 700; letter-spacing: -.5px; margin-top: 2px; color: #1a1a18; }
.hdr .dates { font-size: 13px; font-weight: 500; line-height: 1.4; color: #1a1a18; }
.hdr .dates .sub { font-size: 9.5px; color: #8e8d88; font-weight: 400; }

/* ── KPI BAR ── */
.kpi { border-top: 1.5px solid #1a1a18; border-bottom: 1.5px solid #e4e3de; margin-top: 14px; }
.kpi table { width: 100%; border-collapse: collapse; }
.kpi td { padding: 8px 12px; vertical-align: top; width: 20%; }
.kpi-lbl { font-size: 7px; text-transform: uppercase; letter-spacing: 1.5px; color: #8e8d88; font-weight: 600; margin-bottom: 2px; }
.kpi-val { font-size: 11px; font-weight: 500; letter-spacing: -.02em; color: #1a1a18; }
.kpi-val.red { color: #c8102e; }

/* ── BODY 2-COL ── */
.body-grid { padding: 0 36px 30px; }
.col-left { width: 50%; padding-right: 16px; border-right: .5px solid #e4e3de; }
.col-right { width: 50%; padding-left: 16px; }

/* ── SECTIONS ── */
.sec { margin-bottom: 12px; }
.sec-label {
    font-family: 'Courier New', Courier, monospace;
    font-size: 7px; font-weight: 600; letter-spacing: .2em;
    text-transform: uppercase; color: #c8102e;
    margin-bottom: 6px; padding-bottom: 3px;
    border-bottom: 1px solid #f0efe9;
}

/* ── BULLET LIST (table-based, no absolute positioning) ── */
.blist { border-collapse: collapse; width: 100%; }
.blist td { font-size: 9.5px; line-height: 1.5; color: #5c5b57; font-weight: 300; padding: 2px 0; vertical-align: top; }
.blist .dash { width: 12px; color: #c8102e; font-size: 9px; }
.blist strong { font-weight: 500; color: #1a1a18; }

/* ── BANT STATUS ── */
.status-grid table { width: 100%; border-collapse: separate; border-spacing: 0 3px; }
.status-grid td { padding: 5px 8px; background: #faf9f6; font-size: 9px; line-height: 1.4; vertical-align: top; }
.status-grid .sr-k {
    font-family: 'Courier New', Courier, monospace;
    font-size: 7px; font-weight: 600; letter-spacing: .12em;
    text-transform: uppercase; color: #8e8d88; width: 60px;
}
.status-grid .sr-dot { width: 18px; font-size: 10px; text-align: center; }
.status-grid .sr-v { color: #5c5b57; font-weight: 300; }
.status-grid .sr-v strong { font-weight: 500; color: #1a1a18; }

/* ── PAIN ALERT ── */
.alert {
    padding: 7px 10px; margin-bottom: 5px;
    border-left: 3px solid #c8102e; background: #fdf0f0;
    font-size: 9.5px; line-height: 1.5; color: #5c5b57; font-weight: 300;
}
.alert-title {
    font-size: 7px; font-weight: 700; letter-spacing: .14em;
    text-transform: uppercase; color: #c8102e; margin-bottom: 3px;
}
.alert strong { font-weight: 500; color: #1a1a18; }

/* ── OBJECTIONS ── */
.obj { padding: 6px 8px; border: 1px solid #e4e3de; margin-bottom: 4px; font-size: 9px; line-height: 1.4; }
.obj-q { font-weight: 500; color: #1a1a18; margin-bottom: 2px; font-size: 9.5px; }
.obj-a { color: #5c5b57; font-weight: 300; }

/* ── FOOTER ── */
.pfoot { padding: 6px 36px; border-top: 1px solid #f0efe9; font-size: 8px; color: #8e8d88; letter-spacing: .04em; }
.pfoot-left { width: 70%; }
.pfoot-right { text-align: right; }

/* ── PAGE 2 HEADER ── */
.p2-head { padding: 18px 36px 14px; border-bottom: 1px solid #e4e3de; }
.p2h-left { width: 75%; }
.p2h-right { text-align: right; vertical-align: bottom; }
.p2h-label {
    font-family: 'Courier New', Courier, monospace;
    font-size: 7px; font-weight: 600; letter-spacing: .2em;
    text-transform: uppercase; color: #c8102e; margin-bottom: 4px;
}
.p2h-title { font-size: 20px; font-weight: 700; letter-spacing: -.04em; color: #1a1a18; line-height: 1; }
.p2h-sub { font-size: 10px; color: #8e8d88; font-weight: 300; margin-top: 3px; }
.p2h-badge {
    background: #fdf0f0; border: 1px solid #ffccd4;
    padding: 4px 12px; font-size: 9px; font-weight: 500; color: #c8102e;
    display: inline-block;
}

/* ── STRATEGY BANNER ── */
.strategy-banner {
    margin: 12px 36px 0; background: #1a1a18;
    padding: 10px 16px; font-size: 10px; color: rgba(255,255,255,.7); line-height: 1.55;
}
.strategy-banner strong { color: #fff; font-weight: 500; }

/* ── ROADMAP STEPS (table-based, no absolute positioning) ── */
.roadmap { padding: 14px 36px 30px; }
.step-table { width: 100%; border-collapse: collapse; }
.step-table td { vertical-align: top; }
.step-num-cell { width: 36px; padding-bottom: 8px; }
.step-num-cell.line { border-right: 2px solid #e4e3de; }
.step-num {
    width: 28px; height: 28px;
    background: #1a1a18; color: #fff;
    text-align: center; line-height: 28px;
    font-size: 12px; font-weight: 500;
    border-radius: 50%;
}
.step-key .step-num { background: #c8102e; }
.step-content { padding: 2px 0 14px 14px; }
.step-title { font-size: 12px; font-weight: 600; letter-spacing: -.02em; color: #1a1a18; margin-bottom: 3px; }
.step-desc { font-size: 9.5px; color: #5c5b57; line-height: 1.55; font-weight: 300; margin-bottom: 5px; }
.step-desc strong { font-weight: 500; color: #1a1a18; }
.chip {
    display: inline-block; font-size: 8px; font-weight: 500;
    background: #faf9f6; color: #5c5b57;
    padding: 2px 8px; margin-right: 3px; margin-bottom: 2px;
}
.chip.red { background: #fdf0f0; color: #c8102e; }
"""


def _esc(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _blist(items: list[str]) -> str:
    if not items:
        return '<table class="blist"><tr><td class="dash">&mdash;</td><td>No hay información disponible</td></tr></table>'
    rows = "".join(
        f'<tr><td class="dash">&mdash;</td><td>{_esc(i)}</td></tr>' for i in items
    )
    return f'<table class="blist">{rows}</table>'


def _render_bant(bant: dict) -> str:
    rows = ""
    for key in ("budget", "authority", "need", "timeline"):
        pillar = bant.get(key, {})
        emoji = pillar.get("emoji", "❓")
        text = pillar.get("text", "Sin información")
        label = {"budget": "Budget", "authority": "Authority", "need": "Need", "timeline": "Timeline"}[key]
        rows += (
            f'<tr>'
            f'<td class="sr-k">{_esc(label)}</td>'
            f'<td class="sr-dot">{emoji}</td>'
            f'<td class="sr-v">{_esc(text)}</td>'
            f'</tr>'
        )
    return f'<div class="status-grid"><table>{rows}</table></div>'


def _render_objeciones(objs: list[dict]) -> str:
    if not objs:
        return '<div class="obj"><div class="obj-q">Sin objeciones identificadas</div></div>'
    html = ""
    for o in objs:
        html += (
            f'<div class="obj">'
            f'<div class="obj-q">{_esc(o.get("pregunta", ""))}</div>'
            f'<div class="obj-a">{_esc(o.get("respuesta", ""))}</div>'
            f'</div>'
        )
    return html


def _render_pain_principal(pain: dict) -> str:
    titulo = pain.get("titulo", "PAIN PRINCIPAL")
    texto = pain.get("texto", "Sin evidencia")
    return (
        f'<div class="alert">'
        f'<div class="alert-title">{_esc(titulo)}</div>'
        f'{_esc(texto)}'
        f'</div>'
    )


def _render_steps(steps: list[dict]) -> str:
    if not steps:
        return ""
    rows = ""
    for i, step in enumerate(steps):
        is_key = step.get("key", False)
        is_last = (i == len(steps) - 1)
        row_cls = "step-key" if is_key else ""
        num_cls = "step-num-cell" if is_last else "step-num-cell line"
        titulo = _esc(step.get("titulo", f"Paso {i + 1}"))
        desc = _esc(step.get("desc", ""))

        chips_html = ""
        for c in (step.get("chips") or []):
            if isinstance(c, str):
                chips_html += f'<span class="chip">{_esc(c)}</span>'
            elif isinstance(c, dict):
                red = " red" if c.get("key") else ""
                chips_html += f'<span class="chip{red}">{_esc(c.get("text", ""))}</span>'

        rows += (
            f'<tr class="{row_cls}">'
            f'<td class="{num_cls}"><div class="step-num">{i + 1}</div></td>'
            f'<td class="step-content">'
            f'<div class="step-title">{titulo}</div>'
            f'<div class="step-desc">{desc}</div>'
            f'<div>{chips_html}</div>'
            f'</td></tr>'
        )
    return f'<table class="step-table">{rows}</table>'


def generate_pdf(
    brief: dict,
    company: str,
    demo_date_long: str,
    demo_date_short: str,
    demo_time: str,
    amount_str: str,
    partner: str,
    contact: dict,
) -> bytes:
    today = date.today()
    fecha_sub = f"preparado {today.day} {_MESES_CORTO[today.month]} {today.year}"

    pepm = _esc(brief.get("pepm")) or "—"
    empleados = _esc(brief.get("empleados")) or "—"
    solucion = _esc(brief.get("solucion")) or "—"

    cliente_html = _blist(brief.get("cliente", []))
    situacion_html = _blist(brief.get("situacion", []))
    pain_html = _render_pain_principal(brief.get("pain_principal", {}))
    pains_sec_html = _blist(brief.get("pains_secundarios", []))
    bant_html = _render_bant(brief.get("bant", {}))
    objeciones_html = _render_objeciones(brief.get("objeciones", []))
    acciones_html = _blist(brief.get("acciones_criticas", []))
    estrategia = _esc(brief.get("estrategia", ""))
    steps_html = _render_steps(brief.get("steps", []))

    esc_company = _esc(company)
    esc_date_long = _esc(demo_date_long)
    esc_date_short = _esc(demo_date_short)
    esc_time = _esc(demo_time)
    esc_amount = _esc(amount_str)
    esc_partner = _esc(partner)

    page1 = f'''<div class="page">

  <div class="hdr">
    <div class="tbl">
      <div class="tbl-cell hdr-left">
        <div class="brand">Factorial</div>
        <div class="type">Demo Brief</div>
        <div class="name">{esc_company}</div>
      </div>
      <div class="tbl-cell hdr-right">
        <div class="dates">
          {esc_date_long}<br>
          <span class="sub">{fecha_sub}</span>
        </div>
      </div>
    </div>
  </div>

  <div class="kpi"><table>
    <tr>
      <td><div class="kpi-lbl">MRR</div><div class="kpi-val red">{esc_amount}</div></td>
      <td><div class="kpi-lbl">PEPM</div><div class="kpi-val">{pepm}</div></td>
      <td><div class="kpi-lbl">Empleados</div><div class="kpi-val">{empleados}</div></td>
      <td><div class="kpi-lbl">Partner</div><div class="kpi-val">{esc_partner}</div></td>
      <td><div class="kpi-lbl">Solución</div><div class="kpi-val">{solucion}</div></td>
    </tr>
  </table></div>

  <div class="body-grid tbl">
    <div class="tbl-cell col-left">
      <div class="sec">
        <div class="sec-label">Cliente</div>
        {cliente_html}
      </div>
      <div class="sec">
        <div class="sec-label">Situación actual</div>
        {situacion_html}
      </div>
      <div class="sec">
        <div class="sec-label">Pains priorizados</div>
        {pain_html}
        {pains_sec_html}
      </div>
    </div>

    <div class="tbl-cell col-right">
      <div class="sec">
        <div class="sec-label">BANT</div>
        {bant_html}
      </div>
      <div class="sec">
        <div class="sec-label">Objeciones y riesgos</div>
        {objeciones_html}
      </div>
      <div class="sec">
        <div class="sec-label">Acciones críticas pre-demo</div>
        {acciones_html}
      </div>
    </div>
  </div>

  <div class="pfoot tbl">
    <div class="tbl-cell pfoot-left">{esc_company} &middot; Demo Brief &middot; Factorial</div>
    <div class="tbl-cell pfoot-right">Página 01 / 02</div>
  </div>

</div>'''

    page2 = f'''<div class="page page-2">

  <div class="p2-head tbl">
    <div class="tbl-cell p2h-left">
      <div class="p2h-label">Roadmap de la demo</div>
      <div class="p2h-title">Cómo conducir la conversación</div>
      <div class="p2h-sub">Por dónde tirar paso a paso &middot; tenlo delante durante la demo</div>
    </div>
    <div class="tbl-cell p2h-right">
      <span class="p2h-badge">{esc_date_short}</span>
    </div>
  </div>

  <div class="strategy-banner">
    <strong>Estrategia.</strong> {estrategia}
  </div>

  <div class="roadmap">
    {steps_html}
  </div>

  <div class="pfoot tbl">
    <div class="tbl-cell pfoot-left">{esc_company} &middot; Demo Brief &middot; Factorial</div>
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
