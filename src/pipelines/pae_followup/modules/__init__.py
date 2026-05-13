"""
Module registry — each module knows how to render its output (text or PDF).

Modules are split into:
  - CORE (always generated): analysis, next_step
  - CONDITIONAL (generated if classifier detects the need)
"""

from src.pipelines.pae_followup.modules.analysis import render as render_analysis
from src.pipelines.pae_followup.modules.next_step import render as render_next_step
from src.pipelines.pae_followup.modules.objections import render as render_objections
from src.pipelines.pae_followup.modules.roi_pricing import render as render_roi_pricing
from src.pipelines.pae_followup.modules.battlecard import render as render_battlecard
from src.pipelines.pae_followup.modules.champion_pack import render as render_champion_pack
from src.pipelines.pae_followup.modules.second_demo import render as render_second_demo
from src.pipelines.pae_followup.modules.poc_plan import render as render_poc_plan
from src.pipelines.pae_followup.modules.reengagement import render as render_reengagement

CORE_MODULES = ["analysis", "next_step"]

CONDITIONAL_MODULES = [
    "objections",
    "roi_pricing",
    "battlecard",
    "champion_pack",
    "second_demo",
    "poc_plan",
    "reengagement",
]

_RENDERERS = {
    "analysis": render_analysis,
    "next_step": render_next_step,
    "objections": render_objections,
    "roi_pricing": render_roi_pricing,
    "battlecard": render_battlecard,
    "champion_pack": render_champion_pack,
    "second_demo": render_second_demo,
    "poc_plan": render_poc_plan,
    "reengagement": render_reengagement,
}


def render_modules(brief: dict, data: dict, needs: list[str]) -> list[dict]:
    """
    Renders all modules (core + detected needs).

    Returns list of output blocks:
      [
        {"module": "analysis", "type": "pdf", "pdf_bytes": b"...", "filename": "...", "intro": "..."},
        {"module": "objections", "type": "text", "text": "...", "emoji": "..."},
        ...
      ]
    """
    active_modules = CORE_MODULES + [n for n in needs if n not in CORE_MODULES]

    outputs = []
    for module_name in active_modules:
        section_data = brief.get(module_name)
        if not section_data:
            continue

        renderer = _RENDERERS.get(module_name)
        if not renderer:
            continue

        output = renderer(section_data=section_data, data=data, brief=brief)
        if output:
            output["module"] = module_name
            outputs.append(output)

    return outputs
