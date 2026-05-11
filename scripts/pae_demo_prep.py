"""CLI: generate and send PAE demo brief for a deal.

Usage: python -m scripts.pae_demo_prep <deal_uuid>
"""

import sys

from src.pipelines.pae_demo_prep.run import run


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.pae_demo_prep <deal_uuid>")
        sys.exit(1)

    run(deal_uuid=sys.argv[1])


if __name__ == "__main__":
    main()
