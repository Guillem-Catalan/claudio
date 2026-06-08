"""Generate EB Status coaching paragraph for Slack alert."""

from src.integrations.claude import analyze

PAE_SCRIPT = """\
PAE ECONOMIC BUYER SCRIPT — Identifying the Economic Buyer
Scripts by sales stage, grounded in real Santander pipeline deals.

STAGE 1 — DEMO

Scenario: Opening discovery — before showing the product.
Line: "Antes de que te enseñe la plataforma, quiero entender bien cómo funciona la toma de decisiones en [empresa]. Si al final del proceso decides que Factorial encaja, ¿quién más necesita estar de acuerdo para que esto avance?"
Why it works: Forces the prospect to map the decision process before they are emotionally invested in the product.

Scenario: Champion claims final authority alone (Habber Tec / Jose Donis).
Line: "Perfecto. Y cuando llegas a dirección o finanzas con la propuesta, ¿suelen pedir algún tipo de justificación económica — tipo coste actual del proceso vs la inversión — o con tu recomendación es suficiente para que lo aprueben?"
Why it works: Tests "I decide" without confrontation. If a finance/director layer exists, they'll reveal it.

Scenario: Past rejection by unseen EBs (Serviplast / Xavier Fortuny).
Line: "Entiendo que la decisión final la tenéis que ver con el gerente y los socios. La última vez que llegamos a este punto, en febrero de 2024, el deal no salió adelante precisamente porque ellos no habían visto el producto. ¿Qué te parece si en la próxima llamada los incluimos directamente — así ellos pueden hacer sus preguntas y tú no tienes que hacer de intermediaria?"
Why it works: Uses the deal's own history as the argument — ignoring the EB feels like repeating a known mistake.

STAGE 2 — FACTORIAL PROJECT ALIGNMENT

Scenario: Champion is sold but EB unknown — arm the champion (SALMER / Joan Lorenzo).
Line: "Me alegra que veas el encaje. Ahora lo importante es que [EB] también lo vea. Antes de que hables con él, dime: ¿qué es lo que más le va a importar — el precio por empleado, el tiempo de implementación, o la reducción de riesgo de inspección? Así te preparo una hoja de una página con exactamente eso."
Why it works: Converts the follow-up into champion preparation rather than leaving outcome to chance.

Scenario: EB labeled "dirección" but no name (Inversalter / Pol Bartolomé).
Line: "Me dices que la dirección es quien decide. Para prepararles la información correcta, necesito saber con quién hablo: ¿es el CEO, el director financiero, o los socios? Y una cosa más — ¿qué es lo que más le preocupa a esa persona: el coste, la facilidad de cambio, o el retorno?"
Why it works: Direct but framed as preparation — much harder to refuse when framed as serving the champion better.

Scenario: EB attended demo but was passive (Comesacanarias / Pol Bartolomé).
Line: "[EB] estuvo en la demo y vi que tenía buenas preguntas. Me gustaría asegurarme de que tiene toda la información para tomar la decisión con confianza. ¿Puedo mandarte a ti y a [EB] directamente un resumen ejecutivo con el impacto en horas y el coste total, para que la conversación sea más ágil?"
Why it works: Re-engages a passive EB with a one-pager — bypasses the intermediary before the pricing call.

STAGE 3 — ECONOMICAL ALLIGNMENT

Scenario: Presenting price to champion without EB present — create urgency (Ciudad Jardín / Pol Bartolomé).
Line: "Antes de enviarte los números, quiero asegurarme de que cuando los veas con [EBs] no haya sorpresas. ¿Podemos hacer una llamada rápida de 20 minutos con ellos — yo, tú, y [EBs] — para que puedan hacerme las preguntas directamente? Así tú no tienes que ser el intermediario."
Why it works: Framing it as protecting the champion makes including the EB feel like a service, not a demand.

Scenario: EB rejected on price without ROI context — reopen (Gomplast / Xavier Fortuny).
Line: "Entiendo que [EB] dijo que este año no. Antes de esperarnos, me gustaría intentar algo: ¿puedo hablar con ellos 15 minutos para mostrarles el coste del proceso actual vs la inversión? Si el número tiene sentido, quizás la conversación cambia. Si no, al menos sabemos por qué."
Why it works: Reopens a no by asking for 15 minutes with actual ROI numbers — low commitment, hard to refuse.

Scenario: "Dirección" named but never met — get into the room (Leo Boeck / Xavier Fortuny).
Line: "Entiendo que esto lo tenéis que ver con dirección esta semana. Para prepararles la información adecuada — ¿es [name] quien tiene la decisión final, o hay alguien más? Y ¿qué le importa más a esa persona: el ROI, la facilidad de implementación, o la reducción de riesgo operativo?"
Why it works: Naming the EB directly forces clarification — surfaces the risk before it kills the deal a second time.
"""

_PROMPT = """\
You are a Factorial PAE coach. A deal just entered Economical Alignment. Use the \
PAE Economic Buyer Script below to coach the AE on this specific deal.

{script}

DEAL CONTEXT
- Deal: {deal_name}
- Amount: {amount}
- Days in P&P: {days_in_stage}
- Partner: (omit; not relevant to scripts)
- Classification: {classification}
- EB on file: {eb_display}
- Source note (E_accumulate): "{e_accumulate}"
- Classifier evidence: "{evidence}"
- Classifier gap: "{gap}"

OUTPUT — ONLY the *EB Status* section below. Nothing else. No coaching, \
no script, no recommendations, no extra sections. Match the language of \
the source note (Spanish if Spanish, English if English). Do not greet, \
do not preamble. Start directly with *EB Status* and stop after it.

*EB Status*
<one short paragraph — max 50 words — describing: whether the EB is identified \
(and who, if known), whether they have been in direct contact, and the single \
most important gap. INCLUDE the most telling phrase from the source note as a \
direct quote when it captures the diagnostic context — e.g. el champion dijo \
"el CEO decide", Kasia mencionó "necesito hablar con Andrés antes de cerrar". \
No bullets. STOP after this paragraph.>
"""


def generate_coaching(
    classification: str,
    deal_name: str,
    amount: str,
    days_in_stage: str,
    e_accumulate: str,
    eb_name: str | None,
    eb_role: str | None,
    evidence: str,
    gap: str,
) -> str:
    if eb_name:
        eb_display = f"{eb_name} ({eb_role})" if eb_role else eb_name
    else:
        eb_display = "Not identified"

    prompt = _PROMPT.format(
        script=PAE_SCRIPT,
        deal_name=deal_name,
        amount=amount,
        days_in_stage=days_in_stage,
        classification=classification,
        eb_display=eb_display,
        e_accumulate=e_accumulate,
        evidence=evidence,
        gap=gap,
    )

    return analyze("", prompt, max_tokens=200)
