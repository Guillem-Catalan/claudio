"""Monthly forecast calibration. Compare predictions vs reality."""

import argparse
from src.pipelines.intelligence.calibration import calibrate_month

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--month", help="Target month YYYY-MM (default: previous month)")
    args = parser.parse_args()
    calibrate_month(target_month=args.month)
