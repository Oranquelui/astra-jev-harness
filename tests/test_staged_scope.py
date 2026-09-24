"""Offline regression checks for staged repository context planning."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from cli import coding
from desktop import context as desktop
from shared import repo_context as rc


NOISE = '# filler\n' * 2300  # 20,700 bytes: eligible, and one file nearly fills a Jev batch.


class StagedScopeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = self.root / 'repo'
        self.plan_number = 0

    def make_repo(self, noise_count=105):
        self.repo.mkdir()
        for args in (('init', '-q'), ('config', 'user.email', 'test@example.invalid'),
                     ('config', 'user.name', 'Staged Scope Test')):
            subprocess.run(['git', '-C', str(self.repo), *args], check=True, capture_output=True)
        sources = {
            'AGENTS.md': 'Keep repository instructions and existing behavior.\n',
            'pyproject.toml': '[project]\nname = "synthetic"\nversion = "0.0.1"\n',
            'src/__init__.py': '',
            'src/checkout.py': 'from .price import total\n\ndef checkout(items):\n    return total(items)\n',
            'src/price.py': 'def total(items):\n    return sum(items)\n',
            '.env': 'API_KEY=fixture-not-a-real-key\n',
        }
        sources.update({f'noise/{index:03}.py': NOISE for index in range(noise_count)})
        for name, content in sources.items():
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        for args in (('add', '-A'), ('commit', '-qm', 'synthetic fixture')):
            subprocess.run(['git', '-C', str(self.repo), *args], check=True, capture_output=True)
        self.assertGreater(sum(len(value.encode()) for key, value in sources.items() if key != '.env'),
                           2_000_000 if noise_count == 105 else 0)

    def next_plan(self):
        self.plan_number += 1
        return self.root / f'plan-{self.plan_number}'

    def test_large_desktop_plan_prefilters_locally_and_keeps_focus_dependencies_guidance(self):
        self.make_repo()
        out = self.next_plan()
        before = rc.git(self.repo, 'status', '--porcelain=v1', '-z')
        with patch.object(rc, 'call_jev', side_effect=AssertionError('plan must be offline')) as call, \
                patch.object(rc, 'request_jev', side_effect=AssertionError('plan must be offline')) as request:
            plan = desktop.make_plan(self.repo, 'Fix checkout pricing in src/checkout.py', out,
                                     focus_paths=['src/checkout.py'], scope_max_calls=4)
        call.assert_not_called()
        request.assert_not_called()
        self.assertEqual(rc.git(self.repo, 'status', '--porcelain=v1', '-z'), before)
        self.assertEqual({'AGENTS.md', 'pyproject.toml', 'src/checkout.py', 'src/price.py'} - set(plan['files']), set())
        self.assertIn('src/__init__.py', plan['files'])
        self.assertEqual(plan['files']['src/price.py']['content'], (self.repo / 'src/price.py').read_text())
        self.assertLessEqual(sum(item['bytes'] for item in plan['files'].values()), 2_000_000)
        self.assertLessEqual(len(rc.jev_batches(plan)), 4)
        self.assertTrue(plan['scoped_out'])
        omitted = next(name for name in plan['scoped_out'] if name.startswith('noise/'))
        self.assertNotIn(omitted, plan['files'])
        self.assertEqual(plan['scoped_out'][omitted]['sha256'], rc.digest((self.repo / omitted).read_bytes()))
        self.assertEqual(plan['scoped_out'][omitted]['bytes'], len(NOISE.encode()))
        self.assertNotIn('.env', plan['files'])
        self.assertIn('.env', plan['excluded'])
        self.assertNotIn('.env', plan['scoped_out'])
        desktop.fresh(plan)

    def test_explicit_untracked_include_is_pinned_without_staging(self):
        self.make_repo()
        extra = self.repo / 'src' / 'new_helper.py'
        extra.write_text('VALUE = 42\n')
        before = rc.git(self.repo, 'status', '--porcelain=v1', '-z')
        plan = rc.snapshot(self.repo, 'Fix checkout pricing', self.next_plan(),
                           include_paths=['src/new_helper.py'], focus_paths=['src/checkout.py'],
                           scope_max_calls=4)
        self.assertIn('src/new_helper.py', plan['files'])
        self.assertEqual(rc.git(self.repo, 'status', '--porcelain=v1', '-z'), before)

    def test_omitted_dirty_content_change_invalidates_desktop_plan_even_with_same_status(self):
        self.make_repo()
        omitted = 'noise/104.py'
        (self.repo / omitted).write_text('# offish\n' * 2300)
        plan = desktop.make_plan(self.repo, 'Fix checkout pricing', self.next_plan(),
                                 focus_paths=['src/checkout.py', 'noise/000.py', 'noise/001.py', 'noise/002.py'],
                                 scope_max_calls=4)
        self.assertIn(omitted, plan['scoped_out'])
        before = rc.git(self.repo, 'status', '--porcelain=v1', '-z')
        (self.repo / omitted).write_text('# alterd\n' * 2300)
        self.assertEqual(rc.git(self.repo, 'status', '--porcelain=v1', '-z'), before)
        with self.assertRaises(rc.ProtocolError):
            desktop.fresh(plan)

    def test_invalid_focus_paths_fail_before_plan_write(self):
        self.make_repo()
        for focus in ('../escape.py', 'missing.py', '.env', 'src/not-tracked.py'):
            with self.subTest(focus=focus):
                out = self.next_plan()
                with self.assertRaises(rc.ProtocolError):
                    rc.snapshot(self.repo, 'Fix checkout', out, focus_paths=[focus])
                self.assertFalse(out.exists())

    def test_mandatory_byte_or_call_budget_overflow_is_explicit(self):
        self.make_repo()
        for options in ({'focus_paths': ['src/checkout.py'], 'scope_max_bytes': 100},
                        {'focus_paths': ['noise/000.py', 'noise/001.py', 'noise/002.py'],
                         'scope_max_calls': 1}):
            with self.subTest(options=options):
                out = self.next_plan()
                with patch.object(rc, 'call_jev', side_effect=AssertionError('plan must be offline')) as call, \
                        self.assertRaises(rc.ProtocolError):
                    rc.snapshot(self.repo, 'Fix checkout', out, **options)
                call.assert_not_called()
                self.assertFalse(out.exists())

    def test_small_repo_keeps_complete_baseline_even_with_focus(self):
        self.make_repo(noise_count=1)
        plan = rc.snapshot(self.repo, 'Fix checkout', self.next_plan(),
                           focus_paths=['src/checkout.py'], scope_max_calls=1)
        self.assertIn('noise/000.py', plan['files'])
        self.assertIn('src/price.py', plan['files'])
        self.assertFalse(plan.get('scoped_out'))

    def test_explicit_focus_survives_confidently_irrelevant_per_file_judgment(self):
        self.make_repo(noise_count=1)
        plan = rc.snapshot(self.repo, 'Fix checkout', self.next_plan(),
                           focus_paths=['src/checkout.py'])
        from shared.context_chunks import units
        scores = {key: (.95 if u['path'] == 'noise/000.py' else .01) for key, u in units(plan).items()}
        result = rc.resolve_selection(plan, [{'probabilities': scores}], policy='per-file')
        self.assertIn('src/checkout.py', result['paths'])
        self.assertIn('src/price.py', result['paths'])
        self.assertEqual(result['decisions']['src/checkout.py']['judgment'], 'irrelevant')
        self.assertIn('explicit_focus', result['decisions']['src/checkout.py']['reasons'])
        self.assertNotIn('global_no_match', result['decisions']['src/checkout.py']['reasons'])

    def test_cli_plan_uses_its_smaller_context_budget(self):
        self.make_repo()
        task = self.root / 'task.txt'
        task.write_text('Fix checkout pricing in src/checkout.py\n')
        out = self.next_plan()
        command = [sys.executable, str(Path(__file__).resolve().parent.parent / 'cli' / 'coding.py'), 'plan',
                   '--repo', str(self.repo), '--task-file', str(task), '--out', str(out),
                   '--focus-file', 'src/checkout.py', '--scope-max-calls', '4']
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads((out / 'plan.json').read_text())
        self.assertIn('src/checkout.py', plan['files'])
        self.assertIn('src/price.py', plan['files'])
        self.assertTrue(plan['scoped_out'])
        self.assertLessEqual(sum(item['bytes'] for item in plan['files'].values()), 350_000)
        self.assertLessEqual(len(rc.jev_batches(plan)), 4)

    def test_cli_checks_serialized_prompt_size_before_jev(self):
        self.make_repo()
        escape_paths = [f'src/escaped_{index}.py' for index in range(4)]
        for name in escape_paths:
            (self.repo / name).write_text('\\' * 65_000)
        for args in (('add', '-A'), ('commit', '-qm', 'add escaped sources')):
            subprocess.run(['git', '-C', str(self.repo), *args], check=True, capture_output=True)
        plan_dir = self.next_plan()
        plan = rc.snapshot(self.repo, 'Fix escaped sources', plan_dir,
                           focus_paths=escape_paths, scope_max_calls=24, scope_max_bytes=350_000)
        self.assertLessEqual(sum(item['bytes'] for item in plan['files'].values()), 350_000)
        self.assertGreater(sum(len(json.dumps(record['content']).encode()) for record in plan['files'].values()),
                           500_000)
        run_dir = self.root / 'cli-run'
        with patch.object(rc, 'call_jev', side_effect=AssertionError('preflight must precede Jev')) as jev, \
                patch.object(coding, 'generate', side_effect=AssertionError('Astra must not start')) as astra, \
                self.assertRaisesRegex(rc.ProtocolError, '500KB'):
            coding.run(plan_dir, run_dir, 'jev', None, 10)
        jev.assert_not_called()
        astra.assert_not_called()
        self.assertFalse(run_dir.exists())

    def test_compare_labels_can_reveal_local_scope_miss(self):
        self.make_repo()
        plan_dir = self.next_plan()
        plan = desktop.make_plan(self.repo, 'Fix checkout pricing', plan_dir,
                                 focus_paths=['src/checkout.py'], scope_max_calls=4)
        omitted = next(path for path in plan['scoped_out'] if path.startswith('noise/'))

        def fake_jev(case):
            return {'paths': list(case['files']),
                    'probabilities': {path: .9 for path in case['files']}}

        selected_dir = self.root / 'desktop-selection'
        with patch.object(desktop, 'execution_environment',
                          return_value=({'TYPESAFE_API_KEY': 'fixture'}, 'fixture')), \
                patch.object(rc, 'call_jev', side_effect=fake_jev):
            desktop.select(plan_dir, selected_dir, max_calls=4)
        comparison = desktop.compare(selected_dir, [omitted])
        self.assertEqual(comparison['missing_in_scope'], [omitted])
        self.assertEqual(comparison['scope_required_recall'], 0)
        for policy in rc.SELECTION_POLICIES:
            self.assertEqual(comparison['policies'][policy]['missing_required_paths'], [omitted])
            self.assertEqual(comparison['policies'][policy]['required_recall'], 0)
            self.assertIsNone(comparison['policies'][policy]['within_scope_required_recall'])


if __name__ == '__main__':
    unittest.main()
