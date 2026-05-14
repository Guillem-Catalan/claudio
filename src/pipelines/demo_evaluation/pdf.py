"""
Generate a 1-page PDF demo evaluation report.
Template layout — replace with final design when ready.
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
}
.page { background: #fff; width: 100%; padding: 0; }

.hdr { padding: 24px 36px 0; }
.tbl { display: table; width: 100%; }
.tbl-cell { display: table-cell; vertical-align: top; }
.hdr-left { width: 65%; }
.hdr-right { text-align: right; }
.hdr .brand { font-size: 12px; font-weight: 600; color: #c8102e; letter-spacing: .3px; }
.hdr .type { font-size: 9px; text-transform: uppercase; letter-spacing: 2px; color: #8e8d88; margin-top: 1px; }
.hdr .name { font-size: 24px; font-weight: 700; letter-spacing: -.5px; margin-top: 2px; color: #1a1a18; }
.hdr .dates { font-size: 13px; font-weight: 500; line-height: 1.4; color: #1a1a18; }
.hdr .dates .sub { font-size: 9.5px; color: #8e8d88; font-weight: 400; }

.kpi { border-top: 1.5px solid #1a1a18; border-bottom: 1.5px solid #e4e3de; margin-top: 14px; }
.kpi table { width: 100%; border-collapse: collapse; }
.kpi td { padding: 8px 10px; vertical-align: top; }
.kpi-lbl { font-size: 7px; text-transform: uppercase; letter-spacing: 1.5px; color: #8e8d88; font-weight: 600; margin-bottom: 2px; }
.kpi-val { font-size: 11px; font-weight: 500; color: #1a1a18; }
.kpi-val.red { color: #c8102e; }

.body { padding: 14px 36px 20px; }
.sec { margin-bottom: 10px; }
.sec-label {
    font-family: 'Courier New', Courier, monospace;
    font-size: 7px; font-weight: 600; letter-spacing: .2em;
    text-transform: uppercase; color: #c8102e;
    margin-bottom: 4px; padding-bottom: 3px;
    border-bottom: 1px solid #f0efe9;
}
.sec-text { font-size: 9.5px; line-height: 1.55; color: #5c5b57; font-weight: 300; }
.sec-text strong { font-weight: 500; color: #1a1a18; }

.scores-grid table { width: 100%; border-collapse: separate; border-spacing: 0 3px; }
.scores-grid td { padding: 5px 8px; background: #faf9f6; font-size: 9px; line-height: 1.4; vertical-align: top; }
.scores-grid .sk { font-family: 'Courier New', monospace; font-size: 7px; font-weight: 600; letter-spacing: .12em; text-transform: uppercase; color: #8e8d88; width: 55px; }
.scores-grid .ss { width: 30px; text-align: center; font-weight: 600; color: #1a1a18; }
.scores-grid .sv { color: #5c5b57; font-weight: 300; }

.col-left { width: 50%; padding-right: 14px; border-right: .5px solid #e4e3de; }
.col-right { width: 50%; padding-left: 14px; }

.pfoot { padding: 6px 36px; border-top: 1px solid #f0efe9; font-size: 8px; color: #8e8d88; }
.pfoot-left { width: 70%; }
.pfoot-right { text-align: right; }
"""


def _esc(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _score_color(score) -> str:
    try:
        s = int(score)
    except (TypeError, ValueError):
        return "#8e8d88"
    if s >= 7:
        return "#2eb886"
    if s >= 4:
        return "#daa038"
    return "#c8102e"


def _render_scores(data: dict) -> str:
    pillars = [
        ("M", "Metrics", "m"),
        ("E", "Econ. Buyer", "e"),
        ("DC", "Decision Crit.", "dc"),
        ("DP", "Decision Proc.", "dp"),
        ("I", "Identify Pain", "i"),
        ("C", "Champion", "c"),
    ]
    rows = ""
    for label, _full, key in pillars:
        score = data.get(f"{key}_score", "—")
        text = _esc(data.get(f"{key}_accumulate") or "—")
        color = _score_color(score)
        rows += (
            f'<tr>'
            f'<td class="sk">{label}</td>'
            f'<td class="ss" style="color:{color}">{score}</td>'
            f'<td class="sv">{text}</td>'
            f'</tr>'
        )
    return f'<div class="scores-grid"><table>{rows}</table></div>'


def _bullets(text: str) -> str:
    if not text or not text.strip():
        return '<div class="sec-text">—</div>'
    return f'<div class="sec-text">{_esc(text)}</div>'


def generate_pdf(data: dict) -> bytes:
    today = date.today()
    fecha_sub = f"generado {today.day} {_MESES_CORTO[today.month]} {today.year}"

    company = _esc(data.get("company_name") or "?")
    deal_name = _esc(data.get("deal_name") or "?")
    pae = _esc(data.get("pae") or "?")
    partner = _esc(data.get("partner") or "?")
    demo_date = _esc((data.get("demo_date") or "?")[:10])
    amount = data.get("amount")
    amount_str = f"€{float(amount):,.0f}" if amount else "—"

    summary = _esc(data.get("demo_summary") or "—")
    scores_html = _render_scores(data)
    improvements = _bullets(data.get("improvements") or "")
    strengths = _bullets(data.get("deal_strengths") or "")
    next_step = _bullets(data.get("next_step") or "")
    objections = _bullets(data.get("objections") or "")

    html = f'''<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<style>{_CSS}</style></head><body>
<div class="page">

  <div class="hdr">
    <div class="tbl">
      <div class="tbl-cell hdr-left">
        <div class="brand">Factorial</div>
        <div class="type">Demo Evaluation</div>
        <div class="name">{company}</div>
      </div>
      <div class="tbl-cell hdr-right">
        <div class="dates">
          Demo: {demo_date}<br>
          <span class="sub">{fecha_sub}</span>
        </div>
      </div>
    </div>
  </div>

  <div class="kpi"><table><tr>
    <td><div class="kpi-lbl">MRR</div><div class="kpi-val red">{_esc(amount_str)}</div></td>
    <td><div class="kpi-lbl">PAE</div><div class="kpi-val">{pae}</div></td>
    <td><div class="kpi-lbl">Partner</div><div class="kpi-val">{partner}</div></td>
    <td><div class="kpi-lbl">Deal</div><div class="kpi-val">{deal_name}</div></td>
  </tr></table></div>

  <div class="body">
    <div class="sec">
      <div class="sec-label">Demo Summary</div>
      <div class="sec-text">{summary}</div>
    </div>

    <div class="sec">
      <div class="sec-label">MEDDIC — Ejecución de la Demo</div>
      {scores_html}
    </div>

    <div class="tbl">
      <div class="tbl-cell col-left">
        <div class="sec">
          <div class="sec-label">Coaching — Improvements</div>
          {improvements}
        </div>
        <div class="sec">
          <div class="sec-label">Objeciones activas</div>
          {objections}
        </div>
      </div>
      <div class="tbl-cell col-right">
        <div class="sec">
          <div class="sec-label">Fortalezas</div>
          {strengths}
        </div>
        <div class="sec">
          <div class="sec-label">Next Steps</div>
          {next_step}
        </div>
      </div>
    </div>
  </div>

  <div class="pfoot tbl">
    <div class="tbl-cell pfoot-left">{company} · Demo Evaluation · Factorial</div>
    <div class="tbl-cell pfoot-right">Página 01 / 01</div>
  </div>

</div>
</body></html>'''

    return weasyprint.HTML(string=html).write_pdf()
