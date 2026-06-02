"""
Weekly TL pipeline review report.

Usage:
  python -m scripts.pipeline_review                                      # all PAEs, Santander + Telefónica
  python -m scripts.pipeline_review --pae-email david.clemente@factorial.co
  python -m scripts.pipeline_review --channel C0ATY3V8CN4                # override Slack channel (testing)
"""

import argparse

from src.pipelines.pipeline_review.run import run_all


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pae-email", help="Single PAE email (default: all Santander/Telefónica)")
    parser.add_argument("--channel", help="Override Slack channel ID (for testing)")
    args = parser.parse_args()

    run_all(pae_email=args.pae_email, channel_override=args.channel)


if __name__ == "__main__":
    main()
