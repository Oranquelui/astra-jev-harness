"""Preserve cli.* imports after moving the implementation to Codex cli/."""
from pathlib import Path

__path__ = [str(Path(__file__).resolve().parent / 'Codex cli')]
if __spec__ is not None:
    __spec__.submodule_search_locations = __path__
