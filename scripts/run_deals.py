import sys

from src.pipelines.run_deals.run import run

if __name__ == "__main__":
    full = "--full" in sys.argv
    run(full=full)
