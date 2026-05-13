"""
Module: next_step (CORE — always generated)
Output: PDF — email mock / call script / meeting prep based on next_step_type.
"""

import weasyprint

from src.pipelines.pae_followup.modules._html import _esc, _allow_bold, CSS_BASE


def render(section_data: dict, data: dict, brief: dict) -> dict:
    pae_name = data["pae_name"]
    contact = data.get("contact") or {}
    company = data["company"]
    step_type = section_data.get("next_step_type", "email")

    if step_type == "llamada":
        page = _render_llamada(section_data, pae_name, contact)
    elif step_type == "reunión":
        page = _render_reunion(section_data, pae_name, contact)
    else:
        page = _render_email(section_data, pae_name, contact)

    html = (
        '<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><style>'
        + CSS_BASE
        + "</style></head><body>"
        + page
        + "</body></html>"
    )

    slug = company.lower().replace(" ", "-")
    label_map = {"email": "email", "llamada": "guion-llamada", "reunión": "prep-reunion"}
    return {
        "type": "pdf",
        "pdf_bytes": weasyprint.HTML(string=html).write_pdf(),
        "filename": f"{label_map.get(step_type, 'next-step')}-{slug}.pdf",
        "intro": f":envelope: *Next step: {step_type}* — listo para usar",
    }


def _render_email(d: dict, pae_name: str, contact: dict) -> str:
    email_to = _esc(d.get("email_to") or contact.get("email") or "")
    p2_sub = f"De {_esc(pae_name)} a {_esc(contact.get('name', '?'))} · {_esc(d.get('next_step_badge', '48h post-demo'))}"
    return f'''<div class="page">
  <div class="p2-head tbl">
    <div class="tbl-cell p2h-left">
      <div class="p2h-label">Email de follow-up</div>
      <div class="p2h-title">Listo para copy-paste</div>
      <div class="p2h-sub">{p2_sub}</div>
    </div>
    <div class="tbl-cell p2h-right">
      <span class="p2h-badge">{_esc(d.get("next_step_badge", "48h post-demo"))}</span>
    </div>
  </div>
  <div class="email-wrap">
    <div class="mail-window">
      <div class="mail-bar">
        <span class="mail-dot" style="background:#FF5F57;">&nbsp;</span>
        <span class="mail-dot" style="background:#FEBC2E;">&nbsp;</span>
        <span class="mail-dot" style="background:#28C840;">&nbsp;</span>
        <span class="mail-bar-text">Nuevo mensaje</span>
      </div>
      <div class="mail-fields">
        <div class="mf"><table><tr><td class="mf-k">De</td><td class="mf-v">{_esc(pae_name)} · Factorial</td></tr></table></div>
        <div class="mf"><table><tr><td class="mf-k">Para</td><td class="mf-v">{email_to}</td></tr></table></div>
        <div class="mf"><table><tr><td class="mf-k">Asunto</td><td class="mf-v subj">{_esc(d.get("email_subject", ""))}</td></tr></table></div>
      </div>
      <div class="mail-body">{d.get("email_body", "")}</div>
    </div>
  </div>
  <div class="note-block red"><b>Objetivo.</b> {_esc(d.get("email_objetivo", ""))}</div>
  <div class="note-block blue"><b>Tono.</b> {_esc(d.get("email_tono", ""))}</div>
</div>'''


def _render_llamada(d: dict, pae_name: str, contact: dict) -> str:
    p2_sub = f"{_esc(pae_name)} a {_esc(contact.get('name', '?'))} · {_esc(d.get('next_step_badge', ''))}"

    preguntas = ""
    for i, p in enumerate(d.get("call_preguntas", []), 1):
        preguntas += (
            f'<tr><td class="p2-num">{i}.</td>'
            f'<td><div class="p2-q">{_esc(p.get("pregunta", ""))}</div>'
            f'<div class="p2-why">{_esc(p.get("por_que", ""))}</div></td></tr>'
        )

    objs = ""
    for o in d.get("call_objeciones", []):
        objs += (
            f'<div class="obj-card">'
            f'<div class="obj-q">«{_esc(o.get("objecion", ""))}»</div>'
            f'<div class="obj-a">{_allow_bold(o.get("manejo", ""))}</div></div>'
        )

    return f'''<div class="page">
  <div class="p2-head tbl">
    <div class="tbl-cell p2h-left">
      <div class="p2h-label">Guión de llamada</div>
      <div class="p2h-title">Preparación para la llamada</div>
      <div class="p2h-sub">{p2_sub}</div>
    </div>
    <div class="tbl-cell p2h-right">
      <span class="p2h-badge">{_esc(d.get("next_step_badge", ""))}</span>
    </div>
  </div>
  <div class="p2-body">
    <div class="p2-stit p2-stit-first">Objetivo</div>
    <div class="p2-block">{_allow_bold(d.get("call_objetivo", ""))}</div>
    <div class="p2-stit">Apertura</div>
    <div class="p2-block">«{_allow_bold(d.get("call_apertura", ""))}»</div>
    <div class="p2-stit">Preguntas clave</div>
    <table class="p2-numbered">{preguntas}</table>
    <div class="p2-stit">Objeciones probables</div>
    {objs}
    <div class="p2-stit">Cierre</div>
    <div class="p2-block">{_allow_bold(d.get("call_cierre", ""))}</div>
  </div>
  <div class="note-block red"><b>Objetivo.</b> {_esc(d.get("call_objetivo_nota", ""))}</div>
  <div class="note-block blue"><b>Tono.</b> {_esc(d.get("call_tono", ""))}</div>
</div>'''


def _render_reunion(d: dict, pae_name: str, contact: dict) -> str:
    p2_sub = f"{_esc(pae_name)} a {_esc(contact.get('name', '?'))} · {_esc(d.get('next_step_badge', ''))}"

    agenda = ""
    for i, a in enumerate(d.get("meeting_agenda", []), 1):
        agenda += (
            f'<tr><td class="p2-num">{i}.</td>'
            f'<td class="p2-time">[{_esc(a.get("tiempo", ""))}]</td>'
            f'<td><div class="p2-q">{_esc(a.get("punto", ""))}</div>'
            f'<div class="p2-why">{_esc(a.get("detalle", ""))}</div></td></tr>'
        )

    preguntas = ""
    for i, p in enumerate(d.get("meeting_preguntas", []), 1):
        preguntas += (
            f'<tr><td class="p2-num">{i}.</td>'
            f'<td><div class="p2-q">{_esc(p.get("pregunta", ""))}</div>'
            f'<div class="p2-why">{_esc(p.get("por_que", ""))}</div></td></tr>'
        )

    materiales = ""
    for m in d.get("meeting_materiales", []):
        materiales += f'<tr><td class="bi-dash">&mdash;</td><td>{_esc(m)}</td></tr>'
    mat_html = f'<table class="bi-table">{materiales}</table>' if materiales else ""

    return f'''<div class="page">
  <div class="p2-head tbl">
    <div class="tbl-cell p2h-left">
      <div class="p2h-label">Prep reunión</div>
      <div class="p2h-title">Preparación para la reunión</div>
      <div class="p2h-sub">{p2_sub}</div>
    </div>
    <div class="tbl-cell p2h-right">
      <span class="p2h-badge">{_esc(d.get("next_step_badge", ""))}</span>
    </div>
  </div>
  <div class="p2-body">
    <div class="p2-stit p2-stit-first">Objetivo</div>
    <div class="p2-block">{_allow_bold(d.get("meeting_objetivo", ""))}</div>
    <div class="p2-stit">Agenda</div>
    <table class="p2-numbered">{agenda}</table>
    <div class="p2-stit">Preguntas clave</div>
    <table class="p2-numbered">{preguntas}</table>
    <div class="p2-stit">Materiales</div>
    {mat_html}
  </div>
  <div class="note-block red"><b>Objetivo.</b> {_esc(d.get("meeting_objetivo_nota", ""))}</div>
  <div class="note-block blue"><b>Tono.</b> {_esc(d.get("meeting_tono", ""))}</div>
</div>'''
