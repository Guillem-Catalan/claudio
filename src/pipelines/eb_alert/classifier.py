"""Classify Economic Buyer status from e_accumulate text."""

import json
import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

PLACEHOLDER_RE = re.compile(
    r"^\s*(TBD|N/A|-|\?|pendiente|por identificar|need to identify|unknown)\s*$",
    re.IGNORECASE,
)

VALID_CLASSES = {"IDENTIFIED_INVOLVED", "IDENTIFIED_NOT_INVOLVED", "NOT_IDENTIFIED"}

CLASSIFIER_PROMPT = """\
You are classifying the Economic Buyer (EB) status of a sales deal based on a \
free-text note from the rep. Output exactly one of:

  IDENTIFIED_INVOLVED
  IDENTIFIED_NOT_INVOLVED
  NOT_IDENTIFIED

Definitions:

NOT_IDENTIFIED:
- The note explicitly states the EB is not identified or not yet confirmed \
("falta identificar", "no está confirmado como EB", "need to identify"). \
This wins over any names that also appear.
- No specific person is named as the approver.
- The note only references roles or groups ("the CFO", "management", "el área \
de compras", "gerencia", "dirección", "contabilidad", "los consejeros") \
without naming an individual as the EB.
- The named person is operational/intermediary, or a champion who presents to \
an unnamed decision-maker.

IDENTIFIED_NOT_INVOLVED:
- A specific person is named (first name minimum, ideally with role).
- The note describes them as having approval power (signs, approves budget, \
receives proposal as the decider).
- The rep has NOT had direct contact — info comes via a champion or third party.

IDENTIFIED_INVOLVED:
- Same name + approval power as IDENTIFIED_NOT_INVOLVED.
- The named EB has had direct contact with the rep: joined a call/demo, \
sent/received emails directly, negotiated price in person, accepted/rejected \
proposals directly, or said "lo apruebo yo" in a meeting with the rep.
- If multiple potential EBs exist but at least one named individual is directly \
involved AND has price-validation capacity, classify as IDENTIFIED_INVOLVED.

Decision procedure (apply in order, stop at first match):

Step 1: Does the note explicitly state the EB is NOT identified or NOT confirmed?
        → YES: NOT_IDENTIFIED. Stop.

Step 2: Is the only named person operational, intermediary, or a champion who \
        presents to an unnamed decision-maker (gerencia, dirección, el dueño, \
        contabilidad, etc.)?
        → YES: NOT_IDENTIFIED. Stop.

Step 3: Is there a named individual AND clear evidence they have approval power?
        → NO: NOT_IDENTIFIED. Stop.
        → YES: continue.

Step 4: Has the rep had direct contact with that named EB?
        → NO: IDENTIFIED_NOT_INVOLVED.
        → YES: IDENTIFIED_INVOLVED.

Other rules:
- Hedges do not downgrade. "Falta confirmar si X puede firmar solo" is a gap, \
not a disqualifier.
- Notes may be in Spanish or English.

Output format — exactly two lines:
Line 1: one of IDENTIFIED_INVOLVED, IDENTIFIED_NOT_INVOLVED, NOT_IDENTIFIED
Line 2: a JSON object:
{{
  "eb_name": "<the named EB, or null if NOT_IDENTIFIED>",
  "eb_role": "<role if mentioned, else null>",
  "evidence": "<one short sentence on the key signal>",
  "gap": "<what is missing — for INVOLVED, residual risk; for NOT_INVOLVED, \
what is needed for direct contact; for NOT_IDENTIFIED, what is needed to identify>"
}}

Field value:
\"\"\"
{e_accumulate}
\"\"\"\
"""


@dataclass
class ClassifierResult:
    classification: str
    eb_name: str | None
    eb_role: str | None
    evidence: str
    gap: str


def classify_eb(e_accumulate: str | None, *, model: str | None = None) -> ClassifierResult:
    if not e_accumulate or not e_accumulate.strip():
        return ClassifierResult(
            classification="NOT_IDENTIFIED",
            eb_name=None,
            eb_role=None,
            evidence="E_Accumulate is empty.",
            gap="Rep must identify the EB by name and confirm signing authority.",
        )

    if PLACEHOLDER_RE.match(e_accumulate.strip()):
        return ClassifierResult(
            classification="NOT_IDENTIFIED",
            eb_name=None,
            eb_role=None,
            evidence="E_Accumulate contains a placeholder value.",
            gap="Rep must replace the placeholder with the EB's name and confirm signing authority.",
        )

    prompt = CLASSIFIER_PROMPT.format(e_accumulate=e_accumulate)

    kwargs = {"max_tokens": 400}
    if model:
        kwargs["model"] = model

    from src.integrations.claude import analyze
    response_text = analyze("", prompt, **kwargs)

    lines = response_text.strip().split("\n", 1)
    classification = lines[0].strip()

    if classification not in VALID_CLASSES:
        raise ValueError(
            f"LLM returned unexpected classification: {classification!r}. "
            f"Full response: {response_text!r}"
        )

    parsed: dict = {}
    if len(lines) > 1:
        json_text = lines[1].strip()
        parsed = json.loads(json_text)

    return ClassifierResult(
        classification=classification,
        eb_name=parsed.get("eb_name"),
        eb_role=parsed.get("eb_role"),
        evidence=parsed.get("evidence", ""),
        gap=parsed.get("gap", ""),
    )
