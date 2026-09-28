#!/usr/bin/env python3
"""Development-only black-box oracle: no timing, provider calls or real projects."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from shared import repo_context as rc
from shared.jev import jev_request, JEV_MODEL, write_cache
from desktop import context as desktop


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    args = parser.parse_args()
    binary = args.binary.resolve()
    with tempfile.TemporaryDirectory(prefix='native-runtime-check-') as tmp:
        base = Path(tmp).resolve()
        repo = base / 'repo'
        repo.mkdir()
        (repo / 'main.py').write_text('from lib import value\nprint(value)\n')
        (repo / 'lib.py').write_text('value = 42\n')
        (repo / 'AGENTS.md').write_text('Preserve behavior.\n')
        for argv in [('init', '-q'), ('add', '.'), ('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', '-c', 'commit.gpgsign=false', 'commit', '-qm', 'fixture')]:
            subprocess.run(['git', '-C', str(repo), *argv], check=True, capture_output=True)
        tool_dir = base / 'tools'
        tool_dir.mkdir()
        for name in ('git', 'dirname'):
            import shutil
            (tool_dir / name).symlink_to(shutil.which(name))
        for name in ('python', 'python3', 'go'):
            trap = tool_dir / name
            trap.write_text('#!/bin/sh\nprintf forbidden-runtime >&2\nexit 97\n')
            trap.chmod(0o700)
        env = {'PATH': str(tool_dir), 'LANG': 'en_US.UTF-8'}
        task = 'Implement main.py value behavior'
        task_file = base / 'task.txt'
        task_file.write_text(task)
        plan_dir, selected, cache = base / 'native-plan', base / 'native-selected', base / 'cache'

        def run(*argv, launcher=None, ok=True):
            p = subprocess.run([str(launcher or binary), *map(str, argv)], cwd=base,
                               env=env, capture_output=True, text=True)
            assert 'forbidden-runtime' not in p.stderr, p.stderr
            assert (p.returncode == 0) == ok, (argv, p.returncode, p.stdout, p.stderr)
            return json.loads(p.stdout) if ok else p.stderr

        def fill_cache(plan):
            for batch in rc.jev_batches(plan):
                request = jev_request(rc.selection_case(plan, batch))
                response = {'model': JEV_MODEL, 'answers': {
                    key: {'type': 'noul', 'noul': .9} for key in request['questions']}}
                write_cache(request, response, cache)

        run('desktop', 'plan', '--repo', repo, '--task-file', task_file, '--out', plan_dir)
        plan = rc.load_plan(plan_dir)  # Python can validate the native artifact.
        fill_cache(plan)
        run('desktop', 'select', '--plan', plan_dir, '--out', selected,
            '--cache-dir', cache, '--mode', 'jev', '--require-jev')
        assert desktop.check(selected, require_jev=True)['status'] == 'fresh'
        read = run('desktop', 'read', '--selection', selected, '--path', 'main.py', '--require-jev')
        assert read['text'] == (repo / 'main.py').read_text()
        assert run('desktop', 'present', '--selection', selected)['provider_calls'] == 0
        record = json.loads((selected / 'selection.json').read_text())
        assert record['attempted_calls'] == 0 and all(c['reused'] for c in record['jev_calls'])
        old_plan, old_selection = base / 'python-plan', base / 'python-selected'
        p = desktop.make_plan(repo, task, old_plan)
        fill_cache(p)
        desktop.select(old_plan, old_selection, cache_dir=cache, mode='jev', require_jev=True)
        assert run('desktop', 'check', '--selection', old_selection, '--require-jev')['status'] == 'fresh'
        skills = base / 'skills'
        # Install into a disposable destination; actual user Skills are untouched.
        run('--harness-root', ROOT, 'install', '--skills-dir', skills)
        launcher = skills / 'astra-jev-coding/scripts/context.sh'
        assert run('check', '--selection', selected, launcher=launcher)['require_jev']
        rejected = base / 'rejected'
        run('select', '--plan', plan_dir, '--out', rejected, '--mode', 'local', launcher=launcher, ok=False)
        assert not rejected.exists()
        (repo / 'lib.py').write_text('value = 43\n')
        run('check', '--selection', selected, launcher=launcher, ok=False)
        print(json.dumps({'native_runtime': 'passed', 'legacy_artifact_cross_read': 'passed',
                          'installed_skill': 'passed', 'python_or_go_child_calls': 0,
                          'live_provider_calls': 0, 'timing_runs': 0}))


if __name__ == '__main__':
    main()
