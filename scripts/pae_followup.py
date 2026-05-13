"""Entrypoint: generate follow-up brief for a PAE Demo call."""

import sys

from src.pipelines.pae_followup.run import run

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.pae_followup <call_ref>")
        sys.exit(1)
    run(sys.argv[1])
