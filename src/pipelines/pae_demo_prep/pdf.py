"""
Generate a 2-page PDF demo brief from Claude's structured output.
Page 1: Company overview, BANT, objections, pre-demo actions
Page 2: Demo roadmap with numbered steps and strategy
"""

from datetime import date

import weasyprint

_MESES_CORTO = {
    1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
    7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic",
}

_CSS = """\
@page { size: A4; margin: 0; }

:root {
    --ink: #1a1a18;
    --ink2: #5c5b57;
    --ink3: #8e8d88;
    --bg: #faf9f6;
    --card: #fff;
    --bdr: #e4e3de;
    --bdr-l: #f0efe9;
    --red: #c8102e;
    --red-bg: #fdf0f0;
    --red-tx: #9a0c22;
    --grn: #1a7a4c;
    --grn-bg: #edf7f1;
    --amb: #a86400;
    --amb-bg: #fef6e8;
    --brand: #c8102e;
    --ff: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    --fm: 'Courier New', Courier, monospace;
}

* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: var(--ff);
    font-size: 12.5px;
    line-height: 1.55;
    color: var(--ink);
    background: var(--bg);
    -webkit-font-smoothing: antialiased;
}
.page { background: var(--card); }
.page-2 { page-break-before: always; }

.hdr { padding: 28px 40px 0; }
.hdr .brand { font-size: 13px; font-weight: 600; color: var(--brand); letter-spacing: .3px; }
.hdr .type { font-size: 10px; text-transform: uppercase; letter-spacing: 2px; color: var(--ink3); margin-top: 1px; }
.hdr .name { font-size: 32px; font-weight: 700; letter-spacing: -.5px; margin-top: 2px; }
.hdr .dates { text-align: right; font-size: 14px; font-weight: 500; line-height: 1.4; }
.hdr .dates .sub { font-size: 10.5px; color: var(--ink3); font-weight: 400; }
.hdr-row { display: flex; justify-content: space-between; align-items: flex-start; }

.kpi { display: grid; grid-template-columns: repeat(5, 1fr); border-top: 1.5px solid var(--ink); border-bottom: 1.5px solid var(--bdr); margin-top: 16px; }
.kpi-item { padding: 10px 14px; }
.kpi-lbl { font-size: 8px; text-transform: uppercase; letter-spacing: 1.5px; color: var(--ink3); font-weight: 600; margin-bottom: 3px; }
.kpi-val { font-size: 12px; font-weight: 500; letter-spacing: -.02em; color: var(--ink); }
.kpi-val.red { color: var(--brand); }

.body-grid { display: grid; grid-template-columns: 1fr 1fr; padding: 0 40px 40px; }
.col { padding: 16px 18px; overflow: hidden; }
.col:first-child { border-right: .5px solid var(--bdr); }

.sec { margin-bottom: 14px; }
.sec-label {
    font-family: var(--fm);
    font-size: 8px; font-weight: 600; letter-spacing: .2em;
    text-transform: uppercase; color: var(--brand);
    margin-bottom: 8px; display: flex; align-items: center; gap: 6px;
}
.sec-label::after { content: ''; flex: 1; height: 1px; background: var(--bdr-l); }

.blist { list-style: none; display: flex; flex-direction: column; gap: 4px; }
.blist li {
    position: relative; padding-left: 14px;
    font-size: 10.5px; line-height: 1.5; color: var(--ink2); font-weight: 300;
}
.blist li::before {
    content: '\2014'; color: var(--brand); font-size: 10px;
    position: absolute; left: 0; top: 0; line-height: 1.55;
}
.blist li strong { font-weight: 500; color: var(--ink); }

.status-grid { display: flex; flex-direction: column; gap: 4px; }
.status-row {
    display: grid; grid-template-columns: 70px 18px 1fr;
    align-items: flex-start; gap: 6px;
    padding: 6px 10px; background: var(--bg); border-radius: 5px;
    font-size: 10px; line-height: 1.45;
}
.sr-k {
    font-family: var(--fm); font-size: 8px; font-weight: 600;
    letter-spacing: .12em; text-transform: uppercase; color: var(--ink3); padding-top: 2px;
}
.sr-dot { font-size: 11px; padding-top: 1px; }
.sr-v { color: var(--ink2); font-weight: 300; }
.sr-v strong { font-weight: 500; color: var(--ink); }

.alert {
    padding: 8px 12px; border-radius: 0 5px 5px 0; margin-bottom: 6px;
    border-left: 3px solid var(--amb); background: var(--amb-bg);
    font-size: 10.5px; line-height: 1.5; color: var(--ink2); font-weight: 300;
}
.alert.red { border-color: var(--brand); background: var(--red-bg); }
.alert-title {
    font-size: 8px; font-weight: 700; letter-spacing: .14em;
    text-transform: uppercase; color: var(--amb); margin-bottom: 4px;
}
.alert.red .alert-title { color: var(--brand); }
.alert strong { font-weight: 500; color: var(--ink); }

.obj-list { display: flex; flex-direction: column; gap: 5px; }
.obj { padding: 7px 10px; border: 1px solid var(--bdr); border-radius: 5px; font-size: 10px; line-height: 1.45; }
.obj-q { font-weight: 500; color: var(--ink); margin-bottom: 2px; font-size: 10.5px; }
.obj-a { color: var(--ink2); font-weight: 300; }
.obj-a strong { font-weight: 500; color: var(--ink); }

.pfoot {
    padding: 8px 40px; border-top: 1px solid var(--bdr-l);
    display: flex; justify-content: space-between;
    font-size: 8.5px; color: var(--ink3); letter-spacing: .04em;
}

.p2-head {
    padding: 20px 40px 16px; border-bottom: 1px solid var(--bdr);
    display: flex; justify-content: space-between; align-items: flex-end;
}
.p2h-label {
    font-family: var(--fm); font-size: 8px; font-weight: 600;
    letter-spacing: .2em; text-transform: uppercase; color: var(--brand); margin-bottom: 5px;
}
.p2h-title { font-size: 22px; font-weight: 700; letter-spacing: -.04em; color: var(--ink); line-height: 1; }
.p2h-sub { font-size: 11px; color: var(--ink3); font-weight: 300; margin-top: 4px; }
.p2h-badge {
    background: var(--red-bg); border: 1px solid #ffccd4; border-radius: 20px;
    padding: 5px 14px; font-size: 10px; font-weight: 500; color: var(--brand);
}

.strategy-banner {
    margin: 14px 40px 0; background: var(--ink); border-radius: 7px;
    padding: 12px 18px; font-size: 11px; color: rgba(255,255,255,.7); line-height: 1.55;
}
.strategy-banner strong { color: #fff; font-weight: 500; }

.roadmap { padding: 16px 40px 40px; }
.step { display: grid; grid-template-columns: 40px 1fr; position: relative; }
.step:not(:last-child) .step-line {
    position: absolute; top: 40px; left: 19px; width: 2px;
    height: calc(100%); background: var(--bdr);
}
.step-num {
    width: 32px; height: 32px; border-radius: 50%;
    background: var(--ink); color: #fff;
    display: flex; align-items: center; justify-content: center;
    font-size: 13px; font-weight: 500; position: relative; z-index: 1;
    margin-top: 3px; flex-shrink: 0;
}
.step.key .step-num { background: var(--brand); }
.step-body { padding: 2px 0 20px 16px; }
.step-title { font-size: 13.5px; font-weight: 600; letter-spacing: -.02em; color: var(--ink); margin-bottom: 4px; }
.step-desc { font-size: 10.5px; color: var(--ink2); line-height: 1.55; font-weight: 300; margin-bottom: 6px; }
.step-desc strong { font-weight: 500; color: var(--ink); }
.chips { display: flex; flex-wrap: wrap; gap: 4px; }
.chip { font-size: 9px; font-weight: 500; background: var(--bg); color: var(--ink2); border-radius: 20px; padding: 3px 10px; }
.chip.red { background: var(--red-bg); color: var(--brand); }
"""


def _esc(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _blist(items: list[str]) -> str:
    if not items:
        return '<ul class="blist"><li>No hay información disponible</li></ul>'
    return '<ul class="blist">' + "".join(
        f"<li>{_esc(i)}</li>" for i in items
    ) + "</ul>"


def _status_row(key: str, emoji: str, text: str) -> str:
    return (
        f'<div class="status-row">'
        f'<span class="sr-k">{_esc(key)}</span>'
        f'<span class="sr-dot">{emoji}</span>'
        f'<span class="sr-v">{_esc(text)}</span>'
        f'</div>'
    )


def _render_bant(bant: dict) -> str:
    rows = ""
    for key in ("budget", "authority", "need", "timeline"):
        pillar = bant.get(key, {})
        emoji = pillar.get("emoji", "❓")
        text = pillar.get("text", "Sin información")
        label = {"budget": "Budget", "authority": "Authority", "need": "Need", "timeline": "Timeline"}[key]
        rows += _status_row(label, emoji, text)
    return f'<div class="status-grid">{rows}</div>'


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
        f'<div class="alert red">'
        f'<div class="alert-title">{_esc(titulo)}</div>'
        f'{_esc(texto)}'
        f'</div>'
    )


def _render_step(num: int, step: dict, is_last: bool) -> str:
    is_key = step.get("key", False)
    cls = "step key" if is_key else "step"
    line = "" if is_last else '<div class="step-line"></div>'
    titulo = _esc(step.get("titulo", f"Paso {num}"))
    desc = _esc(step.get("desc", ""))

    chips_html = ""
    for c in (step.get("chips") or []):
        if isinstance(c, str):
            chips_html += f'<span class="chip">{_esc(c)}</span>'
        elif isinstance(c, dict):
            red = " red" if c.get("key") else ""
            chips_html += f'<span class="chip{red}">{_esc(c.get("text", ""))}</span>'

    return (
        f'<div class="{cls}">'
        f'<div><div class="step-num">{num}</div>{line}</div>'
        f'<div class="step-body">'
        f'<div class="step-title">{titulo}</div>'
        f'<div class="step-desc">{desc}</div>'
        f'<div class="chips">{chips_html}</div>'
        f'</div></div>'
    )


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

    steps = brief.get("steps", [])
    steps_html = ""
    for i, step in enumerate(steps):
        steps_html += _render_step(i + 1, step, is_last=(i == len(steps) - 1))

    c_name = _esc(contact.get("name", ""))
    c_title = _esc(contact.get("jobtitle", ""))
    c_email = _esc(contact.get("email", ""))
    c_phone = contact.get("phone", "")
    contact_line = f"{c_name}"
    if c_title:
        contact_line += f" &middot; {c_title}"
    if c_email:
        contact_line += f" &middot; {c_email}"
    if c_phone:
        contact_line += f" &middot; {_esc(c_phone)}"

    esc_company = _esc(company)
    esc_date_long = _esc(demo_date_long)
    esc_date_short = _esc(demo_date_short)
    esc_time = _esc(demo_time)
    esc_amount = _esc(amount_str)
    esc_partner = _esc(partner)

    page1 = f'''<div class="page">
  <div class="hdr">
    <div class="hdr-row">
      <div>
        <div class="brand">Factorial</div>
        <div class="type">Demo Brief</div>
        <div class="name">{esc_company}</div>
      </div>
      <div class="dates">
        {esc_date_long}<br>
        <span class="sub">{fecha_sub}</span>
      </div>
    </div>
  </div>

  <div class="kpi">
    <div class="kpi-item"><div class="kpi-lbl">MRR</div><div class="kpi-val red">{esc_amount}</div></div>
    <div class="kpi-item"><div class="kpi-lbl">PEPM</div><div class="kpi-val">{pepm}</div></div>
    <div class="kpi-item"><div class="kpi-lbl">Empleados</div><div class="kpi-val">{empleados}</div></div>
    <div class="kpi-item"><div class="kpi-lbl">Partner</div><div class="kpi-val">{esc_partner}</div></div>
    <div class="kpi-item"><div class="kpi-lbl">Solución</div><div class="kpi-val">{solucion}</div></div>
  </div>

  <div class="body-grid">
    <div class="col">
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

    <div class="col">
      <div class="sec">
        <div class="sec-label">BANT</div>
        {bant_html}
      </div>
      <div class="sec">
        <div class="sec-label">Objeciones y riesgos</div>
        <div class="obj-list">{objeciones_html}</div>
      </div>
      <div class="sec">
        <div class="sec-label">Acciones críticas pre-demo</div>
        {acciones_html}
      </div>
    </div>
  </div>

  <div class="pfoot">
    <span>{esc_company} &middot; Demo Brief &middot; Factorial</span>
    <span>Página 01 / 02</span>
  </div>
</div>'''

    page2 = f'''<div class="page page-2">
  <div class="p2-head">
    <div>
      <div class="p2h-label">Roadmap de la demo</div>
      <div class="p2h-title">Cómo conducir la conversación</div>
      <div class="p2h-sub">Por dónde tirar paso a paso &middot; tenlo delante durante la demo</div>
    </div>
    <div class="p2h-badge">{esc_date_short}</div>
  </div>

  <div class="strategy-banner">
    <strong>Estrategia.</strong> {estrategia}
  </div>

  <div class="roadmap">
    {steps_html}
  </div>

  <div class="pfoot">
    <span>{esc_company} &middot; Demo Brief &middot; Factorial</span>
    <span>Página 02 / 02</span>
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
