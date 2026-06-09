"""Generate weekly activity digest HTML/PDF."""

from datetime import date, datetime, timedelta

_MESES = {1:"ene",2:"feb",3:"mar",4:"abr",5:"may",6:"jun",7:"jul",8:"ago",9:"sep",10:"oct",11:"nov",12:"dic"}
_DAYS_ES = {0:"Lunes",1:"Martes",2:"Miércoles",3:"Jueves",4:"Viernes",5:"Sábado",6:"Domingo"}


def _esc(t) -> str:
    return (str(t) if t else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _prob_css(p):
    if p is None: return "prob-r"
    if p >= 50: return "prob-g"
    if p >= 30: return "prob-a"
    return "prob-r"


def _meddic_css(s):
    if s is None: return "mm-m"
    if int(s) >= 7: return "mm-g"
    if int(s) >= 4: return "mm-a"
    return "mm-r"


def _ev_css(t):
    return {"DEMO": "demo", "CALL": "call", "MEETING": "meeting"}.get(t, "call")


def _tb_css(t):
    return {"DEMO": "tb-demo", "CALL": "tb-call", "MEETING": "tb-meet"}.get(t, "tb-call")


def _build_event_card(ev: dict, syn: dict) -> str:
    t = ev["type"]
    prob = ev.get("prob")
    amount = ev.get("amount")
    mrr_str = f"&euro;{float(amount):,.0f}" if amount else ""
    is_top = amount and float(amount) >= 3000
    mrr_class = "ev-mrr top" if is_top else "ev-mrr"
    dur = ev.get("duration_min")
    time_str = ev["dt"][11:16] if len(ev["dt"]) > 11 else ""
    if dur and dur > 0:
        time_str += f" &middot; {dur}min"

    meddic_html = ""
    if ev.get("meddic") and ev["meddic"].get("m_score") is not None:
        m = ev["meddic"]
        parts = []
        for letter, key in [("M","m_score"),("E","e_score"),("DC","dc_score"),("DP","dp_score"),("I","i_score"),("C","c_score"),("Comp","comp_score")]:
            s = m.get(key)
            css = _meddic_css(s)
            val = int(s) if s is not None else "?"
            parts.append(f'<span class="mm {css}">{letter} {val}</span>')
        meddic_html = f'<div style="margin:4px 0 8px">{"".join(parts)}</div>'

    signals = syn.get("signals_top3", [])
    blockers = syn.get("blockers_top3", [])
    sig_html = "<br>".join(f"&bull; {_esc(s)}" for s in signals) if signals else ""
    blk_html = "<br>".join(f"&bull; {_esc(b)}" for b in blockers) if blockers else ""

    g2_html = ""
    if sig_html or blk_html:
        g2_html = '<div class="g2">'
        if sig_html:
            g2_html += f'<div class="g2-box sig"><div class="g2t">Señales</div>{sig_html}</div>'
        if blk_html:
            g2_html += f'<div class="g2-box blk"><div class="g2t">Blockers</div>{blk_html}</div>'
        g2_html += '</div>'

    ns = syn.get("next_step", "")
    ns_html = f'<div class="ns"><div class="nst">Next step</div>{_esc(ns)}</div>' if ns else ""

    return f'''
  <div class="ev {_ev_css(t)}">
    <div class="ev-hdr">
      <div class="ev-name">{_esc(ev["deal_name"])}</div>
      <div class="{mrr_class}">{mrr_str}</div>
    </div>
    <div class="ev-meta">
      <span>{time_str}</span>
      <span class="tb {_tb_css(t)}">{t}</span>
      <span class="sp">{_esc(ev.get("deal_stage","?"))}</span>
      {f'<span class="prob {_prob_css(prob)}">{prob}%</span>' if prob is not None else ''}
    </div>
    {meddic_html}
    <div class="ev-context">
      <b>Qu&eacute; pas&oacute;:</b> {_esc(syn.get("what_happened",""))}<br>
      <b>Impacto:</b> {_esc(syn.get("deal_impact",""))}
    </div>
    {g2_html}
    {ns_html}
  </div>'''


def _build_html(
    pae_name: str,
    events: list[dict],
    synthesis: dict,
    week_start: date,
    week_end: date,
) -> str:
    fecha_str = f"{week_start.day} &ndash; {(week_end - timedelta(days=1)).day} {_MESES[week_start.month]} {week_start.year}"

    n_demo = sum(1 for e in events if e["type"] == "DEMO")
    n_call = sum(1 for e in events if e["type"] == "CALL")
    n_meet = sum(1 for e in events if e["type"] == "MEETING")
    deals_touched = len(set(e["deal_name"] for e in events if e["deal_name"] != "?"))

    pills = ""
    if n_demo: pills += f'<span class="pill pill-demo">Demos &times;{n_demo}</span>'
    if n_call: pills += f'<span class="pill pill-call">Calls &times;{n_call}</span>'
    if n_meet: pills += f'<span class="pill pill-meet">Meetings &times;{n_meet}</span>'

    syn_events = synthesis.get("events", [{}] * len(events))

    by_day: dict[str, list[tuple[dict, dict]]] = {}
    for ev, se in zip(events, syn_events):
        day = ev["dt"][:10]
        if day not in by_day:
            by_day[day] = []
        by_day[day].append((ev, se))

    all_days = [(week_start + timedelta(days=i)).isoformat() for i in range(5)]
    days_html = []
    for day_str in all_days:
        d = datetime.fromisoformat(day_str)
        day_name = _DAYS_ES.get(d.weekday(), "?")
        day_events = by_day.get(day_str, [])

        dh = f'<div class="day-section">\n'
        dh += f'  <div class="day-title">{day_name} {d.day} {_MESES[d.month]}'
        if day_events:
            dh += f' &middot; {len(day_events)} interacciones'
        dh += '</div>\n'

        if not day_events:
            dh += '  <div style="color:var(--ink3);font-size:11px;font-style:italic;padding:8px 0">Sin actividad registrada.</div>\n'
        else:
            for ev, se in day_events:
                dh += _build_event_card(ev, se)

        dh += '\n</div>'
        days_html.append(dh)

    coaching = synthesis.get("coaching", [])
    coaching_html = "<br><br>".join(_esc(c) for c in coaching)

    today = date.today()
    gen_date = f"{today.day} {_MESES[today.month]} {today.year}"

    return f'''\
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<style>
:root{{--ink:#1a1a18;--ink2:#5c5b57;--ink3:#8e8d88;--bg:#faf9f6;--card:#fff;--bdr:#e4e3de;--bdr-l:#f0efe9;--red:#c8102e;--red-bg:#fdf0f0;--red-tx:#9a0c22;--grn:#1a7a4c;--grn-bg:#edf7f1;--grn-tx:#12593a;--amb:#a86400;--amb-bg:#fef6e8;--amb-tx:#7a4900;--blu:#1a5fa5;--blu-bg:#edf3fb;--blu-tx:#0f4478;--ff:'Helvetica Neue',Helvetica,Arial,sans-serif;--fd:Georgia,serif}}
*{{margin:0;padding:0;box-sizing:border-box}}
@page{{size:A4;margin:12mm}}
body{{font-family:var(--ff);font-size:12.5px;line-height:1.5;color:var(--ink);background:var(--bg)}}
.page{{max-width:1100px;margin:0 auto;padding:36px 44px;background:var(--card)}}
.hdr{{display:flex;justify-content:space-between;align-items:flex-start;padding-bottom:16px;border-bottom:2.5px solid var(--ink)}}
.hdr h1{{font-family:var(--fd);font-weight:500;font-size:22px;letter-spacing:-.3px;line-height:1.15}}
.hdr h1 em{{font-style:normal;color:var(--red)}}
.hdr .sub{{font-size:11px;color:var(--ink2);margin-top:3px}}
.stats-box{{text-align:right;flex-shrink:0}}
.stats-box .lbl{{font-size:9px;text-transform:uppercase;letter-spacing:1.2px;color:var(--ink3);font-weight:600}}
.stats-box .val{{font-family:var(--fd);font-size:30px;font-weight:700;letter-spacing:-1px;line-height:1.1;margin-top:2px}}
.stats-box .det{{font-size:10px;color:var(--ink3);margin-top:2px}}
.pills{{display:flex;flex-wrap:wrap;gap:5px;margin-top:10px}}
.pill{{font-size:10px;font-weight:500;padding:2px 10px;border-radius:20px;white-space:nowrap}}
.pill-demo{{background:var(--red-bg);color:var(--red-tx)}}.pill-call{{background:var(--blu-bg);color:var(--blu-tx)}}.pill-meet{{background:var(--grn-bg);color:var(--grn-tx)}}
.summary{{margin-top:24px;padding:16px 20px;border-radius:8px;background:var(--bg);font-size:11.5px;line-height:1.65;color:var(--ink2)}}
.summary b{{color:var(--ink);font-weight:600}}
.day-section{{margin-top:28px}}
.day-title{{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:var(--ink);padding-bottom:6px;border-bottom:2px solid var(--ink);margin-bottom:14px}}
.ev{{border:1px solid var(--bdr);border-radius:8px;padding:16px 20px;margin-bottom:12px}}
.ev.demo{{border-left:4px solid var(--red)}}.ev.call{{border-left:4px solid var(--blu)}}.ev.meeting{{border-left:4px solid var(--grn)}}
.ev-hdr{{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:4px}}
.ev-name{{font-weight:700;font-size:13.5px}}
.ev-mrr{{font-family:var(--fd);font-weight:700;font-size:15px}}
.ev-mrr.top{{font-size:18px;color:var(--red)}}
.ev-meta{{display:flex;flex-wrap:wrap;gap:8px;font-size:10px;color:var(--ink3);margin-bottom:8px;align-items:center}}
.tb{{font-size:8.5px;font-weight:600;padding:2px 8px;border-radius:10px;text-transform:uppercase;letter-spacing:.5px}}
.tb-demo{{background:var(--red-bg);color:var(--red-tx)}}.tb-call{{background:var(--blu-bg);color:var(--blu-tx)}}.tb-meet{{background:var(--grn-bg);color:var(--grn-tx)}}
.sp{{font-size:9px;font-weight:500;padding:2px 8px;border-radius:10px;background:var(--bg);color:var(--ink3)}}
.prob{{font-size:9px;font-weight:600;padding:2px 8px;border-radius:10px}}
.prob-g{{background:var(--grn-bg);color:var(--grn-tx)}}.prob-a{{background:var(--amb-bg);color:var(--amb-tx)}}.prob-r{{background:var(--red-bg);color:var(--red-tx)}}
.ev-context{{font-size:11px;line-height:1.6;color:var(--ink2)}}
.ev-context b{{color:var(--ink);font-weight:600}}
.g2{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:8px}}
.g2-box{{font-size:10.5px;line-height:1.5;padding:8px 12px;border-radius:6px}}
.g2-box.sig{{background:var(--grn-bg);color:var(--grn-tx)}}.g2-box.blk{{background:var(--red-bg);color:var(--red-tx)}}
.g2-box .g2t{{font-size:8px;font-weight:600;text-transform:uppercase;letter-spacing:.8px;margin-bottom:3px}}
.ns{{background:var(--blu-bg);border-radius:6px;padding:8px 12px;margin-top:8px;font-size:10.5px;line-height:1.5;color:var(--blu-tx)}}
.ns .nst{{font-size:8px;font-weight:600;text-transform:uppercase;letter-spacing:.8px;color:var(--blu);margin-bottom:2px}}
.mm{{font-size:9px;font-weight:600;padding:2px 7px;border-radius:8px;display:inline-block;margin-right:2px}}
.mm-g{{background:#d4edda;color:#12593a}}.mm-a{{background:#fef6e8;color:#7a4900}}.mm-r{{background:#fce8e8;color:#9a0c22}}.mm-m{{background:#f3f2ed;color:#5c5b57}}
.stit{{font-size:9px;font-weight:600;text-transform:uppercase;letter-spacing:1.5px;color:var(--ink3);margin-bottom:8px;padding-bottom:5px;border-bottom:1px solid var(--bdr-l);margin-top:28px}}
.stit.red{{color:var(--red);border-color:var(--red)}}
.note{{margin-top:12px;padding:12px 16px;border-radius:6px;background:var(--bg);font-size:11px;line-height:1.6;color:var(--ink2)}}
.note b{{color:var(--ink);font-weight:600}}
.foot{{font-size:9.5px;color:var(--ink3);margin-top:24px;padding-top:10px;border-top:.5px solid var(--bdr);text-align:center}}
</style>
</head>
<body>
<div class="page">

<div class="hdr">
  <div>
    <h1>{_esc(pae_name)} &mdash; <em>weekly activity</em></h1>
    <div class="sub">{fecha_str} &middot; Todas las interacciones &middot; Para Team Lead</div>
    <div class="pills">{pills}</div>
  </div>
  <div class="stats-box">
    <div class="lbl">Actividad semanal</div>
    <div class="val">{len(events)}</div>
    <div class="det">{deals_touched} deals tocados</div>
  </div>
</div>

<div class="summary">
  <b>Resumen para el TL:</b> {_esc(synthesis.get("summary", ""))}
</div>

{"".join(days_html)}

<div class="stit red">Observaciones &mdash; coaching para el TL</div>
<div class="note">{coaching_html}</div>

<div class="foot">Generado por Claudio &middot; calls + pae_audits + audit_demos + deal_meetings + snapshots &middot; {gen_date}</div>

</div>
</body>
</html>'''


def generate_pdf(
    pae_name: str,
    events: list[dict],
    synthesis: dict,
    week_start: date,
    week_end: date,
) -> bytes:
    import weasyprint
    html = _build_html(pae_name, events, synthesis, week_start, week_end)
    return weasyprint.HTML(string=html).write_pdf()


def generate_html(
    pae_name: str,
    events: list[dict],
    synthesis: dict,
    week_start: date,
    week_end: date,
) -> str:
    return _build_html(pae_name, events, synthesis, week_start, week_end)
