from pathlib import Path

from src.config import (
    HANDOVER_TRIGGER_TAG,
    TAG_AUDIT_LEVEL,
    ALL_KNOWN_TAGS,
    get_subteam,
)
from src.db.client import supabase

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"

_LEVEL_PRIORITY = {"full_pae": 1, "full_pbd": 2, "light": 3, "light_pae": 3}

LANG_FILE = {
    "Santander":  "lang_es_startup.txt",
    "Telefónica": "lang_es_startup.txt",
    "TIM":        "lang_en.txt",
    "TELEKOM":    "lang_en.txt",
}

PARTNER_NAME = {
    "Santander":  "Banco Santander / Telefónica / MEO",
    "Telefónica": "Banco Santander / Telefónica / MEO",
    "TIM":        "TIM",
    "TELEKOM":    "TELEKOM",
}

TAG_TO_FILE = {
    "91. Partners - PBD Demo Scheduled":                                            "pbd/91.txt",
    "Partners - PBD Demo Scheduled Call":                                            "pbd/91.txt",
    "92. Partners - PBD Positive Champion Connected Call":                           "pbd/92.txt",
    "93. Partners - PBD Gatekeeper Call Connected":                                  "pbd/93.txt",
    "94. Partners - PBD Connected Call - Objection":                                 "pbd/94.txt",
    "95. Partners - PBD Connected Call - Busy/Bad Time":                             "pbd/95.txt",
    "96. Partners - PBD Non Connected - Left Voicemail":                             "pbd/96.txt",
    "97. Partners - PBD Non Connected - No Answer/Busy":                             "pbd/97.txt",
    "98. Partners - PBD Connected Call - Wrong Number":                              "pbd/98.txt",
    "99. Partners - PBD Connected Call - Wrong Champion/Person inside the Company":  "pbd/99.txt",
    "991. Partners - PBD Partner Call":                                              "pbd/991.txt",
    "Partners - PAE Demo":                                                           "pae/demo.txt",
    "Partners - PAE Follow Up":                                                      "pae/follow_up.txt",
    "Partners - PAE Follow Up Meeting":                                              "pae/follow_up.txt",
    "Partners - PAE Closing Call":                                                   "pae/closing.txt",
    "Partners - PAE Closing Meeting":                                                "pae/closing.txt",
}


def _resolve_company_name(crm_id: str | None) -> str:
    if not crm_id:
        return "Unknown"
    try:
        result = (
            supabase.table("atlas")
            .select("company_name")
            .eq("crm_id", crm_id)
            .maybe_single()
            .execute()
        )
        return result.data["company_name"] if result.data else "Unknown"
    except Exception:
        return "Unknown"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def _pick_primary_tag(tags: list[str]) -> str | None:
    known = [t for t in tags if t in ALL_KNOWN_TAGS]
    if not known:
        return None
    if HANDOVER_TRIGGER_TAG in known:
        return HANDOVER_TRIGGER_TAG
    return min(known, key=lambda t: _LEVEL_PRIORITY.get(TAG_AUDIT_LEVEL.get(t, "light"), 3))


def build(call: dict, deal_context: str) -> tuple[str, str]:
    role = call.get("rol") or "PBD"
    tags = call.get("tags") or []
    primary_tag = _pick_primary_tag(tags)

    base = _read(PROMPTS_DIR / "base.txt")
    role_prompt = _read(PROMPTS_DIR / "roles" / ("pae.txt" if role == "PAE" else "pbd.txt"))

    if primary_tag:
        tag_file = TAG_TO_FILE.get(primary_tag)
        tag_path = PROMPTS_DIR / "tags" / tag_file if tag_file else None
        tag_prompt = _read(tag_path) if tag_path and tag_path.exists() else ""
    else:
        tag_prompt = _read(PROMPTS_DIR / "tags" / "untagged.txt")

    parts = [base, role_prompt]
    if deal_context and "Treat this as a first contact" not in deal_context:
        parts.append(deal_context)
    if tag_prompt:
        parts.append(tag_prompt)

    system_prompt = "\n\n".join(parts)

    subteam = get_subteam(call.get("owner_email", ""))
    partner = PARTNER_NAME.get(subteam, "")
    if partner and partner != "Banco Santander / Telefónica / MEO":
        system_prompt = system_prompt.replace("Banco Santander, Telefónica, and MEO", partner)
        system_prompt = system_prompt.replace("Santander, Telefónica, or MEO", partner)

    lang_file = LANG_FILE.get(subteam, "lang_en.txt")
    lang_path = PROMPTS_DIR / lang_file
    if lang_path.exists():
        system_prompt += "\n\n" + _read(lang_path)

    tags_str = ", ".join(tags) if tags else "untagged"
    user_prompt = f"""Audit this call transcript.

## Call metadata
- Call ID: {call.get('call_id', '?')}
- Rep: {call.get('owner_nombre', '?')} ({call.get('owner_email', '?')})
- Role: {role}
- Date: {(call.get('fecha') or '?')[:10]}
- Duration: {call.get('duracion_segundos', 0)} seconds ({round((call.get('duracion_segundos') or 0) / 60, 1)} min)
- Company: {_resolve_company_name(call.get('crm_id'))}
- Tags: [{tags_str}]
- Primary tag for evaluation: {primary_tag or 'none (untagged)'}

## Transcript
{call.get('transcript', '')}"""

    return system_prompt, user_prompt
