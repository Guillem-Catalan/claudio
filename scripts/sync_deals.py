import sys

from src.pipelines.sync_deals.sync import run

if __name__ == "__main__":
    full = "--full" in sys.argv
    run(full=full)
