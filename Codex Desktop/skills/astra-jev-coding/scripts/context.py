#!/usr/bin/env python3
"""Resolve the installed Skill symlink to the native Desktop helper."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
if __name__ == '__main__':
    args = sys.argv[1:]
    if args and args[0] in ('select', 'check', 'read'):
        # Invoking the Jev Skill must not silently become a no-Jev baseline.
        args.append('--require-jev')
    os.execve(sys.executable, [sys.executable, str(ROOT / 'Codex Desktop/context.py'), *args], os.environ.copy())
