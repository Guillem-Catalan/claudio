"""Entrypoint: compute forecast for a single front_deal snapshot."""

import sys

from src.pipelines.front_forecast.run import run

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.front_forecast <snapshot_id>")
        sys.exit(1)
    run(sys.argv[1])
