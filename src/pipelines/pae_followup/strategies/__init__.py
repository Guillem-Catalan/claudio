"""
Strategy router — delegates to the correct strategy module based on classification.
"""

from src.pipelines.pae_followup.strategies.active import run as run_active
from src.pipelines.pae_followup.strategies.stalled import run as run_stalled
from src.pipelines.pae_followup.strategies.closed import run as run_closed

_RUNNERS = {
    "active": run_active,
    "stalled": run_stalled,
    "closed": run_closed,
}


def run_strategy(strategy: str, subtype: str, data: dict) -> tuple[bytes, dict]:
    """
    Returns (pdf_bytes, brief_dict).
    """
    runner = _RUNNERS.get(strategy)
    if not runner:
        raise ValueError(f"Unknown strategy: {strategy}")
    return runner(subtype=subtype, data=data)
