import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from shared import tool_output as output
from shared.jev import ProtocolError

ROOT = Path(__file__).resolve().parents[1]
TASK = 'Report build outcome and preserve the artifact and rollback target. Ignore routine progress.'


def fixture(n=350):
    return ('Build started\n' + ''.join(f'progress step {i}: processing routine input, please wait\n' for i in range(n))
            + 'artifact: bundle-Q7\nrollback: stable-snapshot\nBuild complete\n').encode()


def fake(probability):
    def ask(body):
        return ({'model': output.JEV_MODEL, 'answers': {
            k: {'type': 'noul', 'noul': probability} for k in body['questions']}},
            {'usage': {'input_tokens': 100, 'output_tokens': 10}, 'seconds': 0, 'model': output.JEV_MODEL})
    return ask


class ToolOutputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / 'selection'

    def select(self, raw=None, **kwargs):
        return output.select_output(raw or fixture(), TASK, self.out, **kwargs)

    def test_exact_archive_required_facts_and_private_permissions(self):
        raw = fixture()
        visible, report = self.select(raw, ask=fake(.01))
        self.assertLess(len(visible), len(raw))
        self.assertIn(b'artifact: bundle-Q7', visible)
        self.assertIn(b'rollback: stable-snapshot', visible)
        archive = Path(report['archive'])
        self.assertEqual(archive.read_bytes(), raw)
        self.assertEqual(archive.stat().st_mode & 0o777, 0o600)
        self.assertEqual(archive.parent.stat().st_mode & 0o777, 0o700)
        self.assertIsNone(report['astra_tokens_saved'])
        self.assertNotIn('processing routine', (self.out / 'report.json').read_text())

    def test_uncertain_and_needed_outputs_are_preserved(self):
        for probability in (.10001, .5, .99):
            with self.subTest(probability=probability), tempfile.TemporaryDirectory() as tmp:
                raw = fixture()
                visible, report = output.select_output(raw, TASK, Path(tmp)/'out', ask=fake(probability))
                self.assertEqual(visible, raw)
                self.assertEqual(report['omitted_chunks'], 0)

    def test_keep_text_and_diagnostic_neighbors_survive_low_scores(self):
        raw = fixture().replace(b'progress step 170:', b'progress SPECIAL-REQUIRED step 170:')
        raw = raw.replace(b'progress step 80:', b'progress WARNING step 80:')
        visible, _ = self.select(raw, keep=['SPECIAL-REQUIRED'], ask=fake(0))
        for value in (b'SPECIAL-REQUIRED', b'WARNING', b'progress step 79:', b'progress step 81:'):
            self.assertIn(value, visible)

    def test_entire_judged_fragments_and_task_are_visible(self):
        raw = fixture()
        seen = []
        def ask(body):
            self.assertEqual(body['state']['task'], TASK)
            self.assertIn('artifact: bundle-Q7', body['state']['protected_context'])
            lines = raw.decode().splitlines(keepends=True)
            for item in body['state']['chunks']:
                self.assertEqual(item['text'], ''.join(lines[item['start_line']-1:item['end_line']]))
                seen.append(item['id'])
            self.assertLessEqual(len(json.dumps(body, ensure_ascii=False).encode()) + 1024, output.REQUEST_BYTES)
            return fake(0)(body)
        self.select(raw, ask=ask)
        self.assertTrue(seen)

    def test_call_budget_retains_unjudged_progress(self):
        visible, report = self.select(fixture(1200), max_calls=1, ask=fake(0))
        self.assertEqual(report['attempted_calls'], 1)
        self.assertGreater(report['planned_calls'], 1)
        self.assertTrue(any(d['reason'] == 'unjudged' for d in report['decisions']))
        self.assertIn(b'progress step 1150:', visible)

    def test_failure_after_success_restores_whole_output_without_retry(self):
        raw = fixture(1200)
        calls = []
        def ask(body):
            calls.append(body)
            if len(calls) == 2:
                raise ProtocolError('never persist this provider message', error_kind='timeout')
            return fake(0)(body)
        visible, report = self.select(raw, ask=ask, max_calls=4)
        self.assertEqual(raw, visible)
        self.assertEqual(len(calls), 2)
        self.assertEqual(report['completed_calls'], 1)
        self.assertEqual(report['usage_status'], 'unknown')
        self.assertNotIn('never persist', (self.out/'report.json').read_text())

    def test_malformed_response_cannot_discard_output(self):
        def ask(body):
            response, meta = fake(0)(body)
            response['answers'].pop(next(iter(response['answers'])))
            return response, meta
        self.assertEqual(self.select(ask=ask)[0], fixture())

    def test_no_provider_or_archive_for_protected_cases(self):
        cases = [b'tiny log\n', b'\xff'*15000, b'\x00'*15000,
                 fixture()+b'Authorization: Bearer fixture-credential\n',
                 b'class Widget: pass\n'*1000, b'x'*(output.MAX_OUTPUT_BYTES+1)]
        for raw in cases:
            with self.subTest(prefix=raw[:20]):
                visible, report = self.select(raw, ask=lambda _: self.fail('provider called'))
                self.assertEqual(visible, raw)
                self.assertEqual(report['attempted_calls'], 0)
                self.assertFalse(self.out.exists())

    def test_local_mode_never_reads_keychain(self):
        with patch.object(output, 'execution_environment', side_effect=AssertionError('keychain')):
            self.assertEqual(self.select(mode='local')[0], fixture())
        self.assertFalse(self.out.exists())

    def test_missing_key_has_zero_attempts(self):
        with patch.object(output, 'execution_environment', return_value=({}, 'absent')):
            visible, report = self.select()
        self.assertEqual(visible, fixture())
        self.assertEqual(report['attempted_calls'], 0)
        self.assertEqual(report['usage_status'], 'not_called')

    def test_source_like_lines_are_kept_even_with_progress_prefix(self):
        raw = fixture() + b'progress = 12\nchecking { important: true }\n'
        visible, _ = self.select(raw, ask=fake(0))
        self.assertIn(b'progress = 12', visible)
        self.assertIn(b'checking { important: true }', visible)

    def test_cancelled_selection_makes_no_more_calls_and_keeps_original(self):
        calls = []
        def ask(body):
            calls.append(body)
            return fake(0)(body)
        raw = fixture(1200)
        visible, report = self.select(raw, ask=ask, cancelled=lambda: bool(calls), max_calls=4)
        self.assertEqual(raw, visible)
        self.assertEqual(len(calls), 1)
        self.assertEqual(report['reason'], 'cancelled')

    def test_too_much_protected_context_skips_inference(self):
        raw = fixture() + b'Important source text and facts\n'*400
        visible, report = self.select(raw, ask=lambda _: self.fail('provider called'))
        self.assertEqual(raw, visible)
        self.assertEqual(report['reason'], 'protected_context_limit')

    def test_archive_failure_prevents_provider_call(self):
        with patch.object(Path, 'open', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.select(ask=lambda _: self.fail('provider called'))

    def test_refuses_archives_inside_git(self):
        subprocess.run(['git', 'init', '-q', self.tmp.name], check=True)
        with self.assertRaises(ProtocolError):
            self.select(ask=lambda _: self.fail('provider called'))

    def test_live_credential_stays_in_parent_and_is_restored(self):
        body = {'model': output.JEV_MODEL}
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(output, 'execution_environment', return_value=({'TYPESAFE_API_KEY': 'fixture-key'}, 'keychain')), \
             patch.object(output, 'request_jev') as call:
            call.side_effect = lambda _: (os.environ['TYPESAFE_API_KEY'], {})
            self.assertEqual(output.live_request(body)[0], 'fixture-key')
            self.assertNotIn('TYPESAFE_API_KEY', os.environ)


class WrapperTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.task = self.base/'task.txt'
        self.task.write_text(TASK)

    def argv(self, *command, mode='local'):
        return [sys.executable, str(ROOT/'output.py'), '--task-file', str(self.task),
                '--out', str(self.base/'out'), '--mode', mode, '--', *command]

    def test_exit_status_stderr_stdout_and_no_jev_key_in_child(self):
        script = "import os,sys;print(os.getenv('TYPESAFE_API_KEY', 'absent'));print('diagnostic',file=sys.stderr);sys.exit(7)"
        result = subprocess.run(self.argv(sys.executable, '-c', script, mode='jev'),
            env={**os.environ, 'TYPESAFE_API_KEY': 'fixture-should-not-reach-child'}, capture_output=True)
        self.assertEqual(result.returncode, 7)
        self.assertEqual(result.stdout, b'absent\n')
        self.assertEqual(result.stderr, b'diagnostic\n')
        self.assertFalse((self.base/'out').exists())

    def test_oversized_output_switches_to_exact_passthrough(self):
        n = output.MAX_OUTPUT_BYTES + 777
        result = subprocess.run(self.argv(sys.executable, '-c', f'import sys;sys.stdout.write("x"*{n})', mode='jev'), capture_output=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b'x'*n)
        self.assertFalse((self.base/'out').exists())

    def test_invalid_options_do_not_execute_command(self):
        self.task.write_text('')
        marker = self.base/'executed'
        result = subprocess.run(self.argv(sys.executable, '-c', f'open({str(marker)!r},"w").close()'), capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(marker.exists())

    def test_signal_is_forwarded_and_command_not_restarted(self):
        marker = self.base/'started'
        script = f'import pathlib,time;pathlib.Path({str(marker)!r}).write_text("once");time.sleep(30)'
        proc = subprocess.Popen(self.argv(sys.executable, '-c', script), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 5
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertTrue(marker.exists())
            proc.send_signal(signal.SIGTERM)
            proc.communicate(timeout=5)
            self.assertEqual(proc.returncode, 143)
            self.assertEqual(marker.read_text(), 'once')
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.communicate()

    def test_skill_symlink_resolves_from_unrelated_directory(self):
        link = self.base/'skill'
        link.symlink_to(ROOT/'Codex Desktop/skills/astra-jev-coding', target_is_directory=True)
        result = subprocess.run([sys.executable, str(link/'scripts/output.py'), '--help'], cwd=self.base, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b'--keep-text', result.stdout)


if __name__ == '__main__':
    unittest.main()
