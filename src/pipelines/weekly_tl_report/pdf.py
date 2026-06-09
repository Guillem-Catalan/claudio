"""Generate unified weekly TL report PDF (activity + pipeline review)."""

from datetime import date, timedelta

_MESES = {1:"ene",2:"feb",3:"mar",4:"abr",5:"may",6:"jun",7:"jul",8:"ago",9:"sep",10:"oct",11:"nov",12:"dic"}
_DAYS_ES = {0:"Lunes",1:"Martes",2:"Miércoles",3:"Jueves",4:"Viernes",5:"Sábado",6:"Domingo"}


def _esc(t) -> str:
    return (str(t) if t else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _type_css(mt):
    return {"first_demo": "type-demo", "follow_up": "type-fu", "closing": "type-close"}.get(mt, "type-fu")


def _type_label(mt):
    return {"first_demo": "DEMO", "follow_up": "FOLLOW-UP", "closing": "CLOSING"}.get(mt, mt.upper())


def _prob_css(p):
    if p is None: return "prob-r"
    if p >= 50: return "prob-g"
    if p >= 30: return "prob-a"
    return "prob-r"


def _quality_css(q):
    if q is None: return "q-na"
    if q >= 7: return "q-g"
    if q >= 5: return "q-a"
    return "q-r"


def _mrr_fmt(amount):
    if amount is None: return "—"
    try:
        v = float(amount)
        if v >= 1000: return f"€{v/1000:.1f}K"
        return f"€{v:.0f}"
    except: return "—"


def _bullets_html(text, color="gray"):
    if not text: return ""
    lines = [l.strip() for l in str(text).split("\n") if l.strip()]
    return "".join(f'<div style="font-size:11px;color:#{_bullet_color(color)};margin:2px 0;">• {_esc(l)}</div>' for l in lines[:5])


def _bullet_color(c):
    return {"green": "16a34a", "red": "dc2626", "blue": "2563eb", "gray": "6b7280"}.get(c, "6b7280")


def _meeting_card_html(m: dict) -> str:
    ev = m.get("evaluation", {}) or {}
    mt = m["meeting_type"]
    qs = ev.get("quality_score")
    time_str = (m.get("meeting_start") or "")[:16].split("T")[-1] if m.get("meeting_start") else ""
    has_tr = "🎙️" if m.get("has_call") else "📅"

    card = f'''
    <div style="background:white;border:1px solid #e5e7eb;border-radius:10px;padding:14px;margin:8px 0;">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
        <div style="display:flex;align-items:center;gap:8px;">
          <span class="{_type_css(mt)}">{_type_label(mt)}</span>
          <span style="font-weight:600;font-size:13px;">{_esc(m.get("deal_name", "?"))}</span>
          <span style="font-size:11px;color:#9ca3af;">{has_tr} {time_str}</span>
        </div>
        <div style="display:flex;align-items:center;gap:8px;">
          <span style="font-size:11px;color:#6b7280;">{_mrr_fmt(m.get("amount"))}</span>
          <span class="{_quality_css(qs)}">{qs or "—"}/10</span>
        </div>
      </div>
      <div style="font-size:11px;color:#374151;margin-bottom:6px;">{_esc(ev.get("meeting_summary", "Sin evaluación disponible"))}</div>
    '''

    if mt == "first_demo" and ev:
        scores = " ".join(
            f'<span style="font-size:10px;font-weight:600;background:#f3f4f6;padding:2px 6px;border-radius:4px;">{k}={ev.get(f"{k.lower()}_score", "?")}</span>'
            for k in ["M", "E", "DC", "DP", "I", "C"]
        )
        card += f'<div style="margin:6px 0;">{scores}</div>'

    if mt == "follow_up" and ev:
        if ev.get("blockers_resolved"):
            card += f'<div style="font-size:10px;color:#16a34a;margin:4px 0;">✓ Resuelto: {_esc(ev["blockers_resolved"][:150])}</div>'
        if ev.get("blockers_remaining"):
            card += f'<div style="font-size:10px;color:#dc2626;margin:4px 0;">✗ Pendiente: {_esc(ev["blockers_remaining"][:150])}</div>'

    if mt == "closing" and ev:
        if ev.get("negotiation_assessment"):
            card += f'<div style="font-size:10px;color:#374151;margin:4px 0;">{_esc(ev["negotiation_assessment"][:200])}</div>'

    if ev.get("coaching_note"):
        card += f'<div style="background:#eff6ff;border-radius:6px;padding:6px 10px;font-size:10px;color:#1d4ed8;margin-top:6px;">TL: {_esc(ev["coaching_note"])}</div>'

    card += '</div>'
    return card


def _pipeline_card_html(q: dict, synth_deal: dict | None = None) -> str:
    d, s = q["deal"], q["snap"]
    prob = s.get("close_probability")
    border_color = "#16a34a" if (prob or 0) >= 50 else "#f59e0b" if (prob or 0) >= 30 else "#ef4444"

    card = f'''
    <div style="background:white;border:1px solid #e5e7eb;border-left:4px solid {border_color};border-radius:10px;padding:14px;margin:8px 0;">
      <div style="display:flex;justify-content:space-between;margin-bottom:6px;">
        <span style="font-weight:600;font-size:13px;">{_esc(d.get("deal_name", "?"))}</span>
        <div style="display:flex;gap:8px;align-items:center;">
          <span style="font-size:11px;color:#6b7280;">{_mrr_fmt(d.get("amount"))}</span>
          <span class="{_prob_css(prob)}">{prob or "?"}%</span>
        </div>
      </div>
      <div style="font-size:10px;color:#9ca3af;margin-bottom:6px;">{_esc(d.get("deal_stage", ""))} · {d.get("deal_age_days", "?")}d</div>
    '''

    scores = " ".join(
        f'<span style="font-size:10px;font-weight:600;background:#f3f4f6;padding:2px 6px;border-radius:4px;">{k}={s.get(f"{k.lower()}_score", "?")}</span>'
        for k in ["M", "E", "DC", "DP", "I", "C"]
    )
    card += f'<div style="margin:6px 0;">{scores}</div>'

    if synth_deal:
        card += f'<div style="font-size:11px;color:#374151;margin:6px 0;">{_esc(synth_deal.get("context", ""))}</div>'
        if synth_deal.get("tl_action"):
            card += f'<div style="background:#eff6ff;border-radius:6px;padding:6px 10px;font-size:10px;color:#1d4ed8;margin-top:6px;">TL: {_esc(synth_deal["tl_action"])}</div>'

    card += '</div>'
    return card


def generate_html(
    pae_name: str,
    meetings: list[dict],
    activity_synthesis: dict | None,
    qualified_deals: list[dict],
    pipeline_synthesis: dict | None,
    week_start: date,
    week_end: date,
) -> str:
    week_range = f"{week_start.day} {_MESES[week_start.month]} — {(week_end - timedelta(days=1)).day} {_MESES[(week_end - timedelta(days=1)).month]}"

    n_demo = sum(1 for m in meetings if m["meeting_type"] == "first_demo")
    n_fu = sum(1 for m in meetings if m["meeting_type"] == "follow_up")
    n_close = sum(1 for m in meetings if m["meeting_type"] == "closing")

    html = f'''<!DOCTYPE html>
<html><head><meta charset="UTF-8"><style>
body {{ font-family: Inter, system-ui, sans-serif; font-size: 12px; color: #1e293b; margin: 0; padding: 24px; background: #f8fafc; }}
.header {{ background: linear-gradient(135deg, #1e3a5f 0%, #2563eb 100%); color: white; padding: 24px; border-radius: 12px; margin-bottom: 20px; }}
.header h1 {{ margin: 0; font-size: 20px; font-weight: 700; }}
.header .sub {{ font-size: 12px; opacity: 0.8; margin-top: 4px; }}
.pills {{ display: flex; gap: 8px; margin-top: 12px; }}
.pill {{ font-size: 10px; font-weight: 600; padding: 3px 10px; border-radius: 99px; background: rgba(255,255,255,0.2); }}
.section-title {{ font-size: 14px; font-weight: 700; color: #1e293b; margin: 20px 0 10px; padding-bottom: 6px; border-bottom: 2px solid #e5e7eb; }}
.summary-box {{ background: #eff6ff; border-radius: 10px; padding: 14px; font-size: 12px; color: #1e40af; margin-bottom: 16px; line-height: 1.5; }}
.day-header {{ font-size: 12px; font-weight: 600; color: #6b7280; margin: 16px 0 6px; text-transform: uppercase; }}
.type-demo {{ font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 4px; background: #dbeafe; color: #1d4ed8; }}
.type-fu {{ font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 4px; background: #fef3c7; color: #92400e; }}
.type-close {{ font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 4px; background: #dcfce7; color: #166534; }}
.q-g {{ font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 4px; background: #dcfce7; color: #166534; }}
.q-a {{ font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 4px; background: #fef3c7; color: #92400e; }}
.q-r {{ font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 4px; background: #fee2e2; color: #991b1b; }}
.q-na {{ font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 4px; background: #f3f4f6; color: #9ca3af; }}
.prob-g {{ font-size: 10px; font-weight: 600; padding: 2px 6px; border-radius: 4px; background: #dcfce7; color: #166534; }}
.prob-a {{ font-size: 10px; font-weight: 600; padding: 2px 6px; border-radius: 4px; background: #fef3c7; color: #92400e; }}
.prob-r {{ font-size: 10px; font-weight: 600; padding: 2px 6px; border-radius: 4px; background: #fee2e2; color: #991b1b; }}
.coaching-box {{ background: #faf5ff; border-radius: 10px; padding: 14px; font-size: 11px; color: #6b21a8; margin-top: 12px; line-height: 1.6; }}
.divider {{ border: none; border-top: 3px solid #2563eb; margin: 30px 0; }}
.footer {{ text-align: center; font-size: 10px; color: #9ca3af; margin-top: 24px; }}
</style></head><body>
'''

    # Header
    html += f'''
    <div class="header">
      <h1>{_esc(pae_name)} — Weekly Report</h1>
      <div class="sub">{week_range}</div>
      <div class="pills">
        <span class="pill">{n_demo} Demos</span>
        <span class="pill">{n_fu} Follow-ups</span>
        <span class="pill">{n_close} Closing</span>
        <span class="pill">{len(meetings)} Total</span>
      </div>
    </div>
    '''

    # Part 1: Weekly Activity
    html += '<div class="section-title">📋 Weekly Activity</div>'

    if activity_synthesis and activity_synthesis.get("summary"):
        html += f'<div class="summary-box">{_esc(activity_synthesis["summary"])}</div>'

    # Group by day
    days: dict[str, list] = {}
    for m in meetings:
        day_str = (m.get("meeting_start") or "")[:10]
        if day_str not in days:
            days[day_str] = []
        days[day_str].append(m)

    current = week_start
    while current < week_end:
        day_name = _DAYS_ES.get(current.weekday(), "?")
        day_str = current.isoformat()
        html += f'<div class="day-header">{day_name} {current.day} {_MESES[current.month]}</div>'
        if day_str in days:
            for m in days[day_str]:
                html += _meeting_card_html(m)
        else:
            html += '<div style="font-size:11px;color:#9ca3af;font-style:italic;padding:8px;">Sin actividad registrada</div>'
        current += timedelta(days=1)

    # Coaching
    if activity_synthesis and activity_synthesis.get("coaching"):
        html += '<div class="coaching-box"><strong>Coaching</strong><br>'
        for c in activity_synthesis["coaching"]:
            html += f'<div style="margin:4px 0;">{_esc(c)}</div>'
        html += '</div>'

    # Divider
    html += '<hr class="divider">'

    # Part 2: Pipeline Review
    html += '<div class="section-title">📊 Pipeline Review</div>'

    if not qualified_deals:
        html += '<div style="font-size:11px;color:#9ca3af;font-style:italic;padding:8px;">No hay deals avanzados con prob ≥ 46%</div>'
    else:
        if pipeline_synthesis and pipeline_synthesis.get("summary"):
            html += f'<div class="summary-box">{_esc(pipeline_synthesis["summary"])}</div>'

        synth_deals = {}
        if pipeline_synthesis:
            for sd in pipeline_synthesis.get("deals", []):
                synth_deals[sd.get("deal_name", "")] = sd

        for q in qualified_deals:
            synth_deal = synth_deals.get(q["deal"].get("deal_name"), None)
            html += _pipeline_card_html(q, synth_deal)

        if pipeline_synthesis and pipeline_synthesis.get("patrones"):
            html += '<div class="coaching-box"><strong>Patrones recurrentes</strong><br>'
            for p in pipeline_synthesis["patrones"]:
                html += f'<div style="margin:4px 0;">{_esc(p)}</div>'
            html += '</div>'

    html += '<div class="footer">Generado por Claudio · deals + front_deal_snapshots + calls + pae_audits + deal_meetings + calendar_meetings</div>'
    html += '</body></html>'
    return html


def generate_pdf(
    pae_name: str,
    meetings: list[dict],
    activity_synthesis: dict | None,
    qualified_deals: list[dict],
    pipeline_synthesis: dict | None,
    week_start: date,
    week_end: date,
) -> bytes:
    html = generate_html(pae_name, meetings, activity_synthesis, qualified_deals, pipeline_synthesis, week_start, week_end)
    from weasyprint import HTML
    return HTML(string=html).write_pdf()
