"""Private exercise checks, executed in a separate bounded process."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cli.fixtures import CASES
from cli.benchmark import evaluate_worker

if __name__ == "__main__":
    request = json.load(sys.stdin)
    case = next(c for c in CASES if c["id"] == request["case"])
    print(json.dumps(evaluate_worker(case, request["replacements"])))
