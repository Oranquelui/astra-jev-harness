"""Preserve desktop.* imports after moving the implementation to Codex Desktop/."""
from pathlib import Path

__path__ = [str(Path(__file__).resolve().parent / 'Codex Desktop')]
if __spec__ is not None:
    __spec__.submodule_search_locations = __path__
