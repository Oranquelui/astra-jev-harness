#!/usr/bin/env python3
"""Resolve the installed Skill symlink to the Claude Code helper."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
if __name__ == '__main__':
    os.execve(sys.executable, [sys.executable, str(ROOT / 'Claude Code/context.py'), *sys.argv[1:]], os.environ.copy())
