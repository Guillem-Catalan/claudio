import sys

from src.pipelines.audit.run import run_single

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.audit <call_id>")
        sys.exit(1)

    result = run_single(sys.argv[1])
    if result:
        print(f"Audit complete: win_rate_score={result.get('win_rate_score')}")
    else:
        print("Audit returned no result")
        sys.exit(1)
