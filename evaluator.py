"""Compatibility entrypoint for the CLI benchmark evaluator."""
import runpy
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
if __name__ == "__main__":
    runpy.run_module("cli.evaluator", run_name="__main__")
