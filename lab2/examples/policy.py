"""Policy exercise: edit lab2/student_policy.py, then run this script."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from lab2.run import main

if __name__ == "__main__":
    main(["--controller", "student", *sys.argv[1:]])
