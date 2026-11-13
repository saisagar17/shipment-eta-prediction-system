"""Run the three independent training-only Optuna studies."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from ml.tuning import OUT, TUNED, optimize
from ml.tuned_evaluation import verify_freeze

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study",choices=list(TUNED))
    args=parser.parse_args()
    if (OUT / "freeze.json").exists():
        verify_freeze()
        print("Verified frozen run. Use a separate project copy with an empty models/tuning directory for a fresh study.")
    else:
        for key in [args.study] if args.study else TUNED:
            optimize(key)
