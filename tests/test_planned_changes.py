"""Offline contracts for explicitly planned additions and test edits."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import coding
import repo_context as rc
from tests import test_coding


class PlannedChangesTests(unittest.TestCase):
    def setUp(self):
        test_coding.RepositoryTests.setUp(self)
        config = patch.object(coding, 'read_model_settings', return_value={
            'model': 'fixture-model', 'reasoning': 'high'})
        config.start()
        self.addCleanup(config.stop)

    def make_plan(self, create=(), test_edits=()):
        return rc.snapshot(self.repo, 'Add a helper and its tests', self.plan_dir,
                           create_paths=list(create), test_edit_paths=list(test_edits))

    def run_candidate(self, edits, command=None):
        run_dir = self.root / 'run'
        answer = {'summary': 'Add helper', 'needs_context': [], 'files': []}
        def local_verify(candidate, argv, timeout):
            process = subprocess.run(argv, cwd=candidate, capture_output=True, text=True,
                                     env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}, timeout=timeout)
            return {k: getattr(process, k) for k in ('returncode', 'stdout', 'stderr')}
        with patch.object(coding, 'generate', return_value=(edits, answer, {})), \
                patch.object(coding, 'verify', side_effect=local_verify):
            result = coding.run(self.plan_dir, run_dir, 'astra', command, 10)
        return run_dir, result

    def test_new_source_and_test_run_verify_apply(self):
        self.make_plan(['helper.py', 'tests/test_helper.py'])
        edits = {'helper.py': 'value = 2\n',
                 'tests/test_helper.py': 'from helper import value\nassert value == 2\n'}
        command = [sys.executable, '-B', '-c',
                   'import runpy; runpy.run_path("tests/test_helper.py"); import code; assert code.value == 1']
        run_dir, result = self.run_candidate(edits, command)
        self.assertEqual(result['status'], 'verified', result)
        self.assertFalse((self.repo / 'helper.py').exists())
        self.assertIn('--- /dev/null', (run_dir / 'changes.diff').read_text())
        self.assertIn('helper.py', result['candidate_hashes'])
        with patch.object(coding, 'verify', return_value={'returncode': 0, 'stdout': '', 'stderr': ''}):
            self.assertEqual(coding.reverify(run_dir, 5)['status'], 'verified')
        coding.apply(run_dir)
        for p, content in edits.items():
            self.assertEqual((self.repo / p).read_text(), content)

    def test_existing_test_edit_requires_explicit_plan(self):
        (self.repo / 'test_code.py').write_text('assert False\n')
        rc.git(self.repo, 'add', 'test_code.py')
        self.make_plan(test_edits=['test_code.py'])
        run_dir, result = self.run_candidate({'test_code.py': 'assert True\n'},
                                             [sys.executable, '-B', 'test_code.py'])
        self.assertEqual(result['status'], 'verified', result)
        coding.apply(run_dir)
        self.assertEqual((self.repo / 'test_code.py').read_text(), 'assert True\n')

    def test_invalid_creation_targets_are_rejected_before_plan_write(self):
        (self.repo / 'occupied.py').write_text('untracked\n')
        (self.repo / 'linked').symlink_to(self.root, target_is_directory=True)
        rc.git(self.repo, 'config', 'core.ignoreCase', 'true')
        for p in ['code.py', 'CODE.py', 'occupied.py', 'code.py/child.py', '../escape.py',
                  'nested/../alias.py', './alias.py', 'nested//alias.py', 'linked/new.py',
                  'AGENTS.md', 'AgEnTs.md', 'policies/new.py', '.git/config.py', '.env.py', 'node_modules/a.py']:
            with self.subTest(path=p), self.assertRaises(rc.ProtocolError):
                self.make_plan([p])
            self.assertFalse(self.plan_dir.exists())

    def test_duplicate_or_parent_child_creation_targets_rejected(self):
        for paths in [['a.py', 'a.py'], ['a.py', 'a.py/child.py'], ['a.py', 'A.py']]:
            with self.subTest(paths=paths), self.assertRaises(rc.ProtocolError):
                self.make_plan(paths)

    def test_test_edit_targets_must_be_existing_eligible_tests(self):
        for p in ['code.py', 'test_missing.py', 'AGENTS.md']:
            with self.subTest(path=p), self.assertRaises(rc.ProtocolError):
                self.make_plan(test_edits=[p])

    def test_apply_refuses_new_destination_even_when_git_ignores_it(self):
        (self.repo / '.gitignore').write_text('helper.py\n')
        rc.git(self.repo, 'add', '.gitignore')
        self.make_plan(['helper.py'])
        run_dir, result = self.run_candidate({'helper.py': 'value = 2\n'}, [sys.executable, '-c', 'pass'])
        self.assertEqual(result['status'], 'verified', result)
        (self.repo / 'helper.py').write_text('other work\n')
        with self.assertRaises(rc.ProtocolError):
            coding.apply(run_dir)
        self.assertEqual((self.repo / 'helper.py').read_text(), 'other work\n')

    def test_new_candidate_tampering_rejected_by_reverify_and_apply(self):
        self.make_plan(['helper.py'])
        run_dir, result = self.run_candidate({'helper.py': 'value = 2\n'}, [sys.executable, '-c', 'pass'])
        self.assertEqual(result['status'], 'verified', result)
        (run_dir / 'candidate/helper.py').write_text('value = 99\n')
        with self.assertRaises(rc.ProtocolError):
            coding.reverify(run_dir, 5)
        with self.assertRaises(rc.ProtocolError):
            coding.apply(run_dir)

    def test_failure_rolls_back_new_files_and_directories(self):
        self.make_plan(['new/package/helper.py'])
        run_dir, result = self.run_candidate({'new/package/helper.py': 'value = 2\n', 'code.py': 'value = 2\n'},
                                             [sys.executable, '-c', 'pass'])
        self.assertEqual(result['status'], 'verified', result)
        with patch.object(coding.os, 'replace', side_effect=OSError('disk failure')):
            with self.assertRaises(rc.ProtocolError):
                coding.apply(run_dir)
        self.assertFalse((self.repo / 'new').exists())
        self.assertEqual((self.repo / 'code.py').read_text(), 'value = 1\n')
        self.assertEqual(json.loads((run_dir / 'result.json').read_text())['status'], 'apply_failed')

    def test_destination_created_during_apply_is_not_overwritten(self):
        self.make_plan(['helper.py'])
        run_dir, result = self.run_candidate({'code.py': 'value = 2\n', 'helper.py': 'value = 2\n'},
                                             [sys.executable, '-c', 'pass'])
        self.assertEqual(result['status'], 'verified', result)
        link = os.link
        def raced_link(src, dst):
            Path(dst).write_text('concurrent work\n')
            link(src, dst)
        with patch.object(coding.os, 'link', side_effect=raced_link):
            with self.assertRaises(rc.ProtocolError):
                coding.apply(run_dir)
        self.assertEqual((self.repo / 'helper.py').read_text(), 'concurrent work\n')
        self.assertEqual((self.repo / 'code.py').read_text(), 'value = 1\n')

    def test_rollback_preserves_concurrent_changes_and_records_incomplete_recovery(self):
        self.make_plan(['new/helper.py'])
        run_dir, result = self.run_candidate({'new/helper.py': 'value = 2\n', 'code.py': 'value = 2\n'},
                                             [sys.executable, '-c', 'pass'])
        self.assertEqual(result['status'], 'verified', result)
        def fail_after_concurrent_edit(src, dst):
            (self.repo / 'new/helper.py').write_text('concurrent work\n')
            raise OSError('disk failure')
        with patch.object(coding.os, 'replace', side_effect=fail_after_concurrent_edit):
            with self.assertRaises(rc.ProtocolError):
                coding.apply(run_dir)
        self.assertEqual((self.repo / 'new/helper.py').read_text(), 'concurrent work\n')
        result = json.loads((run_dir / 'result.json').read_text())
        self.assertEqual(result['status'], 'apply_failed')
        self.assertEqual(result['recovery_incomplete'], ['new/helper.py'])

    def test_verification_detects_mutation_of_new_file(self):
        self.make_plan(['helper.py'])
        run_dir, result = self.run_candidate({'helper.py': 'value = 2\n'},
                                             [sys.executable, '-c', 'open("helper.py", "w").write("changed")'])
        self.assertEqual(result['status'], 'failed', result)
        with self.assertRaises(rc.ProtocolError):
            coding.apply(run_dir)

    def test_failed_verification_can_recover_without_generation(self):
        self.make_plan(['helper.py'])
        run_dir, result = self.run_candidate({'helper.py': 'value = 2\n'}, [sys.executable, '-c', 'exit(1)'])
        self.assertEqual(result['status'], 'verification_failed', result)
        with self.assertRaises(rc.ProtocolError):
            coding.apply(run_dir)
        with patch.object(coding, 'generate', side_effect=AssertionError('must not regenerate')), \
                patch.object(coding, 'verify', return_value={'returncode': 0, 'stdout': '', 'stderr': ''}):
            self.assertEqual(coding.reverify(run_dir, 5)['status'], 'verified')
        coding.apply(run_dir)
        self.assertEqual((self.repo / 'helper.py').read_text(), 'value = 2\n')

    def test_unplanned_test_and_source_additions_are_rejected(self):
        (self.repo / 'conftest.py').write_text('# test configuration\n')
        rc.git(self.repo, 'add', '.')
        plan = self.make_plan()
        self.assertEqual(plan['version'], 1)
        for p in ['conftest.py', 'test_new.py', 'unknown.py']:
            with self.subTest(path=p), self.assertRaises(rc.ProtocolError):
                coding.materialize(plan, self.root / 'candidate', {p: 'pass\n'})

    def test_new_empty_file_is_visible_in_diff(self):
        self.make_plan(['package/__init__.py', 'helper.py'])
        run_dir, result = self.run_candidate({'package/__init__.py': '', 'helper.py': 'value = 2'},
                                             [sys.executable, '-c', 'pass'])
        self.assertEqual(result['status'], 'verified', result)
        diff = (run_dir / 'changes.diff').read_text()
        self.assertIn('package/__init__.py', diff)
        self.assertIn('new file mode 100644', diff)
        checked = subprocess.run(['git', '-C', str(self.repo), 'apply', '--check', str(run_dir / 'changes.diff')],
                                 capture_output=True, text=True)
        self.assertEqual(checked.returncode, 0, checked.stderr)

    def test_cli_records_explicit_permissions_without_provider_calls(self):
        (self.repo / 'test_code.py').write_text('assert True\n')
        rc.git(self.repo, 'add', 'test_code.py')
        task = self.root / 'task.txt'
        task.write_text('Add helper and tests')
        checked = subprocess.run([sys.executable, str(Path(coding.__file__)), 'plan', '--repo', str(self.repo),
                                  '--out', str(self.plan_dir), '--task-file', str(task),
                                  '--allow-create', 'helper.py', '--allow-test-edit', 'test_code.py'],
                                 capture_output=True, text=True)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        plan = rc.load_plan(self.plan_dir)
        self.assertEqual(plan['version'], 2)
        self.assertEqual(plan['create_paths'], ['helper.py'])
        self.assertEqual(plan['test_edit_paths'], ['test_code.py'])
        self.assertIn('helper.py', (self.plan_dir / 'PLAN.md').read_text())

    def test_generation_schema_allows_only_declared_test_edits_and_additions(self):
        (self.repo / 'test_code.py').write_text('assert True\n')
        (self.repo / 'test_other.py').write_text('assert True\n')
        rc.git(self.repo, 'add', '.')
        plan = self.make_plan(['helper.py'], ['test_code.py'])
        folder = self.root / 'generation'
        answer = {'summary': 'new helper', 'needs_context': [],
                  'files': [{'path': 'helper.py', 'content': 'value = 2\n'}]}
        def provider(*args):
            (folder / 'answer.json').write_text(json.dumps(answer))
            return {'returncode': 0, 'stdout': '', 'stderr': ''}
        with patch.object(coding, 'bounded_process', side_effect=provider), \
                patch.object(coding, 'parse_codex_events', return_value={
                    'failed': False, 'completed': True, 'contaminated': False}):
            edits, _, _ = coding.generate(plan, list(plan['files']), folder, 5)
        self.assertEqual(edits, {'helper.py': 'value = 2\n'})
        schema = json.loads((folder / 'schema.json').read_text())
        allowed = schema['properties']['files']['items']['properties']['path']['enum']
        self.assertIn('helper.py', allowed)
        self.assertIn('test_code.py', allowed)
        self.assertNotIn('test_other.py', allowed)
        for index, entry in enumerate([
                {'path': 'test_other.py', 'content': 'pass\n'},
                {'path': 'unplanned.py', 'content': 'pass\n'},
                {'path': 'helper.py', 'content': '\0'},
                {'path': 'helper.py', 'content': 'x' * 100001}]):
            folder = self.root / f'rejected-{index}'
            answer['files'] = [entry]
            with self.subTest(path=entry['path'], index=index), \
                    patch.object(coding, 'bounded_process', side_effect=provider), \
                    patch.object(coding, 'parse_codex_events', return_value={
                        'failed': False, 'completed': True, 'contaminated': False}), \
                    self.assertRaises(rc.ProtocolError):
                coding.generate(plan, list(plan['files']), folder, 5)


if __name__ == '__main__':
    unittest.main()
