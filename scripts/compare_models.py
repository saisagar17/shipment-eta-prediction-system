"""Reproduce the offline validation experiment without writing to serving artifacts."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from data_generation.config import ROOT
from ml.compare import run

if __name__ == "__main__":
    report, selection = run()
    path = ROOT / "reports/model_comparison.md"
    path.write_text(report, encoding="utf-8", newline="\n")
    print(f"Recommended {selection['recommended']}. Report: {path}")
