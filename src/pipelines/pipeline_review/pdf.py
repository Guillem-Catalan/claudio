"""Generate TL pipeline review PDF from deal data + Claude synthesis."""

from datetime import date

_MESES = {
    1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
    7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic",
}

STAGE_LABELS = {
    "Factorial Project Alignment started": "Product Alignment",
    "Product Alignment": "Product Alignment",
    "MEDDPICC Criteria Validation Started": "MEDDPICC Validation",
    "Economical Allignment Started": "Economical Alignment",
    "Economical Alignment Started": "Economical Alignment",
    "Pricing and Packaging": "Pricing & Packaging",
    "Pricing & Packaging": "Pricing & Packaging",
    "Contract Sent": "Contract Sent",
}

STAGE_PILL_CSS = {
    "Factorial Project Alignment started": "sp-pa",
    "Product Alignment": "sp-pa",
    "MEDDPICC Criteria Validation Started": "sp-mv",
    "Economical Allignment Started": "sp-ea",
    "Economical Alignment Started": "sp-ea",
    "Pricing and Packaging": "sp-pp",
    "Pricing & Packaging": "sp-pp",
    "Contract Sent": "sp-cs",
}

HEADER_PILL_CSS = {
    "Product Alignment": "p-pa",
    "MEDDPICC Validation": "p-mv",
    "Economical Alignment": "p-ea",
    "Pricing & Packaging": "p-pp",
    "Contract Sent": "p-cs",
}


def _esc(text) -> str:
    return (str(text) if text else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _meddic_css(score) -> str:
    if score is None:
        return "mm-m"
    s = int(score)
    if s >= 7:
        return "mm-g"
    if s >= 4:
        return "mm-a"
    return "mm-r"


def _prob_class(prob) -> str:
    if prob is None or prob < 20:
        return "prob-low"
    if prob < 40:
        return "prob-mid"
    return "prob-high"


def _prob_tag_css(prob) -> str:
    if prob is None:
        return "tag-b"
    if prob >= 50:
        return "tag-g"
    if prob >= 30:
        return "tag-a"
    return "tag-r"


def _build_header_pills(qualified: list[dict]) -> str:
    from collections import Counter
    labels = []
    for q in qualified:
        stage = q["deal"].get("deal_stage", "")
        labels.append(STAGE_LABELS.get(stage, stage))
    counts = Counter(labels)
    pills = []
    for label, count in counts.most_common():
        css = HEADER_PILL_CSS.get(label, "p-pa")
        pills.append(f'<span class="pill {css}">{_esc(label)} &times;{count}</span>')
    return "\n      ".join(pills)


def _build_deal_card(q: dict, synthesis_deal: dict, is_first: bool) -> str:
    d, s = q["deal"], q["snap"]
    prob = s.get("close_probability")
    pc = _prob_class(prob)
    mrr_cls = "dcard-mrr big" if is_first else "dcard-mrr"
    mrr_val = float(d.get("amount") or 0)
    stage = d.get("deal_stage", "")
    stage_label = STAGE_LABELS.get(stage, stage)
    stage_css = STAGE_PILL_CSS.get(stage, "sp-pa")
    prob_tag = _prob_tag_css(prob)
    prob_str = f"{prob}%" if prob is not None else "—"
    age = d.get("deal_age_days") or "?"

    meddic = ""
    for letter, key in [("M", "m_score"), ("E", "e_score"), ("DC", "dc_score"),
                        ("DP", "dp_score"), ("I", "i_score"), ("C", "c_score"),
                        ("Comp", "comp_score")]:
        score = s.get(key)
        css = _meddic_css(score)
        score_str = str(int(score)) if score is not None else "?"
        meddic += f'<span class="mm {css}">{letter} {score_str}</span>'

    context = _esc(synthesis_deal.get("context", ""))
    signals = synthesis_deal.get("signals_top3", [])
    blockers = synthesis_deal.get("blockers_top3", [])
    tl_action = _esc(synthesis_deal.get("tl_action", ""))

    signals_html = "<br>\n        ".join(f"&bull; {_esc(sig)}" for sig in signals) if signals else "&mdash;"
    blockers_html = "<br>\n        ".join(f"&bull; {_esc(b)}" for b in blockers) if blockers else "&mdash;"

    return f'''
  <div class="dcard {pc}">
    <div class="dcard-hdr">
      <div><div class="dcard-name">{_esc(d.get("deal_name", "?"))}</div></div>
      <div class="{mrr_cls}">&euro;{mrr_val:,.0f}</div>
    </div>
    <div class="dcard-meta">
      <span>{age}d</span>
      <span class="stage-pill {stage_css}">{_esc(stage_label)}</span>
      <span class="tag {prob_tag}">{prob_str}</span>
    </div>
    <div class="dcard-meddic">{meddic}</div>
    <div class="dcard-body">{context}</div>
    <div class="g2">
      <div class="g2-box signals">
        <div class="g2-title">Se&ntilde;ales de compra</div>
        {signals_html}
      </div>
      <div class="g2-box blockers">
        <div class="g2-title">Blockers activos</div>
        {blockers_html}
      </div>
    </div>
    <div class="tl-action">
      <div class="tl-label">D&oacute;nde puede entrar el TL</div>
      {tl_action}
    </div>
  </div>'''


def _build_patrones(patrones: list[str]) -> str:
    if not patrones:
        return ""
    items = "<br><br>\n    ".join(_esc(p) for p in patrones)
    return f'''
<div style="margin-top:28px">
  <div class="stit red">Patrones recurrentes &mdash; coaching para el TL</div>
  <div class="note">
    {items}
  </div>
</div>'''


def _build_html(
    pae_name: str,
    qualified: list[dict],
    synthesis: dict,
) -> str:
    today = date.today()
    fecha = f"{today.day} {_MESES[today.month]} {today.year}"

    mrr_total = sum(float(q["deal"].get("amount") or 0) for q in qualified)
    mrr_str = f"&euro;{mrr_total:,.0f}" if mrr_total else "&mdash;"

    probs = [q["snap"].get("close_probability") for q in qualified if q["snap"].get("close_probability") is not None]
    prob_range = f"{min(probs)}&ndash;{max(probs)}%" if probs else "&mdash;"

    header_pills = _build_header_pills(qualified)

    synthesis_deals = {sd["deal_name"]: sd for sd in synthesis.get("deals", [])}

    deal_cards = []
    for i, q in enumerate(qualified):
        deal_name = q["deal"].get("deal_name", "")
        sd = synthesis_deals.get(deal_name, {})
        deal_cards.append(_build_deal_card(q, sd, is_first=(i == 0)))

    patrones_html = _build_patrones(synthesis.get("patrones", []))

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
.mrr-box{{text-align:right;flex-shrink:0}}
.mrr-box .lbl{{font-size:9px;text-transform:uppercase;letter-spacing:1.2px;color:var(--ink3);font-weight:600}}
.mrr-box .val{{font-family:var(--fd);font-size:30px;font-weight:700;letter-spacing:-1px;line-height:1.1;margin-top:2px}}
.mrr-box .det{{font-size:10px;color:var(--ink3);margin-top:2px}}
.pills{{display:flex;flex-wrap:wrap;gap:5px;margin-top:10px}}
.pill{{font-size:10px;font-weight:500;padding:2px 10px;border-radius:20px;white-space:nowrap}}
.p-pa{{background:var(--blu-bg);color:var(--blu-tx)}}.p-pp{{background:var(--grn-bg);color:var(--grn-tx)}}.p-mv{{background:#f3e8ff;color:#6b21a8}}.p-ea{{background:var(--amb-bg);color:var(--amb-tx)}}.p-cs{{background:var(--red-bg);color:var(--red-tx)}}
.stit{{font-size:9px;font-weight:600;text-transform:uppercase;letter-spacing:1.5px;color:var(--ink3);margin-bottom:8px;padding-bottom:5px;border-bottom:1px solid var(--bdr-l);margin-top:24px}}
.stit.red{{color:var(--red);border-color:var(--red)}}
.summary{{margin-top:24px;padding:16px 20px;border-radius:8px;background:var(--bg);font-size:11.5px;line-height:1.65;color:var(--ink2)}}
.summary b{{color:var(--ink);font-weight:600}}
.dcards{{display:flex;flex-direction:column;gap:18px;margin-top:16px}}
.dcard{{border:1px solid var(--bdr);border-radius:8px;padding:18px 22px;position:relative}}
.dcard.prob-high{{border-left:4px solid var(--grn)}}
.dcard.prob-mid{{border-left:4px solid var(--amb)}}
.dcard.prob-low{{border-left:4px solid var(--red)}}
.dcard-hdr{{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:6px}}
.dcard-name{{font-weight:700;font-size:14px}}
.dcard-mrr{{font-family:var(--fd);font-weight:700;font-size:16px}}
.dcard-mrr.big{{font-size:20px;color:var(--red)}}
.dcard-meta{{display:flex;flex-wrap:wrap;gap:8px;font-size:10px;color:var(--ink3);margin-bottom:8px;align-items:center}}
.dcard-meta span{{display:flex;align-items:center;gap:3px}}
.tag{{font-size:9px;font-weight:500;padding:2px 8px;border-radius:10px;display:inline-block}}
.tag-r{{background:var(--red-bg);color:var(--red-tx)}}.tag-a{{background:var(--amb-bg);color:var(--amb-tx)}}.tag-g{{background:var(--grn-bg);color:var(--grn-tx)}}.tag-b{{background:var(--blu-bg);color:var(--blu-tx)}}
.stage-pill{{font-size:9px;font-weight:500;padding:2px 8px;border-radius:10px;display:inline-block}}
.sp-pa{{background:var(--blu-bg);color:var(--blu-tx)}}.sp-pp{{background:var(--grn-bg);color:var(--grn-tx)}}.sp-ea{{background:var(--amb-bg);color:var(--amb-tx)}}.sp-mv{{background:#f3e8ff;color:#6b21a8}}.sp-cs{{background:var(--red-bg);color:var(--red-tx)}}
.dcard-meddic{{display:flex;gap:4px;margin:6px 0 10px}}
.mm{{font-size:9px;font-weight:600;padding:2px 7px;border-radius:8px}}
.mm-g{{background:#d4edda;color:#12593a}}.mm-a{{background:#fef6e8;color:#7a4900}}.mm-r{{background:#fce8e8;color:#9a0c22}}.mm-m{{background:#f3f2ed;color:#5c5b57}}
.dcard-body{{font-size:11px;line-height:1.6;color:var(--ink2)}}
.dcard-body b{{color:var(--ink);font-weight:600}}
.g2{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:10px}}
.g2-box{{font-size:10.5px;line-height:1.55;padding:8px 12px;border-radius:6px}}
.g2-box.signals{{background:var(--grn-bg);color:var(--grn-tx)}}
.g2-box.blockers{{background:var(--red-bg);color:var(--red-tx)}}
.g2-box .g2-title{{font-size:8.5px;font-weight:600;text-transform:uppercase;letter-spacing:.8px;margin-bottom:4px}}
.tl-action{{background:var(--blu-bg);border-radius:6px;padding:10px 14px;margin-top:12px;font-size:10.5px;line-height:1.55;color:var(--blu-tx)}}
.tl-action b{{color:var(--ink);font-weight:600}}
.tl-label{{font-size:8.5px;font-weight:600;text-transform:uppercase;letter-spacing:1px;color:var(--blu);margin-bottom:3px}}
.note{{margin-top:16px;padding:12px 16px;border-radius:6px;background:var(--bg);font-size:11px;line-height:1.6;color:var(--ink2)}}
.note b{{color:var(--ink);font-weight:600}}
.foot{{font-size:9.5px;color:var(--ink3);margin-top:24px;padding-top:10px;border-top:.5px solid var(--bdr);text-align:center}}
</style>
</head>
<body>
<div class="page">

<div class="hdr">
  <div>
    <h1>{_esc(pae_name)} &mdash; <em>pipeline review</em></h1>
    <div class="sub">Deals avanzados con prob &ge;46% &middot; Para Team Lead &middot; {fecha}</div>
    <div class="pills">
      {header_pills}
    </div>
  </div>
  <div class="mrr-box">
    <div class="lbl">MRR deals en scope</div>
    <div class="val">{mrr_str}</div>
    <div class="det">{len(qualified)} deals &middot; {prob_range} close probability</div>
  </div>
</div>

<div class="summary">
  <b>Resumen para el TL:</b> {_esc(synthesis.get("summary", ""))}
</div>

<div class="dcards">
{"".join(deal_cards)}
</div>

{patrones_html}

<div class="foot">Generado por Claudio &middot; Datos: deals + front_deal_snapshots (MEDDIC + close_probability) &middot; {fecha}</div>

</div>
</body>
</html>'''

def generate_pdf(
    pae_name: str,
    qualified: list[dict],
    synthesis: dict,
) -> bytes:
    import weasyprint
    html = _build_html(pae_name, qualified, synthesis)
    return weasyprint.HTML(string=html).write_pdf()


def generate_html(
    pae_name: str,
    qualified: list[dict],
    synthesis: dict,
) -> str:
    return _build_html(pae_name, qualified, synthesis)
