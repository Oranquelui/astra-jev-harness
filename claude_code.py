"""Expose claude_code.* imports for the implementation in Claude Code/."""
from pathlib import Path

__path__ = [str(Path(__file__).resolve().parent / 'Claude Code')]
if __spec__ is not None:
    __spec__.submodule_search_locations = __path__
