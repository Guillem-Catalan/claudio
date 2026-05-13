"""
PDF template for stalled deals — re-engagement plan.
Single page with: situation analysis, re-engagement sequence, email/call templates.
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
.brand { font-size: 13px; font-weight: 600; color: #a86400; letter-spacing: .3px; }
.type { font-size: 10px; text-transform: uppercase; letter-spacing: 2px; color: #8e8d88; margin-top: 1px; }
.name { font-size: 32px; font-weight: 700; letter-spacing: -.5px; margin-top: 2px; }
.dates { font-size: 14px; font-weight: 500; line-height: 1.4; }
.dates .sub { font-size: 10.5px; color: #8e8d88; font-weight: 400; }

.kpi { border-top: 1.5px solid #1a1a18; border-bottom: 1.5px solid #e4e3de; margin-top: 16px; }
.kpi table { width: 100%; border-collapse: collapse; }
.kpi td { padding: 10px 14px; vertical-align: top; width: 25%; }
.kpi-lbl { font-size: 8.5px; text-transform: uppercase; letter-spacing: 1.5px; color: #8e8d88; font-weight: 600; }
.kpi-val { font-size: 16px; font-weight: 600; margin-top: 1px; }
.kpi-val.amb { color: #a86400; }
.kpi-val.red { color: #c8102e; }

.body { padding: 24px 40px 40px; }
.stit {
    font-family: 'Courier New', Courier, monospace;
    font-size: 9px; font-weight: 500; text-transform: uppercase;
    letter-spacing: 2px; color: #a86400; margin-bottom: 10px; margin-top: 24px;
}
.stit-first { margin-top: 0; }

.bi-table { width: 100%; border-collapse: collapse; }
.bi-table td { font-size: 11.5px; line-height: 1.6; color: #5c5b57; padding: 3px 0; vertical-align: top; }
.bi-dash { width: 14px; color: #8e8d88; }
.bi-table b { color: #1a1a18; font-weight: 600; }

.hbox {
    border-left: 3px solid #a86400; background: #fef6e8;
    padding: 12px 16px; margin-top: 12px;
}
.hbox .ht {
    font-size: 10px; font-weight: 600; text-transform: uppercase;
    letter-spacing: 1px; color: #a86400; margin-bottom: 4px;
}
.hbox p { font-size: 11px; line-height: 1.6; color: #5c5b57; }
.hbox p b { color: #1a1a18; font-weight: 600; }

.seq-table { width: 100%; border-collapse: collapse; }
.seq-table td { padding: 10px 0; vertical-align: top; border-bottom: .5px solid #f0efe9; font-size: 11px; line-height: 1.55; color: #5c5b57; }
.seq-table tr:last-child td { border-bottom: none; }
.seq-num { width: 28px; font-size: 14px; font-weight: 600; color: #a86400; }
.seq-day { width: 55px; font-size: 10px; font-weight: 600; color: #a86400; letter-spacing: .5px; }
.seq-q { font-weight: 500; color: #1a1a18; }
.seq-detail { font-size: 10.5px; color: #8e8d88; margin-top: 2px; }

.note-block { margin: 10px 0 0; padding: 9px 14px; font-size: 10.5px; line-height: 1.5; font-weight: 300; }
.note-block.amber { background: #fef6e8; border-left: 3px solid #a86400; color: #3a2a00; }
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
    deal_stage = data["deal"].get("deal_stage", "?")
    days_stalled = _esc(brief.get("days_stalled", "?"))

    sequence_html = ""
    for i, step in enumerate(brief.get("sequence", []), 1):
        sequence_html += (
            f'<tr>'
            f'<td class="seq-num">{i}.</td>'
            f'<td class="seq-day">{_esc(step.get("day", ""))}</td>'
            f'<td><div class="seq-q">{_esc(step.get("action", ""))}</div>'
            f'<div class="seq-detail">{_allow_bold(step.get("detail", ""))}</div></td>'
            f'</tr>'
        )

    html = f'''<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<style>{_CSS}</style></head><body>
<div class="page">
  <div class="hdr">
    <div class="tbl">
      <div class="tbl-cell hdr-left">
        <div class="brand">Factorial</div>
        <div class="type">Re-engagement Plan</div>
        <div class="name">{_esc(company)}</div>
      </div>
      <div class="tbl-cell hdr-right">
        <div class="dates">
          {_esc(demo_datetime)}<br>
          <span class="sub">Stage · {_esc(deal_stage)}</span>
        </div>
      </div>
    </div>
  </div>

  <div class="kpi"><table><tr>
    <td style="padding-left:40px"><div class="kpi-lbl">MRR</div><div class="kpi-val red">{_esc(amount_str)}</div></td>
    <td><div class="kpi-lbl">Partner</div><div class="kpi-val">{_esc(partner)}</div></td>
    <td><div class="kpi-lbl">Días parado</div><div class="kpi-val amb">{days_stalled}</div></td>
    <td><div class="kpi-lbl">Urgencia</div><div class="kpi-val amb">{_esc(brief.get("urgency", "?"))}</div></td>
  </tr></table></div>

  <div class="body">
    <div class="stit stit-first">Diagnóstico</div>
    {_render_bullets(brief.get("diagnosis", []))}

    <div class="hbox">
      <div class="ht">Por qué se paró</div>
      <p>{_allow_bold(brief.get("stall_reason", ""))}</p>
    </div>

    <div class="stit">Secuencia de re-engagement</div>
    <table class="seq-table">{sequence_html}</table>

    <div class="stit">Qué decir</div>
    {_render_bullets(brief.get("talking_points", []))}

    <div class="stit">Qué NO hacer</div>
    {_render_bullets(brief.get("avoid", []))}

    <div class="note-block amber"><b>Objetivo.</b> {_esc(brief.get("objective", ""))}</div>
    <div class="note-block blue"><b>Trigger events.</b> {_esc(brief.get("trigger_events", ""))}</div>
  </div>
</div>
</body></html>'''

    return weasyprint.HTML(string=html).write_pdf()
