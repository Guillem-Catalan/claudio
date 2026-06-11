"""Generate learned patterns from deal trajectories. Run weekly."""

from src.pipelines.intelligence.patterns import generate_patterns

if __name__ == "__main__":
    generate_patterns()
