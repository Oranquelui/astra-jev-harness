#!/usr/bin/env python3
"""Link a Skill to this clone; never copy credentials or overwrite another skill."""
import argparse
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
# target -> (Skill source relative to this clone, installed name, legacy source or None)
TARGETS = {
    'codex-desktop': ('Codex Desktop/skills/astra-jev-coding', 'astra-jev-coding', 'desktop/skills/astra-jev-coding'),
    'claude-code': ('Claude Code/skills/claude-jev-coding', 'claude-jev-coding', None),
}


def default_skills_dir(target='codex-desktop'):
    if target == 'claude-code':
        return Path.home() / '.claude' / 'skills'
    return Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))) / 'skills'


def install(skills_dir, check=False, target='codex-desktop'):
    if target not in TARGETS:
        raise ValueError('Unknown install target')
    relative, name, legacy_relative = TARGETS[target]
    source = ROOT / relative
    if not (source / 'SKILL.md').is_file():
        raise ValueError('Keep the complete repository clone; Skill source is missing')
    link = Path(skills_dir).expanduser() / name
    if link.is_symlink() and link.resolve() == source:
        return 'already-installed', link
    legacy = ROOT / legacy_relative if legacy_relative else None
    if legacy and link.is_symlink() and link.resolve() == legacy and not legacy.exists():
        if not check:
            # Replace only this clone's old link, atomically. Failures keep it.
            with tempfile.TemporaryDirectory(prefix='.astra-jev-install-', dir=link.parent) as tmp:
                replacement = Path(tmp) / link.name
                replacement.symlink_to(source, target_is_directory=True)
                replacement.replace(link)
        return 'would-update' if check else 'updated', link
    if link.exists() or link.is_symlink():
        raise ValueError('A different skill already exists at the destination; leave it intact and choose another --skills-dir')
    if not check:
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(source, target_is_directory=True)
    return 'would-install' if check else 'installed', link


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Show the action without writing anything')
    parser.add_argument('--target', choices=tuple(TARGETS), default='codex-desktop',
                        help='codex-desktop (default): $CODEX_HOME/skills; claude-code: ~/.claude/skills')
    parser.add_argument('--skills-dir', type=Path,
                        help='Skills directory, e.g. <project>/.claude/skills for a project-scoped Claude Code Skill')
    args = parser.parse_args()
    try:
        status, target = install(args.skills_dir or default_skills_dir(args.target), args.check, args.target)
        print(f'{status}: {target}')
        return 0
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
