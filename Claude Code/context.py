#!/usr/bin/env python3
"""Read-only Jev context handoff for the active Claude Code conversation."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from shared import host_context as hc
from shared import repo_context as rc
from shared.credentials import execution_environment
from shared.jev import ProtocolError

SURFACE = 'claude-code'
LABEL = 'Claude Code'
NO_JEV_ROUTE = 'local'


def _host():
    # Resolve through this module so patches of its functions stay effective.
    return sys.modules[__name__]


def fresh(plan):
    rc.check_plan_fresh(plan)


def load_host_plan(path):
    return hc.load_surface_plan(path, _host())


def make_plan(repo, task, out, include_paths=None, focus_paths=None, scope_max_calls=4):
    return hc.make_plan(_host(), repo, task, out, include_paths, focus_paths, scope_max_calls)


def select(plan_dir, out, max_calls=4, policy='batch', cache_dir=None, evidence_dir=None, mode='jev'):
    return hc.select(_host(), plan_dir, out, max_calls, policy, cache_dir, evidence_dir, mode)


def check(selection_dir):
    return hc.check(_host(), selection_dir)


def read_context(selection_dir, path, start_line=1, end_line=None):
    """Expose only a requested range after checking provenance and source freshness."""
    return hc.read_context(_host(), selection_dir, path, start_line, end_line)


def compare(selection_dir, required_paths=None):
    """Compare policies against identical saved evidence, without network or writes."""
    return hc.compare(_host(), selection_dir, required_paths)


def main():
    return hc.main(_host(), __doc__)


if __name__ == '__main__':
    raise SystemExit(main())
