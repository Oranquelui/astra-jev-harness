"""The Desktop Skill must not silently turn requested Jev selection into local reads."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from desktop import context as dc
from shared import jev
from shared import repo_context as rc


LAUNCHER = Path(__file__).resolve().parents[1] / 'Codex Desktop/skills/astra-jev-coding/scripts/context.py'


class RequiredJevTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        for args in (('init', '-q'), ('config', 'user.email', 'fixture@example.invalid'),
                     ('config', 'user.name', 'Fixture')):
            rc.git(self.repo, *args)
        (self.repo / 'main.py').write_text('def value():\n    return 1\n')
        rc.git(self.repo, 'add', '.')
        rc.git(self.repo, 'commit', '-qm', 'fixture')
        self.plan = self.root / 'plan'
        dc.make_plan(self.repo, 'Update value while preserving behavior.', self.plan)
        self.out = self.root / 'selection'
        self.link = self.root / 'installed-skill'
        self.link.symlink_to(LAUNCHER.resolve().parents[1], target_is_directory=True)
        self.credentials = patch.object(dc, 'execution_environment',
                                        return_value=({'TYPESAFE_API_KEY': 'fixture'}, 'environment'))
        self.credentials.start()
        self.addCleanup(self.credentials.stop)

    @staticmethod
    def response(case):
        return {'paths': list(case['files']),
                'probabilities': {path: .9 for path in case['files']},
                'usage': {'input_tokens': 10, 'output_tokens': 2},
                'fallback': None, 'model': jev.JEV_MODEL, 'reused': False}

    @staticmethod
    def cached_response(payload):
        value = {'model': payload['model'], 'answers': {
            key: {'type': 'noul', 'noul': .9} for key in payload['questions']}}
        return value, {'model': payload['model'], 'reused': False,
                       'usage': {'input_tokens': 10, 'output_tokens': 2},
                       'request_sha256': jev.request_hash(payload), 'seconds': .01}

    def rewrite_record(self, directory, **updates):
        path = directory / 'selection.json'
        record = json.loads(path.read_text())
        record.update(updates)
        path.write_text(json.dumps(record))

    def run_installed(self, *args):
        env = os.environ.copy()
        env.pop('TYPESAFE_API_KEY', None)
        return subprocess.run([sys.executable, str(self.link / 'scripts/context.py'), *args],
                              cwd=self.root, env=env, text=True, capture_output=True, timeout=15)

    def test_strict_local_and_small_auto_reject_before_credentials_provider_or_output(self):
        for mode in ('local', 'auto'):
            out = self.root / mode
            with self.subTest(mode=mode), patch.object(dc, 'execution_environment') as key, \
                    patch.object(rc, 'call_jev') as call, patch.object(rc, 'request_jev') as request:
                with self.assertRaisesRegex(jev.ProtocolError, 'Jev selection required'):
                    dc.select(self.plan, out, mode=mode, require_jev=True)
                key.assert_not_called()
                call.assert_not_called()
                request.assert_not_called()
                self.assertFalse(out.exists())

    def test_strict_default_jev_pipeline_records_real_judgments_and_leaves_target_unchanged(self):
        before = rc.git(self.repo, 'status', '--porcelain=v1', '-z')
        with patch.object(rc, 'call_jev', side_effect=self.response) as call:
            record = dc.select(self.plan, self.out, max_calls=1, require_jev=True)
        self.assertEqual(call.call_count, 1)
        self.assertTrue(record['require_jev'])
        self.assertEqual(record['attempted_calls'], 1)
        self.assertEqual(record['metrics']['judged_fragments'], 1)
        self.assertEqual(dc.check(self.out, require_jev=True)['status'], 'fresh')
        read = dc.read_context(self.out, 'main.py', 2, 2, require_jev=True)
        self.assertEqual(read['text'], '    return 1\n')
        self.assertEqual(read['provider_calls'], 0)
        self.assertEqual(before, rc.git(self.repo, 'status', '--porcelain=v1', '-z'))

    def test_strict_cache_reuses_valid_judgments_without_provider_or_credentials(self):
        cache = self.root / 'cache'
        with patch.object(rc, 'request_jev', side_effect=self.cached_response) as first_call:
            dc.select(self.plan, self.out, max_calls=1, cache_dir=cache, require_jev=True)
        self.assertEqual(first_call.call_count, 1)
        with patch.object(dc, 'execution_environment') as key, \
                patch.object(rc, 'request_jev') as request, patch.object(rc, 'call_jev') as call:
            replay = self.root / 'replay'
            record = dc.select(self.plan, replay, max_calls=1, cache_dir=cache, require_jev=True)
            self.assertEqual(dc.check(replay, require_jev=True)['status'], 'fresh')
            self.assertIn('return 1', dc.read_context(replay, 'main.py', require_jev=True)['text'])
            key.assert_not_called()
            request.assert_not_called()
            call.assert_not_called()
        self.assertEqual(record['attempted_calls'], 0)
        self.assertTrue(record['jev_calls'][0]['reused'])
        self.assertEqual(record['metrics']['judged_fragments'], 1)

    def test_strict_saved_local_context_is_rejected_by_check_and_read(self):
        dc.select(self.plan, self.out, mode='local')
        with self.assertRaisesRegex(jev.ProtocolError, 'Jev selection required'):
            dc.check(self.out, require_jev=True)
        with self.assertRaisesRegex(jev.ProtocolError, 'Jev selection required'):
            dc.read_context(self.out, 'main.py', require_jev=True)

    def test_metadata_claims_cannot_replace_saved_judgments(self):
        dc.select(self.plan, self.out, mode='local')
        self.rewrite_record(self.out, route='jev', selection_mode='jev', attempted_calls=1,
                            metrics={'judged_files': 1, 'judged_fragments': 1}, require_jev=True)
        # Persisted strict intent must also apply when a native caller omits the flag.
        for explicit in (False, True):
            with self.subTest(explicit=explicit), self.assertRaisesRegex(jev.ProtocolError, 'Jev selection required'):
                dc.check(self.out, require_jev=explicit)
            with self.subTest(read_explicit=explicit), self.assertRaisesRegex(jev.ProtocolError, 'Jev selection required'):
                dc.read_context(self.out, 'main.py', require_jev=explicit)

    def test_strict_read_replays_probability_validation(self):
        with patch.object(rc, 'call_jev', side_effect=self.response):
            dc.select(self.plan, self.out, require_jev=True)
        self.rewrite_record(self.out, jev_calls=[{'probabilities': {'missing.py': .9}}])
        with self.assertRaises(jev.ProtocolError):
            dc.check(self.out, require_jev=True)
        with self.assertRaises(jev.ProtocolError):
            dc.read_context(self.out, 'main.py', require_jev=True)

    def test_strict_zero_judgment_result_fails_before_context_is_published(self):
        plan = dc.load_desktop_plan(self.plan)
        no_judgments = {**rc.resolve_selection(plan, []), 'route': 'jev', 'jev_calls': []}
        with patch.object(rc, 'select', return_value=no_judgments), \
                self.assertRaisesRegex(jev.ProtocolError, 'Jev selection required'):
            dc.select(self.plan, self.out, require_jev=True)
        self.assertFalse((self.out / 'context.json').exists())
        self.assertEqual(json.loads((self.out / 'selection.json').read_text())['status'], 'failed')

    def test_provider_failure_preserves_attempt_without_falling_back_to_local(self):
        error = jev.ProtocolError('PRIVATE PROVIDER BODY', error_kind='http_error', http_status=403)
        with patch.object(rc, 'call_jev', side_effect=error) as call, self.assertRaises(jev.ProtocolError):
            dc.select(self.plan, self.out, require_jev=True)
        self.assertEqual(call.call_count, 1)
        saved = (self.out / 'selection.json').read_text()
        record = json.loads(saved)
        self.assertEqual(record['status'], 'failed')
        self.assertEqual(record['attempted_calls'], 1)
        self.assertEqual(record['jev_calls'], [])
        self.assertEqual(record['failure']['http_status'], 403)
        self.assertNotIn('PRIVATE PROVIDER BODY', saved)
        self.assertFalse((self.out / 'context.json').exists())
        with self.assertRaises(jev.ProtocolError):
            dc.check(self.out, require_jev=True)
        with self.assertRaises(jev.ProtocolError):
            dc.read_context(self.out, 'main.py', require_jev=True)

    def test_missing_credential_has_no_local_fallback_or_output(self):
        with patch.object(dc, 'execution_environment', return_value=({}, 'absent')), \
                patch.object(rc, 'call_jev') as call, patch.object(rc, 'request_jev') as request:
            with self.assertRaisesRegex(jev.ProtocolError, 'credential unavailable'):
                dc.select(self.plan, self.out, require_jev=True)
            call.assert_not_called()
            request.assert_not_called()
        self.assertFalse(self.out.exists())

    def test_installed_symlink_rejects_local_and_small_auto_with_actionable_error(self):
        for mode in ('local', 'auto'):
            out = self.root / ('installed-' + mode)
            result = self.run_installed('select', '--plan', str(self.plan), '--out', str(out), '--mode=' + mode)
            with self.subTest(mode=mode):
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Jev selection required', result.stderr)
                self.assertFalse(out.exists())

    def test_installed_symlink_default_check_and_read_reject_previous_local_record(self):
        dc.select(self.plan, self.out, mode='local')
        for args in (('check', '--selection', str(self.out)),
                     ('read', '--selection', str(self.out), '--path', 'main.py')):
            result = self.run_installed(*args)
            with self.subTest(command=args[0]):
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Jev selection required', result.stderr)
                self.assertNotIn('return 1', result.stdout)

    def test_native_local_baseline_remains_explicitly_available(self):
        with patch.object(dc, 'execution_environment') as key, patch.object(rc, 'call_jev') as call:
            record = dc.select(self.plan, self.out, mode='local')
            self.assertEqual(dc.check(self.out)['status'], 'fresh')
            self.assertIn('return 1', dc.read_context(self.out, 'main.py')['text'])
            self.assertEqual(record['attempted_calls'], 0)
            key.assert_not_called()
            call.assert_not_called()


if __name__ == '__main__':
    unittest.main()
