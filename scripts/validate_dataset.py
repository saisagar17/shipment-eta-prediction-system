"""Validate the serialized dataset without regenerating it."""
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"src"))
from data_generation.config import ROOT
from data_generation.pipeline import audit_disk

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    _, _, checks = audit_disk(args.output_root)
    for name in checks:
        logging.info("PASS  %s", name)
