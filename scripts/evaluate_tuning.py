"""Freeze using validation, then separately evaluate the immutable release."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from ml.tuned_evaluation import freeze, test_frozen

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("step",choices=["freeze","test"])
    step=p.parse_args().step
    if step=="freeze":
        record=freeze()
        print("Frozen:",record["selected"],record["name"],record["time_utc"])
    else:
        scores=test_frozen()
        for key,r in scores.items():
            print(key,round(r["mae"],4),round(r["severe"]["mean_under"],4))
