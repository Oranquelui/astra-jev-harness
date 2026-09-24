"""Configured models must not import unrelated settings or invent usage identity."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import coding
from cli import model_config
from shared.jev import ProtocolError
from tests import test_coding


class ModelSettingsTests(unittest.TestCase):
    def test_allowlist_preserves_model_effort_and_drops_other_settings(self):
        settings = model_config.model_settings({
            'model': 'gpt-6-sol', 'model_reasoning_effort': 'xhigh',
            'model_provider': 'openai', 'mcp_servers': {'private': {'env': {'KEY': 'secret'}}},
            'sandbox_mode': 'danger-full-access', 'developer_instructions': 'unrelated'})
        self.assertEqual(settings, {'model': 'gpt-6-sol', 'reasoning': 'xhigh'})
        self.assertEqual(model_config.model_arguments(settings),
                         ['--model', 'gpt-6-sol', '-c', 'model_reasoning_effort="xhigh"'])

    def test_absent_settings_leave_cli_defaults_without_astra_fallback(self):
        settings = model_config.model_settings({})
        self.assertEqual(settings, {'model': None, 'reasoning': None})
        self.assertEqual(model_config.model_arguments(settings), [])

    def test_unsupported_or_invalid_settings_fail_without_echoing_values(self):
        for config in ({'model_provider': 'private-provider-secret'},
                       {'profile': 'private-profile-secret'},
                       {'model': 'private\nsecret'},
                       {'model_reasoning_effort': 'private-secret'},
                       {'model': 123}):
            with self.subTest(config=config), self.assertRaises(ProtocolError) as caught:
                model_config.model_settings(config)
            self.assertNotIn('secret', str(caught.exception))


class ConfigurationTransportTests(unittest.TestCase):
    def invoke_reader(self, script, timeout=3):
        real_popen = subprocess.Popen
        with tempfile.TemporaryDirectory() as tmp:
            script_path = Path(tmp) / 'fake_codex.py'
            script_path.write_text(script)
            children = []
            def start(argv, **kwargs):
                self.assertEqual(argv[:3], ['codex', 'app-server', '--stdio'])
                self.assertNotIn('TYPESAFE_API_KEY', kwargs['env'])
                process = real_popen([sys.executable, '-u', str(script_path)], **kwargs)
                children.append(process)
                return process
            try:
                with patch.object(model_config.subprocess, 'Popen', side_effect=start), \
                        patch.dict(os.environ, {'TYPESAFE_API_KEY': 'private-fixture-key'}):
                    return model_config.read_model_settings(tmp, timeout)
            finally:
                self.assertTrue(all(p.poll() is not None for p in children))

    def test_handshake_reads_only_allowlisted_settings(self):
        result = self.invoke_reader('''import json, sys
first = json.loads(sys.stdin.readline())
assert first['method'] == 'initialize'
print(json.dumps({'id': first['id'], 'result': {}}), flush=True)
assert json.loads(sys.stdin.readline())['method'] == 'initialized'
request = json.loads(sys.stdin.readline())
assert request['method'] == 'config/read'
assert request['params']['includeLayers'] is False
assert request['params']['cwd']
print(json.dumps({'id': request['id'], 'result': {'config': {
    'model': 'configured-test', 'model_reasoning_effort': 'high',
    'mcp_servers': {'private': {'token': 'private-fixture-secret'}}}}}), flush=True)
''')
        self.assertEqual(result, {'model': 'configured-test', 'reasoning': 'high'})

    def test_transport_failure_timeout_and_malformed_output_are_redacted(self):
        scripts = [
            "import time; time.sleep(10)",
            "print('private-fixture-secret', flush=True)",
            "import json; print(json.dumps({'id':1,'error':{'message':'private-fixture-secret'}}), flush=True)",
        ]
        for script in scripts:
            with self.subTest(script=script), self.assertRaises(ProtocolError) as caught:
                self.invoke_reader(script, timeout=.25)
            self.assertNotIn('private-fixture-secret', str(caught.exception))


class GenerationSettingsTests(unittest.TestCase):
    setUp = test_coding.RepositoryTests.setUp
    plan = test_coding.RepositoryTests.plan

    def test_generate_forwards_configured_values_preserving_isolation(self):
        plan = self.plan()
        folder = self.root / 'generation'
        def provider(argv, cwd, env, timeout, prompt):
            self.assertIn('--ignore-user-config', argv)
            self.assertEqual(argv[argv.index('--model') + 1], 'gpt-6-sol')
            self.assertIn('model_reasoning_effort="xhigh"', argv)
            self.assertEqual(argv[argv.index('--sandbox') + 1], 'read-only')
            self.assertNotIn('TYPESAFE_API_KEY', env)
            (folder / 'answer.json').write_text(json.dumps(
                {'summary': 'unchanged', 'needs_context': [], 'files': []}))
            return {'returncode': 0, 'stdout': '{"type":"turn.completed","usage":{"input_tokens":5}}',
                    'stderr': ''}
        with patch.object(coding, 'read_model_settings', return_value={
                'model': 'gpt-6-sol', 'reasoning': 'xhigh'}), \
                patch.object(coding, 'bounded_process', side_effect=provider):
            _, _, meta = coding.generate(plan, list(plan['files']), folder, 5)
        self.assertEqual(meta['requested_model'], 'gpt-6-sol')
        self.assertEqual(meta['requested_reasoning'], 'xhigh')
        self.assertIsNone(meta['model'])  # exec's usage event does not identify the serving model.
        self.assertIsNone(meta['reasoning'])

    def test_timeout_record_retains_requested_settings_without_false_model(self):
        plan = self.plan()
        folder = self.root / 'generation'
        with patch.object(coding, 'read_model_settings', return_value={
                'model': 'gpt-6-sol', 'reasoning': 'high'}), \
                patch.object(coding, 'bounded_process', side_effect=ProtocolError('timeout')), \
                self.assertRaises(ProtocolError):
            coding.generate(plan, list(plan['files']), folder, 5)
        meta = json.loads((folder / 'metadata.json').read_text())
        self.assertEqual(meta['requested_model'], 'gpt-6-sol')
        self.assertTrue(meta['failed'])
        self.assertIsNone(meta['model'])

    def test_config_failure_precedes_any_paid_selection(self):
        self.plan()
        with patch.object(coding, 'read_model_settings', side_effect=ProtocolError('Config unavailable')), \
                patch.object(coding, 'select') as select, patch.object(coding, 'generate') as generate:
            result = coding.run(self.plan_dir, self.root / 'run', 'jev', None, 5)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['stage'], 'model_configuration')
        self.assertEqual(result['attempted_astra_calls'], 0)
        select.assert_not_called()
        generate.assert_not_called()


if __name__ == '__main__':
    unittest.main()
