"""Compatibility import for cli.benchmark; new code belongs in its surface package."""
import sys
from cli import benchmark as _implementation

if __name__ == "__main__":
    raise SystemExit(_implementation.main())

sys.modules[__name__] = _implementation
