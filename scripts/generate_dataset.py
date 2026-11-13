"""Generate and audit all phase-one files."""
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"src"))
from data_generation.config import ROOT, Config
from data_generation.pipeline import export

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-root", type=Path, default=ROOT)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    tables = export(Config(seed=args.seed), args.output_root)
    for name, frame in tables.items():
        logging.info("%s: %d rows", name, len(frame))
    logging.info("Validated persisted files in %s", args.output_root)
