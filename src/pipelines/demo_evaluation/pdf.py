"""Generate weekly demo coaching PDF from HTML template."""

from collections import Counter
from datetime import date, timedelta

import weasyprint

STAGE_CSS = {
    "Product Alignment": "s-pa",
    "Pricing and Packaging": "s-pp",
    "Contracting": "s-tr",
    "Demo Booked": "s-db",
    "New Deals": "s-nd",
    "Closed Won": "s-cw",
    "Closed Lost": "s-cl",
    "On Hold": "s-nd",
    "To Reschedule": "s-nd",
    "Discovery": "s-pa",
    "Meeting Booked": "s-db",
    "Closed Pending Payment": "s-cw",
}

STAGE_PILL_CSS = {
    "Product Alignment": "p-pa",
    "Pricing and Packaging": "p-pp",
    "Contracting": "p-tr",
    "Demo Booked": "p-db",
    "New Deals": "p-nd",
    "Closed Won": "p-cw",
    "Closed Lost": "p-cl",
}

BANT_CSS = {"Confirmed": "bt-c", "Partial": "bt-p", "Missing": "bt-m", "N/A": "bt-n"}

STATUS_BADGE = {"rojo": "r", "ámbar": "a", "verde": "g"}
STATUS_COLOR_VAR = {
    "rojo": "var(--red-tx)",
    "ámbar": "var(--amb-tx)",
    "verde": "var(--grn-tx)",
}

_CIRCLED = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩"]

_MESES = {
    1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
    7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic",
}


def _esc(text) -> str:
    return (str(text) if text else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _format_date_short(val) -> str:
    s = str(val)[:10] if val else ""
    if len(s) == 10:
        parts = s.split("-")
        if len(parts) == 3:
            d, m = int(parts[2]), int(parts[1])
            return f"{d} {_MESES.get(m, parts[1])}"
    return s or "—"


def _week_range_str(week_start: date, week_end: date) -> str:
    fri = week_start + timedelta(days=4)
    end = week_end - timedelta(days=1)
    return f"{week_start.day} {_MESES[week_start.month]} — {end.day} {_MESES[end.month]}"


def _build_stage_pills(audit_rows: list[dict], deals_data: dict) -> str:
    stages = []
    for row in audit_rows:
        deal = deals_data.get(row.get("deal_ref"), {})
        stage = deal.get("deal_stage") or row.get("deal_stage") or "?"
        stages.append(stage)
    counts = Counter(stages)
    pills = []
    for stage, count in counts.most_common():
        css = STAGE_PILL_CSS.get(stage, "p-nd")
        pills.append(f'<span class="pill {css}">{_esc(stage)} &times;{count}</span>')
    return "\n      ".join(pills)


def _build_deals_table(
    audit_rows: list[dict],
    deals_data: dict,
    pbd_names: dict[str, str],
    bant_per_deal: dict[str, dict],
) -> str:
    rows_html = []
    for row in audit_rows:
        deal_ref = row.get("deal_ref")
        deal = deals_data.get(deal_ref, {}) if deal_ref else {}
        deal_name = row.get("deal_name") or deal.get("deal_name") or "?"
        deal_name_esc = _esc(deal_name)
        demo_date = _format_date_short(row.get("demo_date"))
        amount = row.get("amount") or deal.get("amount")
        mrr = f"€{float(amount):,.0f}" if amount is not None else "—"
        stage = deal.get("deal_stage") or row.get("deal_stage") or "?"
        stage_css = STAGE_CSS.get(stage, "s-nd")
        age = deal.get("deal_age_days") or "?"
        pbd_name = _esc(
            deal.get("pbd") or pbd_names.get(deal_ref, "") or row.get("pbd") or "—"
        )

        bant = bant_per_deal.get(deal_name, {})
        bant_pills = ""
        for letter, key in [("B", "budget"), ("A", "authority"), ("N", "need"), ("T", "timing")]:
            status = bant.get(key, "Missing")
            css = BANT_CSS.get(status, "bt-n")
            bant_pills += f'<span class="bt {css}">{letter}</span>'

        rows_html.append(
            f"<tr>"
            f"<td>{deal_name_esc}</td>"
            f"<td>{demo_date}</td>"
            f'<td class="r">{mrr}</td>'
            f'<td><span class="stag {stage_css}">{_esc(stage)}</span></td>'
            f'<td class="r">{age}d</td>'
            f"<td>{pbd_name}</td>"
            f"<td>{bant_pills}</td>"
            f"</tr>"
        )
    return "\n      ".join(rows_html)


def _build_meddic(synthesis: dict) -> str:
    pillars = [
        ("M", "Metrics", "m"),
        ("E", "Economic buyer", "e"),
        ("DC", "Decision criteria", "dc"),
        ("DP", "Decision process", "dp"),
        ("I", "Identify pain", "i"),
        ("C", "Champion", "c"),
    ]
    rows = []
    for abbr, name, key in pillars:
        status = synthesis.get(f"{key}_status", "rojo")
        text = _esc(synthesis.get(f"{key}_text", "—"))
        badge = STATUS_BADGE.get(status, "r")
        color = STATUS_COLOR_VAR.get(status, "var(--red-tx)")
        rows.append(
            f'<div class="mrow">'
            f'<div class="mbdg {badge}">{abbr}</div>'
            f'<div class="mtxt">'
            f'<div class="tl">{name} <span style="color:{color}">· {_esc(status)}</span></div>'
            f'<div class="td">{text}</div>'
            f'</div></div>'
        )
    return "\n  ".join(rows)


def _build_signals(synthesis: dict) -> str:
    signals = synthesis.get("buyer_signals") or []
    if not signals:
        return '<div class="sig-item">—</div>'
    items = []
    for s in signals:
        deal = _esc(s.get("deal", ""))
        sig_list = s.get("signals") or []
        if isinstance(sig_list, list):
            text = "; ".join(_esc(sig) for sig in sig_list if sig)
        else:
            text = _esc(str(sig_list))
        items.append(f'<div class="sig-item"><b>{deal}:</b> {text}</div>')
    return "\n    ".join(items)


def _build_objections(synthesis: dict) -> str:
    objs = synthesis.get("objections") or []
    if not objs:
        return '<div class="sig-item">—</div>'
    items = []
    for o in objs:
        cat = _esc(o.get("category", ""))
        text = _esc(o.get("text", ""))
        items.append(f'<div class="sig-item"><b>{cat}:</b> {text}</div>')
    return "\n    ".join(items)


def _build_improvements(synthesis: dict) -> str:
    imps = synthesis.get("improvements") or []
    if not imps:
        return ""
    items = []
    for i, imp in enumerate(imps):
        ic = _CIRCLED[i] if i < len(_CIRCLED) else f"({i+1})"
        title = _esc(imp.get("title", ""))
        text = _esc(imp.get("text", ""))
        items.append(
            f'<div class="imp-row">'
            f'<div class="imp-ic">{ic}</div>'
            f'<div class="imp-tx"><b>{title}</b> {text}</div>'
            f'</div>'
        )
    return "\n    ".join(items)


def generate_pdf(
    pae_name: str,
    week_start: date,
    week_end: date,
    audit_rows: list[dict],
    deals_data: dict[str, dict],
    pbd_names: dict[str, str],
    synthesis: dict,
) -> bytes:
    today = date.today()
    fecha_envio = f"{today.day} {_MESES[today.month]} {today.year}"
    semana = f"W{week_start.isocalendar()[1]}"
    semana_rango = _week_range_str(week_start, week_end)
    mrr_total = sum(float(r.get("amount") or 0) for r in audit_rows)
    mrr_str = f"€{mrr_total:,.0f}" if mrr_total else "—"

    bant_per_deal = {}
    for item in (synthesis.get("bant_per_deal") or []):
        bant_per_deal[item.get("deal", "")] = item

    stage_pills = _build_stage_pills(audit_rows, deals_data)
    deals_table = _build_deals_table(audit_rows, deals_data, pbd_names, bant_per_deal)
    meddic_html = _build_meddic(synthesis)
    meddic_intro = _esc(synthesis.get("meddic_intro_note", ""))
    signals_html = _build_signals(synthesis)
    objections_html = _build_objections(synthesis)
    improvements_html = _build_improvements(synthesis)
    handover_note = _esc(synthesis.get("pbd_handover_note", "—"))

    html = f'''\
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<style>
:root{{--ink:#1a1a18;--ink2:#5c5b57;--ink3:#8e8d88;--bg:#faf9f6;--card:#fff;--bdr:#e4e3de;--bdr-l:#f0efe9;--red:#c8102e;--red-bg:#fdf0f0;--red-tx:#9a0c22;--grn:#1a7a4c;--grn-bg:#edf7f1;--grn-tx:#12593a;--amb:#a86400;--amb-bg:#fef6e8;--amb-tx:#7a4900;--blu:#1a5fa5;--blu-bg:#edf3fb;--blu-tx:#0f4478;--ff:'Helvetica Neue',Helvetica,Arial,sans-serif;--fd:Georgia,serif}}
*{{margin:0;padding:0;box-sizing:border-box}}
@page{{size:A4 landscape;margin:12mm}}
body{{font-family:var(--ff);font-size:12.5px;line-height:1.5;color:var(--ink);background:var(--bg);-webkit-font-smoothing:antialiased}}
.page{{max-width:1080px;margin:0 auto;padding:36px 44px;background:var(--card)}}
.hdr{{display:flex;justify-content:space-between;align-items:flex-start;padding-bottom:16px;border-bottom:2.5px solid var(--ink)}}
.hdr h1{{font-family:var(--fd);font-weight:500;font-size:24px;letter-spacing:-.4px;line-height:1.15}}
.hdr h1 em{{font-style:normal;color:var(--red)}}
.hdr .sub{{font-size:11.5px;color:var(--ink2);margin-top:3px}}
.mrr-box{{text-align:right;flex-shrink:0}}
.mrr-box .lbl{{font-size:9.5px;text-transform:uppercase;letter-spacing:1.2px;color:var(--ink3);font-weight:600}}
.mrr-box .val{{font-family:var(--fd);font-size:34px;font-weight:700;letter-spacing:-1px;line-height:1.1;margin-top:2px}}
.mrr-box .det{{font-size:10.5px;color:var(--ink3);margin-top:2px}}
.pills{{display:flex;flex-wrap:wrap;gap:5px;margin-top:10px}}
.pill{{font-size:10px;font-weight:500;padding:2px 10px;border-radius:20px;white-space:nowrap}}
.p-pa{{background:var(--blu-bg);color:var(--blu-tx)}}.p-tr{{background:var(--amb-bg);color:var(--amb-tx)}}.p-cl{{background:var(--red-bg);color:var(--red-tx)}}.p-cw{{background:var(--grn-bg);color:var(--grn-tx)}}.p-pp{{background:#e8f0fe;color:#1a5fa5}}.p-nd{{background:#f3f2ed;color:#5c5b57}}.p-db{{background:var(--grn-bg);color:var(--grn-tx)}}
.stit{{font-size:9.5px;font-weight:600;text-transform:uppercase;letter-spacing:1.5px;color:var(--ink3);margin-bottom:8px;padding-bottom:5px;border-bottom:1px solid var(--bdr-l)}}
.stit.red{{color:var(--red);border-color:var(--red)}}
.stit.grn{{color:var(--grn);border-color:var(--grn)}}
.dtbl{{width:100%;border-collapse:collapse;font-size:11px;margin-top:6px}}
.dtbl th{{font-size:9px;font-weight:600;text-transform:uppercase;letter-spacing:.7px;color:var(--ink3);text-align:left;padding:5px 5px 5px 0;border-bottom:1.5px solid var(--ink)}}
.dtbl th.r{{text-align:right}}
.dtbl td{{padding:6px 5px 6px 0;border-bottom:.5px solid var(--bdr-l);vertical-align:middle}}
.dtbl td.r{{text-align:right;font-variant-numeric:tabular-nums}}
.dtbl tr:last-child td{{border-bottom:1.5px solid var(--bdr)}}
.stag{{font-size:9.5px;font-weight:500;padding:2px 8px;border-radius:11px;white-space:nowrap;display:inline-block}}
.s-pa{{background:var(--blu-bg);color:var(--blu-tx)}}.s-tr{{background:var(--amb-bg);color:var(--amb-tx)}}.s-cl{{background:var(--red-bg);color:var(--red-tx)}}.s-cw{{background:var(--grn-bg);color:var(--grn-tx)}}.s-pp{{background:#e8f0fe;color:#1a5fa5}}.s-nd{{background:#f3f2ed;color:#5c5b57}}.s-db{{background:var(--grn-bg);color:var(--grn-tx)}}
.bt{{font-size:9px;font-weight:500;padding:1px 6px;border-radius:8px;display:inline-block;margin:0 1px}}
.bt-c{{background:#d4edda;color:#12593a}}.bt-p{{background:#fef6e8;color:#7a4900}}.bt-m{{background:#fce8e8;color:#9a0c22}}.bt-n{{background:#f3f2ed;color:#8e8d88}}
.g2{{display:grid;grid-template-columns:1fr 1fr;gap:28px;margin-top:24px}}
.mdet{{margin-top:14px}}
.mrow{{display:flex;gap:8px;padding:9px 0;border-bottom:.5px solid var(--bdr-l)}}
.mrow:last-child{{border-bottom:none}}
.mbdg{{min-width:24px;height:22px;border-radius:4px;display:inline-flex;align-items:center;justify-content:center;font-size:10.5px;font-weight:600;flex-shrink:0;margin-top:1px}}
.mbdg.r{{background:#fce8e8;color:#9a0c22}}.mbdg.a{{background:var(--amb-bg);color:var(--amb-tx)}}.mbdg.g{{background:var(--grn-bg);color:var(--grn-tx)}}
.mtxt{{flex:1}}
.mtxt .tl{{font-weight:600;font-size:11.5px}}
.mtxt .td{{font-size:11px;color:var(--ink2);margin-top:2px;line-height:1.55}}
.sig-item{{font-size:10.5px;line-height:1.5;color:var(--ink2);padding:5px 0;border-bottom:.5px solid var(--bdr-l)}}
.sig-item:last-child{{border-bottom:none}}
.sig-item b{{color:var(--ink);font-weight:500}}
.imp{{margin-top:6px}}
.imp-row{{display:flex;gap:8px;padding:7px 0;border-bottom:.5px solid var(--bdr-l);font-size:10.5px;line-height:1.55}}
.imp-row:last-child{{border-bottom:none}}
.imp-ic{{width:18px;height:18px;border-radius:50%;background:var(--blu-bg);display:flex;align-items:center;justify-content:center;flex-shrink:0;margin-top:1px;font-size:10px;color:var(--blu-tx)}}
.imp-tx{{color:var(--ink2);flex:1}}
.imp-tx b{{color:var(--ink);font-weight:500}}
.note{{margin-top:16px;padding:12px 16px;border-radius:6px;background:var(--bg);font-size:11px;line-height:1.6;color:var(--ink2)}}
.note b{{color:var(--ink);font-weight:500}}
.foot{{font-size:9.5px;color:var(--ink3);margin-top:24px;padding-top:10px;border-top:.5px solid var(--bdr);text-align:center}}
</style>
</head>
<body>
<div class="page">

<div class="hdr">
  <div>
    <h1>{_esc(pae_name)} — <em>weekly demo coaching</em></h1>
    <div class="sub">Demos de la semana {_esc(semana_rango)} · Enviado {fecha_envio}</div>
    <div class="pills">
      {stage_pills}
    </div>
  </div>
  <div class="mrr-box">
    <div class="lbl">MRR demos semana</div>
    <div class="val">{mrr_str}</div>
    <div class="det">{len(audit_rows)} demos esta semana</div>
  </div>
</div>

<div style="margin-top:22px">
  <div class="stit">Demos de la semana · stage desde tabla Deals</div>
  <table class="dtbl">
    <thead><tr><th>Deal</th><th>Demo</th><th class="r">MRR</th><th>Stage (Deals)</th><th class="r">Edad</th><th>PBD</th><th>BANT pre-demo</th></tr></thead>
    <tbody>
      {deals_table}
    </tbody>
  </table>
  <div style="display:flex;gap:10px;margin-top:8px;font-size:10px;color:var(--ink3)">
    <span><span class="bt bt-c" style="font-size:8px">X</span> Confirmed</span>
    <span><span class="bt bt-p" style="font-size:8px">X</span> Partial</span>
    <span><span class="bt bt-m" style="font-size:8px">X</span> Missing</span>
  </div>
</div>

<div class="mdet" style="margin-top:28px">
  <div class="stit red">Estado MEDDIC — análisis cualitativo</div>
  <div class="note" style="margin-top:0;margin-bottom:12px">{meddic_intro}</div>
  {meddic_html}
</div>

<div class="g2" style="margin-top:24px">
  <div>
    <div class="stit grn">Señales de compra</div>
    {signals_html}
  </div>
  <div>
    <div class="stit red">Objeciones y blockers</div>
    {objections_html}
  </div>
</div>

<div style="margin-top:24px">
  <div class="stit">Improvements — patrones y acciones concretas</div>
  <div class="imp">
    {improvements_html}
  </div>
</div>

<div style="margin-top:24px">
  <div class="stit">Nota sobre el handover PBD → PAE</div>
  <div class="note">{handover_note}</div>
</div>

<div class="foot">Generado por Claudio · Datos: Deals + audit_demos + deal_context · {fecha_envio}</div>

</div>
</body>
</html>'''

    return weasyprint.HTML(string=html).write_pdf()
