import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import repo_context as rc


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.repo)], check=True)
        for k, v in [('user.name', 'Harness Test'), ('user.email', 'harness@example.invalid')]:
            rc.git(self.repo, 'config', k, v)
        (self.repo / 'code.py').write_text('value = 1\n')
        (self.repo / '.env').write_text('API_KEY=not-a-real-key\n')
        rc.git(self.repo, 'add', '.')
        rc.git(self.repo, 'commit', '-qm', 'fixture')
        self.plan_dir = self.root / 'plan'

    def plan(self):
        return rc.snapshot(self.repo, 'valueを2に変更してください', self.plan_dir)

    def test_snapshot_preserves_dirty_contents_and_excludes_environment(self):
        (self.repo / 'code.py').write_text('value = 3\n')
        plan = self.plan()
        self.assertEqual(plan['files']['code.py']['content'], 'value = 3\n')
        self.assertNotIn('.env', plan['files'])
        self.assertIn('.env', plan['excluded'])

    def test_small_auto_route_never_calls_jev(self):
        plan = self.plan()
        with patch.object(rc, 'call_jev', side_effect=AssertionError('must not call')):
            self.assertEqual(rc.select(plan)['route'], 'astra')

    def test_path_traversal_and_symlinks_refused(self):
        (self.repo / 'link.py').symlink_to(self.repo / 'code.py')
        for rel in ['../escape', '/tmp/escape', 'link.py', 'a\\b']:
            with self.assertRaises(rc.ProtocolError):
                rc.safe_path(self.repo, rel)

    def test_dependency_closure_keeps_local_imports_and_guidance(self):
        files = {'src/a.py': 'from .b import value', 'src/b.py': 'value=1', 'AGENTS.md': 'rules', 'other.py': 'pass'}
        self.assertEqual(rc.dependencies(files, ['src/a.py']), ['AGENTS.md', 'src/a.py', 'src/b.py'])

    def test_empty_irrelevant_batches_do_not_force_all_files_into_context(self):
        plan = {'task': 'fix chosen.py', 'files': {'chosen.py': {'content': 'value=1'}, **{
            f'noise{i}.py': {'content': '# noise\n' * 200} for i in range(40)}}}
        def fake(case):
            probs = {p: .95 if p == 'chosen.py' else .03 for p in case['files']}
            paths = [p for p, v in probs.items() if v >= .8]
            return {'paths': paths or list(case['files']), 'probabilities': probs}
        with patch.object(rc, 'call_jev', side_effect=fake):
            self.assertEqual(rc.select(plan, 'jev')['paths'], ['chosen.py'])

    def test_apply_rolls_back_completed_writes_on_filesystem_error(self):
        import coding
        (self.repo / 'second.py').write_text('value = 1\n')
        rc.git(self.repo, 'add', '.')
        rc.git(self.repo, 'commit', '-qm', 'second fixture')
        plan = self.plan()
        run = self.root / 'run'
        run.mkdir()
        edits = {'code.py': 'value = 2\n', 'second.py': 'value = 2\n'}
        coding.materialize(plan, run / 'candidate', edits)
        result = {'status': 'verified', 'verification_exit_code': 0, 'plan': str(self.plan_dir),
                  'plan_sha256': rc.digest((self.plan_dir / 'plan.json').read_bytes()),
                  'candidate_hashes': coding.candidate_hashes(run / 'candidate', plan['files']),
                  'edits': {p: rc.digest(s.encode()) for p, s in edits.items()}}
        (run / 'result.json').write_text(json.dumps(result))
        replace = os.replace
        def fail_second(src, dst):
            if Path(dst).name == 'second.py':
                raise OSError('simulated disk error')
            return replace(src, dst)
        with patch.object(coding.os, 'replace', side_effect=fail_second):
            with self.assertRaises(rc.ProtocolError):
                coding.apply(run)
        self.assertEqual((self.repo / 'code.py').read_text(), 'value = 1\n')
        self.assertEqual((self.repo / 'second.py').read_text(), 'value = 1\n')

    def test_verification_rejects_shell_string(self):
        import coding
        with self.assertRaises(rc.ProtocolError):
            coding.verify(self.repo, 'python3 -m unittest; unwanted-command', 3)

    def test_apply_rejects_changed_source_and_leaves_existing_work(self):
        import coding
        plan = self.plan()
        run = self.root / 'run'
        run.mkdir()
        coding.materialize(plan, run / 'candidate', {'code.py': 'value = 2\n'})
        result = {'status': 'verified', 'verification_exit_code': 0, 'plan': str(self.plan_dir),
                  'candidate_hashes': coding.candidate_hashes(run / 'candidate', plan['files']),
                  'plan_sha256': rc.digest((self.plan_dir / 'plan.json').read_bytes()),
                  'edits': {'code.py': rc.digest(b'value = 2\n')}}
        (run / 'result.json').write_text(json.dumps(result))
        (self.repo / 'code.py').write_text('value = 99\n')
        with self.assertRaises(rc.ProtocolError):
            coding.apply(run)
        self.assertEqual((self.repo / 'code.py').read_text(), 'value = 99\n')

    def test_only_verified_unchanged_candidate_can_apply(self):
        import coding
        plan = self.plan()
        run = self.root / 'run'
        run.mkdir()
        coding.materialize(plan, run / 'candidate', {'code.py': 'value = 2\n'})
        result = {'status': 'verification_failed', 'verification_exit_code': 0, 'plan': str(self.plan_dir),
                  'candidate_hashes': coding.candidate_hashes(run / 'candidate', plan['files']),
                  'plan_sha256': rc.digest((self.plan_dir / 'plan.json').read_bytes()),
                  'edits': {'code.py': rc.digest(b'value = 2\n')}}
        (run / 'result.json').write_text(json.dumps(result))
        with self.assertRaises(rc.ProtocolError):
            coding.apply(run)
        result['status'] = 'verified'
        (run / 'result.json').write_text(json.dumps(result))
        (run / 'candidate' / 'code.py').write_text('value = 9\n')
        with self.assertRaises(rc.ProtocolError):
            coding.apply(run)
        (run / 'candidate' / 'code.py').write_text('value = 2\n')
        coding.apply(run)
        self.assertEqual((self.repo / 'code.py').read_text(), 'value = 2\n')
        self.assertEqual(json.loads((run / 'result.json').read_text())['status'], 'applied')


if __name__ == '__main__':
    unittest.main()
