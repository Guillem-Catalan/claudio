"""
PDF template for closed deals — TL close report (won or lost).
Single page with: outcome, timeline, key factors, lessons, recommendations.
"""

import weasyprint

_CSS = """\
@page { size: A4; margin: 0; }
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    font-size: 12.5px; line-height: 1.55; color: #1a1a18; background: #faf9f6;
}
.page { background: #fff; width: 100%; height: 1123px; overflow: hidden; }

.tbl { display: table; width: 100%; }
.tbl-cell { display: table-cell; vertical-align: top; }

.hdr { padding: 28px 40px 0; }
.hdr-left { width: 65%; }
.hdr-right { text-align: right; vertical-align: top; }
.brand-won { font-size: 13px; font-weight: 600; color: #12593a; letter-spacing: .3px; }
.brand-lost { font-size: 13px; font-weight: 600; color: #c8102e; letter-spacing: .3px; }
.type { font-size: 10px; text-transform: uppercase; letter-spacing: 2px; color: #8e8d88; margin-top: 1px; }
.name { font-size: 32px; font-weight: 700; letter-spacing: -.5px; margin-top: 2px; }
.dates { font-size: 14px; font-weight: 500; line-height: 1.4; }
.dates .sub { font-size: 10.5px; color: #8e8d88; font-weight: 400; }

.kpi { border-top: 1.5px solid #1a1a18; border-bottom: 1.5px solid #e4e3de; margin-top: 16px; }
.kpi table { width: 100%; border-collapse: collapse; }
.kpi td { padding: 10px 14px; vertical-align: top; width: 20%; }
.kpi-lbl { font-size: 8.5px; text-transform: uppercase; letter-spacing: 1.5px; color: #8e8d88; font-weight: 600; }
.kpi-val { font-size: 16px; font-weight: 600; margin-top: 1px; }
.kpi-val.red { color: #c8102e; }
.kpi-val.green { color: #12593a; }

.body-grid { padding: 0 40px 40px; }
.col-l { width: 50%; padding-right: 32px; padding-top: 24px; border-right: .5px solid #e4e3de; overflow: hidden; }
.col-r { width: 50%; padding-left: 32px; padding-top: 24px; overflow: hidden; }

.stit {
    font-family: 'Courier New', Courier, monospace;
    font-size: 9px; font-weight: 500; text-transform: uppercase;
    letter-spacing: 2px; color: #c8102e; margin-bottom: 10px; margin-top: 24px;
}
.stit.green { color: #12593a; }
.stit-first { margin-top: 0; }

.bi-table { width: 100%; border-collapse: collapse; }
.bi-table td { font-size: 11.5px; line-height: 1.6; color: #5c5b57; padding: 3px 0; vertical-align: top; }
.bi-dash { width: 14px; color: #8e8d88; }
.bi-table b { color: #1a1a18; font-weight: 600; }

.hbox {
    border-left: 3px solid #c8102e; background: #fdf0f0;
    padding: 12px 16px; margin-top: 12px;
}
.hbox.green { border-left-color: #12593a; background: #edf7f1; }
.hbox .ht {
    font-size: 10px; font-weight: 600; text-transform: uppercase;
    letter-spacing: 1px; color: #c8102e; margin-bottom: 4px;
}
.hbox.green .ht { color: #12593a; }
.hbox p { font-size: 11px; line-height: 1.6; color: #5c5b57; }
.hbox p b { color: #1a1a18; font-weight: 600; }

.numbered-table { width: 100%; border-collapse: collapse; }
.numbered-table td { padding: 8px 0; vertical-align: top; border-bottom: .5px solid #f0efe9; font-size: 11px; line-height: 1.55; color: #5c5b57; }
.numbered-table tr:last-child td { border-bottom: none; }
.num { width: 28px; font-size: 14px; font-weight: 600; color: #c8102e; }
.num.green { color: #12593a; }
.q-title { font-weight: 500; color: #1a1a18; }
.q-detail { font-size: 10.5px; color: #8e8d88; margin-top: 2px; }

.note-block { margin: 10px 0 0; padding: 9px 14px; font-size: 10.5px; line-height: 1.5; font-weight: 300; }
.note-block.red { background: #fdf0f0; border-left: 3px solid #c8102e; color: #3a1a22; }
.note-block.green { background: #edf7f1; border-left: 3px solid #12593a; color: #0a3320; }
.note-block.blue { background: #f0f7ff; border-left: 3px solid #3b82f6; color: #1e3a5f; }
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


def _render_bullets(items) -> str:
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


def generate_pdf(brief: dict, data: dict) -> bytes:
    company = data["company"]
    demo_datetime = data["demo_datetime"]
    amount_str = data["amount_str"]
    partner = data["partner"]
    pae_name = data["pae_name"]
    is_won = data.get("classification", {}).get("is_won", False)

    deal_stage = data["deal"].get("deal_stage", "?")
    outcome = brief.get("outcome", "Cerrado")
    brand_class = "brand-won" if is_won else "brand-lost"
    report_type = "Win Report" if is_won else "Loss Report"
    color = "green" if is_won else ""

    factors_html = ""
    for i, f in enumerate(brief.get("key_factors", []), 1):
        num_class = f'num {color}' if is_won else "num"
        factors_html += (
            f'<tr>'
            f'<td class="{num_class}">{i}.</td>'
            f'<td><div class="q-title">{_esc(f.get("factor", ""))}</div>'
            f'<div class="q-detail">{_allow_bold(f.get("evidence", ""))}</div></td>'
            f'</tr>'
        )

    lessons_html = ""
    for i, l in enumerate(brief.get("lessons", []), 1):
        num_class = f'num {color}' if is_won else "num"
        lessons_html += (
            f'<tr>'
            f'<td class="{num_class}">{i}.</td>'
            f'<td><div class="q-title">{_esc(l.get("lesson", ""))}</div>'
            f'<div class="q-detail">{_allow_bold(l.get("application", ""))}</div></td>'
            f'</tr>'
        )

    hbox_class = "hbox green" if is_won else "hbox"
    stit_class = "stit green" if is_won else "stit"

    html = f'''<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<style>{_CSS}</style></head><body>
<div class="page">
  <div class="hdr">
    <div class="tbl">
      <div class="tbl-cell hdr-left">
        <div class="{brand_class}">Factorial</div>
        <div class="type">{_esc(report_type)}</div>
        <div class="name">{_esc(company)}</div>
      </div>
      <div class="tbl-cell hdr-right">
        <div class="dates">
          {_esc(demo_datetime)}<br>
          <span class="sub">PAE · {_esc(pae_name)}</span>
        </div>
      </div>
    </div>
  </div>

  <div class="kpi"><table><tr>
    <td style="padding-left:40px"><div class="kpi-lbl">MRR</div><div class="kpi-val red">{_esc(amount_str)}</div></td>
    <td><div class="kpi-lbl">Resultado</div><div class="kpi-val {'green' if is_won else 'red'}">{_esc(outcome)}</div></td>
    <td><div class="kpi-lbl">Partner</div><div class="kpi-val">{_esc(partner)}</div></td>
    <td><div class="kpi-lbl">Stage</div><div class="kpi-val">{_esc(deal_stage)}</div></td>
    <td><div class="kpi-lbl">Días en pipeline</div><div class="kpi-val">{_esc(brief.get("days_in_pipeline", "?"))}</div></td>
  </tr></table></div>

  <div class="body-grid tbl">
    <div class="tbl-cell col-l">
      <div class="{stit_class} stit-first">Resumen del deal</div>
      {_render_bullets(brief.get("summary", []))}

      <div class="{hbox_class}">
        <div class="ht">{"Qué funcionó" if is_won else "Causa raíz de la pérdida"}</div>
        <p>{_allow_bold(brief.get("root_cause", ""))}</p>
      </div>

      <div class="{stit_class}">Timeline</div>
      {_render_bullets(brief.get("timeline", []))}
    </div>

    <div class="tbl-cell col-r">
      <div class="{stit_class} stit-first">Factores clave</div>
      <table class="numbered-table">{factors_html}</table>

      <div class="{stit_class}">Lecciones · Aplicación</div>
      <table class="numbered-table">{lessons_html}</table>

      <div class="note-block {'green' if is_won else 'red'}"><b>{"Patrón replicable." if is_won else "Acción correctiva."}</b> {_esc(brief.get("action", ""))}</div>
      <div class="note-block blue"><b>Recomendación para el equipo.</b> {_esc(brief.get("team_recommendation", ""))}</div>
    </div>
  </div>
</div>
</body></html>'''

    return weasyprint.HTML(string=html).write_pdf()
