#!/usr/bin/env python3
"""Link the Desktop Skill to this clone; never copy credentials or overwrite another skill."""
import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent


def install(skills_dir, check=False):
    source = ROOT / 'desktop/skills/astra-jev-coding'
    if not (source / 'SKILL.md').is_file():
        raise ValueError('Keep the complete repository clone; Skill source is missing')
    target = Path(skills_dir).expanduser() / 'astra-jev-coding'
    if target.is_symlink() and target.resolve() == source:
        return 'already-installed', target
    if target.exists() or target.is_symlink():
        raise ValueError('A different skill already exists at the destination; leave it intact and choose another --skills-dir')
    if not check:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(source, target_is_directory=True)
    return 'would-install' if check else 'installed', target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Show the action without writing anything')
    parser.add_argument('--skills-dir', type=Path,
                        default=Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))) / 'skills')
    args = parser.parse_args()
    try:
        status, target = install(args.skills_dir, args.check)
        print(f'{status}: {target}')
        return 0
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
