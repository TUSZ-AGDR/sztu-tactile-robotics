"""Basic exercise: edit the parameters below, then run this script."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from lab2 import ExperimentConfig
from lab2.run import main

OBJECT_NAME = "cylinder"  # box / cylinder / sphere
TARGET_FORCE_N = 2.0  # Try 2.0, 4.0, and 6.0.
MASS_KG = 0.03
FRICTION = 1.0

if __name__ == "__main__":
    main(config=ExperimentConfig(object_name=OBJECT_NAME, target_force_N=TARGET_FORCE_N,
                                mass_kg=MASS_KG, friction=FRICTION))
