"""Compatibility import for shared.repo_context; new code belongs in its surface package."""
import sys
from shared import repo_context as _implementation

sys.modules[__name__] = _implementation
