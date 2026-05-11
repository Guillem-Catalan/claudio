import sys

from src.pipelines.atlas.run import generate

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python -m scripts.atlas <atlas_id> <crm_id>")
        sys.exit(1)

    generate(atlas_id=sys.argv[1], crm_id=sys.argv[2])
