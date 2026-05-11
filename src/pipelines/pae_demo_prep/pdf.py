"""
Generate a PDF demo brief from Claude's structured output.
Uses weasyprint to convert an HTML template to PDF.
"""

from pathlib import Path

import weasyprint

_TEMPLATE = """\
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<style>
  @page {{ size: A4; margin: 2cm; }}
  body {{ font-family: 'Helvetica Neue', Arial, sans-serif; font-size: 11pt; color: #1a1a1a; line-height: 1.5; }}
  h1 {{ font-size: 18pt; color: #0f3057; border-bottom: 3px solid #0f3057; padding-bottom: 6px; margin-bottom: 16px; }}
  h2 {{ font-size: 13pt; color: #0f3057; margin-top: 20px; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px; }}
  .meta {{ background: #f4f6f8; padding: 12px 16px; border-radius: 6px; margin-bottom: 20px; font-size: 10pt; }}
  .meta strong {{ color: #0f3057; }}
  .section {{ margin-bottom: 16px; white-space: pre-wrap; }}
  .label {{ font-weight: bold; color: #555; font-size: 9pt; text-transform: uppercase; letter-spacing: 0.3px; }}
  hr {{ border: none; border-top: 1px solid #ddd; margin: 16px 0; }}
</style>
</head>
<body>

<h1>Demo Brief — {company}</h1>

<div class="meta">
  <strong>Demo:</strong> {demo_date} · {demo_time}<br>
  <strong>Contacto:</strong> {contact_name} · {contact_title} · {contact_email}<br>
  <strong>Deal:</strong> {amount} | Partner: {partner}
</div>

<h2>1. Quién es el cliente</h2>
<div class="section">{company_overview}</div>

<h2>2. Historial de deals</h2>
<div class="section">{deal_history}</div>

<h2>3. Pain points identificados</h2>
<div class="section">{pain_points}</div>

<h2>4. Estado BANT</h2>
<div class="section">{bant_status}</div>

<h2>5. Objeciones</h2>
<div class="section">{objections}</div>

<h2>6. Señales de compra</h2>
<div class="section">{buying_signals}</div>

<h2>7. Contactos clave</h2>
<div class="section">{contacts_key}</div>

<h2>8. Estrategia de demo</h2>
<div class="section">{demo_strategy}</div>

</body>
</html>"""


def _escape(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def generate_pdf(
    brief: dict,
    company: str,
    demo_date: str,
    demo_time: str,
    amount_str: str,
    partner: str,
    contact: dict,
) -> bytes:
    html = _TEMPLATE.format(
        company=_escape(company),
        demo_date=_escape(demo_date),
        demo_time=_escape(demo_time),
        contact_name=_escape(contact.get("name", "")),
        contact_title=_escape(contact.get("jobtitle", "")),
        contact_email=_escape(contact.get("email", "")),
        amount=_escape(amount_str),
        partner=_escape(partner),
        company_overview=_escape(brief.get("company_overview", "")),
        deal_history=_escape(brief.get("deal_history", "")),
        pain_points=_escape(brief.get("pain_points", "")),
        bant_status=_escape(brief.get("bant_status", "")),
        objections=_escape(brief.get("objections", "")),
        buying_signals=_escape(brief.get("buying_signals", "")),
        contacts_key=_escape(brief.get("contacts_key", "")),
        demo_strategy=_escape(brief.get("demo_strategy", "")),
    )

    return weasyprint.HTML(string=html).write_pdf()
