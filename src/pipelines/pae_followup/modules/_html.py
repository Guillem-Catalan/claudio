"""
Shared HTML/CSS utilities for PDF module rendering.
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


CSS_BASE = """\
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

.tbl { display: table; width: 100%; }
.tbl-cell { display: table-cell; vertical-align: top; }

/* -- HEADER -- */
.hdr { padding: 28px 40px 0; }
.hdr-left { width: 65%; }
.hdr-right { text-align: right; vertical-align: top; }
.brand { font-size: 13px; font-weight: 600; color: #c8102e; letter-spacing: .3px; }
.type { font-size: 10px; text-transform: uppercase; letter-spacing: 2px; color: #8e8d88; margin-top: 1px; }
.name { font-size: 32px; font-weight: 700; letter-spacing: -.5px; margin-top: 2px; }
.dates { font-size: 14px; font-weight: 500; line-height: 1.4; }
.dates .sub { font-size: 10.5px; color: #8e8d88; font-weight: 400; }

/* -- KPI BAR -- */
.kpi { border-top: 1.5px solid #1a1a18; border-bottom: 1.5px solid #e4e3de; margin-top: 16px; }
.kpi table { width: 100%; border-collapse: collapse; }
.kpi td { padding: 10px 14px; vertical-align: top; width: 20%; }
.kpi-lbl { font-size: 8.5px; text-transform: uppercase; letter-spacing: 1.5px; color: #8e8d88; font-weight: 600; }
.kpi-val { font-size: 16px; font-weight: 600; margin-top: 1px; }
.kpi-val.red { color: #c8102e; }
.kpi-val.amb { color: #a86400; }

/* -- BODY 2-COL -- */
.body-grid { padding: 0 40px 40px; }
.col-l { width: 50%; padding-right: 32px; padding-top: 24px; border-right: .5px solid #e4e3de; overflow: hidden; }
.col-r { width: 50%; padding-left: 32px; padding-top: 24px; overflow: hidden; }

/* -- SECTION TITLES -- */
.stit {
    font-family: 'Courier New', Courier, monospace;
    font-size: 9px; font-weight: 500; text-transform: uppercase;
    letter-spacing: 2px; color: #c8102e;
    margin-bottom: 10px; margin-top: 24px;
}
.stit-first { margin-top: 0; }

/* -- BULLET ITEMS -- */
.bi-table { width: 100%; border-collapse: collapse; }
.bi-table td { font-size: 11.5px; line-height: 1.6; color: #5c5b57; padding: 3px 0; vertical-align: top; }
.bi-dash { width: 14px; color: #8e8d88; }
.bi-table b { color: #1a1a18; font-weight: 600; }

/* -- MEDDIC -- */
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

/* -- HIGHLIGHT BOX -- */
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

/* -- SIGNALS -- */
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

/* -- OBJECTIONS -- */
.obj-card { background: #faf9f6; padding: 12px 16px; margin-top: 10px; }
.obj-q { font-size: 11.5px; font-weight: 600; color: #1a1a18; margin-bottom: 6px; }
.obj-a { font-size: 10.5px; line-height: 1.6; color: #5c5b57; }
.obj-a b { color: #1a1a18; font-weight: 500; }

/* -- PROBABILITY -- */
.prob { background: #fdf0f0; padding: 16px 20px; margin-top: 16px; }
.prob-num { font-size: 36px; font-weight: 700; color: #c8102e; line-height: 1; width: 70px; }
.prob-num small { font-size: 16px; }
.prob-txt { font-size: 11px; line-height: 1.6; color: #5c5b57; }
.prob-txt b { color: #1a1a18; font-weight: 600; }

/* -- PAGE 2+ SHARED -- */
.p2-head { padding: 18px 32px 14px; border-bottom: 1px solid #e4e3de; }
.p2h-left { width: 75%; }
.p2h-right { text-align: right; vertical-align: bottom; }
.p2h-label { font-size: 8px; font-weight: 600; letter-spacing: 2px; text-transform: uppercase; color: #c8102e; margin-bottom: 5px; }
.p2h-title { font-size: 22px; font-weight: 600; letter-spacing: -.04em; color: #1a1a18; line-height: 1; }
.p2h-sub { font-size: 11px; color: #8e8d88; font-weight: 300; margin-top: 4px; }
.p2h-badge { background: #fdf0f0; border: 1px solid #ffccd4; padding: 5px 12px; font-size: 10px; font-weight: 500; color: #c8102e; }

/* -- EMAIL MOCK -- */
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

/* -- SLIDE SHARED -- */
.slide-body { padding: 24px 40px 40px; }
.slide-body .stit { margin-top: 20px; }
.slide-body .stit-first { margin-top: 0; }

/* -- CALL/MEETING/SLIDE SECTIONS -- */
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
.p2-time { width: 55px; font-size: 10px; font-weight: 600; color: #c8102e; letter-spacing: .5px; }

/* -- NOTE BLOCKS -- */
.note-block { margin: 10px 32px 0; padding: 9px 14px; font-size: 10.5px; line-height: 1.5; font-weight: 300; }
.note-block.blue { background: #f0f7ff; border-left: 3px solid #3b82f6; color: #1e3a5f; }
.note-block.red { background: #fdf0f0; border-left: 3px solid #c8102e; color: #3a1a22; }
.note-block.amber { background: #fef6e8; border-left: 3px solid #a86400; color: #3a2a00; }
.note-block.green { background: #edf7f1; border-left: 3px solid #12593a; color: #0a3320; }
.note-block strong, .note-block b { font-weight: 500; color: #1a1a18; }
"""


def slide_page(label: str, title: str, subtitle: str, body_html: str, badge: str = "") -> str:
    """Renders a single-page slide with header + body content."""
    badge_html = f'<span class="p2h-badge">{_esc(badge)}</span>' if badge else ""
    return f'''<div class="page">
  <div class="p2-head tbl">
    <div class="tbl-cell p2h-left">
      <div class="p2h-label">{_esc(label)}</div>
      <div class="p2h-title">{_esc(title)}</div>
      <div class="p2h-sub">{_esc(subtitle)}</div>
    </div>
    <div class="tbl-cell p2h-right">{badge_html}</div>
  </div>
  <div class="slide-body">{body_html}</div>
</div>'''


def render_slide_pdf(html_body: str, filename: str) -> bytes:
    """Wraps body HTML in full document and renders to PDF."""
    html = (
        '<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><style>'
        + CSS_BASE
        + "</style></head><body>"
        + html_body
        + "</body></html>"
    )
    import weasyprint
    return weasyprint.HTML(string=html).write_pdf()
