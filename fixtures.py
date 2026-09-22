"""Compatibility import for cli.fixtures; new code belongs in its surface package."""
import sys
from cli import fixtures as _implementation

sys.modules[__name__] = _implementation
