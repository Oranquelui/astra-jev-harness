"""Desktop handoff boundaries, freshness, usage, and failure recovery."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from desktop import context as dc
from shared import repo_context as rc
from shared.jev import ProtocolError


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        for args in (['init', '-q'], ['config', 'user.email', 'test@example.invalid'], ['config', 'user.name', 'Test']):
            subprocess.run(['git', '-C', str(self.repo), *args], check=True, capture_output=True)
        (self.repo / 'main.py').write_text('def value():\n    return 1\n')
        subprocess.run(['git', '-C', str(self.repo), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(self.repo), 'commit', '-qm', 'fixture'], check=True)
        self.plan = self.root / 'plan'
        dc.make_plan(self.repo, 'Update value and preserve existing behavior.', self.plan)
        self.out = self.root / 'selection'
        self.credential = patch.object(dc, 'execution_environment', return_value=({'TYPESAFE_API_KEY': 'fixture'}, 'environment'))
        self.credential.start()
        self.addCleanup(self.credential.stop)

    def response(self, case):
        return {'paths': list(case['files']), 'probabilities': {p: .9 for p in case['files']},
                'fallback': None, 'usage': {'input_tokens': 10, 'output_tokens': 2}, 'model': 'fixture'}

    def test_selected_context_is_read_only_and_keeps_parent_key(self):
        before = rc.git(self.repo, 'status', '--porcelain=v1', '-z')
        with patch.object(rc, 'call_jev', side_effect=self.response) as jev, patch.dict(os.environ, {'TYPESAFE_API_KEY': 'parent'}):
            record = dc.select(self.plan, self.out, 1)
            self.assertEqual(os.environ['TYPESAFE_API_KEY'], 'parent')
        self.assertEqual(jev.call_count, 1)
        self.assertEqual(record['astra_child_calls'], 0)
        self.assertEqual(record['attempted_calls'], 1)
        self.assertEqual(dc.check(self.out)['status'], 'fresh')
        self.assertEqual(rc.git(self.repo, 'status', '--porcelain=v1', '-z'), before)
        self.assertEqual(json.loads((self.out / 'context.json').read_text())['files']['main.py'], (self.repo / 'main.py').read_text())
        self.assertNotIn('TYPESAFE_API_KEY', (self.out / 'selection.json').read_text())

    def test_budget_rejects_before_credentials_or_provider(self):
        p = json.loads((self.plan / 'plan.json').read_text())
        p['files']['more.py'] = {'content': 'x' * 21900}
        with patch.object(dc, 'load_desktop_plan', return_value=p), patch.object(dc, 'fresh'), \
                patch.object(rc, 'jev_batches', return_value=[{}, {}]), \
                patch.object(dc, 'execution_environment') as credentials, patch.object(rc, 'call_jev') as jev:
            with self.assertRaises(ProtocolError):
                dc.select(self.plan, self.out, 1)
        credentials.assert_not_called()
        jev.assert_not_called()
        self.assertFalse(self.out.exists())

    def test_changed_dirty_file_is_rejected_even_when_status_is_unchanged(self):
        (self.repo / 'main.py').write_text('before\n')
        self.plan = self.root / 'dirty-plan'
        dc.make_plan(self.repo, 'Update value.', self.plan)
        (self.repo / 'main.py').write_text('after\n')
        with patch.object(rc, 'call_jev') as jev, self.assertRaises(ProtocolError):
            dc.select(self.plan, self.out, 1)
        jev.assert_not_called()

    def test_failure_saves_completed_and_attempted_calls_without_retry(self):
        with patch.object(rc, 'jev_batches', return_value=[{'main.py': 'one'}, {'main.py': 'two'}]), \
                patch.object(rc, 'call_jev', side_effect=[self.response({'files': {'main.py': 'one'}}), ProtocolError('private provider body')]) as jev, \
                patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ProtocolError):
                dc.select(self.plan, self.out, 2)
            self.assertNotIn('TYPESAFE_API_KEY', os.environ)
        record = json.loads((self.out / 'selection.json').read_text())
        self.assertEqual(record['status'], 'failed')
        self.assertEqual(record['attempted_calls'], 2)
        self.assertEqual(len(record['jev_calls']), 1)
        self.assertEqual(jev.call_count, 2)
        self.assertNotIn('private provider body', (self.out / 'selection.json').read_text())
        with patch.object(rc, 'call_jev') as jev, self.assertRaises(ProtocolError):
            dc.select(self.plan, self.out, 2)
        jev.assert_not_called()
        with self.assertRaises(ProtocolError):
            dc.check(self.out)

    def test_change_during_provider_call_cannot_produce_usable_context(self):
        def change(case):
            (self.repo / 'main.py').write_text('concurrent change\n')
            return self.response(case)
        with patch.object(rc, 'call_jev', side_effect=change), self.assertRaises(ProtocolError):
            dc.select(self.plan, self.out, 1)
        self.assertEqual(json.loads((self.out / 'selection.json').read_text())['status'], 'failed')
        self.assertFalse((self.out / 'context.json').exists())

    def test_consumption_rejects_context_tampering_or_new_repo_state(self):
        with patch.object(rc, 'call_jev', side_effect=self.response):
            dc.select(self.plan, self.out, 1)
        original = (self.out / 'context.json').read_bytes()
        (self.out / 'context.json').write_text('{}')
        with self.assertRaises(ProtocolError):
            dc.check(self.out)
        (self.out / 'context.json').write_bytes(original)
        (self.repo / 'new.py').write_text('untracked\n')
        with self.assertRaises(ProtocolError):
            dc.check(self.out)

    def test_desktop_process_does_not_import_cli_implementation(self):
        script = 'import sys; from desktop import context; assert not any(x.startswith("cli.") for x in sys.modules)'
        result = subprocess.run([os.sys.executable, '-c', script], cwd=Path(__file__).resolve().parent.parent, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_cli_rejects_desktop_context_plan(self):
        from cli import coding
        with self.assertRaises(ProtocolError):
            coding.load_plan(self.plan)

    def test_desktop_rejects_cli_plan(self):
        cli_plan = self.root / 'cli-plan'
        rc.snapshot(self.repo, 'Update value.', cli_plan)
        with self.assertRaises(ProtocolError):
            dc.load_desktop_plan(cli_plan)

    def test_offline_compare_never_calls_provider_or_keychain_and_keeps_artifacts(self):
        with patch.object(rc, 'call_jev', side_effect=self.response):
            dc.select(self.plan, self.out, 1, policy='per-file')
        before = {p.name: p.read_bytes() for p in self.out.iterdir()}
        # Replay is historical: source edits should not require a paid refresh.
        (self.repo / 'main.py').write_text('later source state\n')
        with patch.object(rc, 'call_jev', side_effect=AssertionError('offline only')), \
                patch.object(dc, 'execution_environment', side_effect=AssertionError('no credentials')):
            report = dc.compare(self.out, ['main.py'])
        self.assertEqual(report['additional_provider_calls'], 0)
        self.assertEqual(report['policies']['per-file']['required_recall'], 1)
        self.assertEqual(report['policies']['batch']['missing_required_paths'], [])
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.out.iterdir()})

    def test_compare_does_not_claim_quality_without_labels_and_rejects_bad_labels(self):
        with patch.object(rc, 'call_jev', side_effect=self.response):
            dc.select(self.plan, self.out, 1)
        self.assertIsNone(dc.compare(self.out)['policies']['batch']['required_recall'])
        with self.assertRaises(ProtocolError):
            dc.compare(self.out, ['not-in-plan.py'])
        with self.assertRaises(ProtocolError):
            dc.compare(self.out, ['main.py', 'main.py'])
        (self.plan / 'plan.json').write_text('{}')
        with self.assertRaises(ProtocolError):
            dc.compare(self.out)

    def test_compare_reports_a_required_file_lost_by_experimental_policy(self):
        (self.repo / 'noise.py').write_text('answer = 1\n')
        rc.git(self.repo, 'add', 'noise.py')
        self.plan = self.root / 'comparison-plan'
        dc.make_plan(self.repo, 'Update value.', self.plan)
        def probabilities(case):
            return {'paths': list(case['files']), 'probabilities': {'main.py': .5, 'noise.py': .01}}
        with patch.object(rc, 'call_jev', side_effect=probabilities):
            dc.select(self.plan, self.out, 1)
        report = dc.compare(self.out, ['main.py', 'noise.py'])
        self.assertEqual(report['policies']['batch']['required_recall'], 1)
        self.assertEqual(report['policies']['per-file']['required_recall'], .5)
        self.assertEqual(report['policies']['per-file']['missing_required_paths'], ['noise.py'])

    def test_shared_budget_is_enforced_before_any_call(self):
        plan = rc.load_plan(self.plan)
        with patch.object(rc, 'jev_batches', return_value=[{}, {}]), patch.object(rc, 'call_jev') as jev:
            with self.assertRaises(ProtocolError):
                rc.select(plan, 'jev', max_calls=1)
        jev.assert_not_called()


if __name__ == '__main__':
    unittest.main()
