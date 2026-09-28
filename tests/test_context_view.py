"""Bounded, source-first views never turn unexplored files into omissions."""
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch

from desktop import context as desktop
from shared import repo_context as rc
from shared import host_context as hc
from shared import context_view as view


class ContextViewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        for args in [('init', '-q'), ('config', 'user.name', 'Fixture'),
                     ('config', 'user.email', 'fixture@example.invalid')]:
            rc.git(self.repo, *args)
        sources = {'AGENTS.md': 'Preserve behavior.\n',
                   'src/main.py': 'def checkout():\n    return 1\n',
                   'other/hidden.py': '# obscure implementation\n' + 'value = 1\n' * 2000,
                   'second/hidden.py': '# independent branch\n' + 'value = 2\n' * 2000,
                   '.env': 'SECRET=fixture\n'}
        for name, text in sources.items():
            p = self.repo / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
        rc.git(self.repo, 'add', '.')
        rc.git(self.repo, 'commit', '-qm', 'fixture')
        self.plan = self.root / 'plan'
        desktop.make_plan(self.repo, 'Fix checkout', self.plan,
                          focus_paths=['src/main.py'], scope_max_calls=1)
        self.selection = self.root / 'selected'
        with patch.object(rc, 'call_jev', return_value={'probabilities': {'src/main.py': .95}}), \
             patch.object(desktop, 'execution_environment', return_value=({'TYPESAFE_API_KEY': 'fixture'}, 'fixture')):
            desktop.select(self.plan, self.selection, 1, require_jev=True)

    def present(self, **options):
        return hc.present(desktop, self.selection, **options)

    def discover(self, **options):
        return hc.discover(desktop, self.plan, **options)

    def test_presentation_is_bounded_verbatim_and_does_not_mutate_retention(self):
        before = (self.selection / 'context.json').read_bytes()
        with patch.object(rc, 'call_jev', side_effect=AssertionError('No API')):
            r = self.present(max_bytes=1800, lines_per_file=1)
        self.assertLessEqual(len(json.dumps(r, ensure_ascii=False).encode()) + 1, 1800)
        for item in r['items']:
            lines = (self.repo / item['path']).read_text().splitlines(keepends=True)
            self.assertEqual(item['text'], ''.join(lines[item['start_line']-1:item['end_line']]))
            self.assertEqual(item['source_sha256'], rc.digest((self.repo / item['path']).read_bytes()))
        main = next(i for i in r['items'] if i['path'] == 'src/main.py')
        self.assertEqual(main['unpresented_ranges'], [[2, 2]])
        self.assertEqual(before, (self.selection / 'context.json').read_bytes())
        self.assertEqual(r['provider_calls'], 0)
        self.assertGreater(r['scoped_out_files'], 0)

    def test_discovery_keeps_multiple_branches_and_returns_unjudged_previews(self):
        before = (self.plan / 'plan.json').read_bytes()
        tree = self.discover()
        self.assertEqual({i['directory'] for i in tree['items']}, {'other', 'second'})
        self.assertNotIn('.env', json.dumps(tree))
        for branch in tree['items']:
            r = self.discover(directory=branch['directory'], max_bytes=1500)
            self.assertLessEqual(len(json.dumps(r, ensure_ascii=False).encode()) + 1, 1500)
            item = r['items'][0]
            self.assertEqual(item['judgment'], 'unjudged')
            self.assertTrue((self.repo / item['path']).read_text().startswith(item['text']))
        self.assertEqual(before, (self.plan / 'plan.json').read_bytes())

    def test_discovered_file_can_be_focused_without_losing_existing_focus(self):
        r = self.discover(directory='other')
        required = r['items'][0]['path']
        next_dir = self.root / 'next'
        p = desktop.make_plan(self.repo, 'Fix checkout', next_dir,
            focus_paths=['src/main.py', required], scope_max_calls=2)
        self.assertIn(required, p['files'])
        self.assertIn('src/main.py', p['focus_paths'])
        with patch.object(rc, 'call_jev', side_effect=lambda case: {
                 'probabilities': {key: .5 for key in case['files']}}), \
             patch.object(desktop, 'execution_environment', return_value=({'TYPESAFE_API_KEY': 'fixture'}, 'fixture')):
            desktop.select(next_dir, self.root / 'next-selected', 2, require_jev=True)
        self.assertEqual(desktop.check(self.root / 'next-selected')['status'], 'fresh')

    def test_stale_plan_tampered_context_wrong_surface_and_local_guard(self):
        from claude_code import context as claude
        with self.assertRaises(rc.ProtocolError):
            hc.discover(claude, self.plan)
        with self.assertRaises(rc.ProtocolError):
            hc.present(claude, self.selection)
        local = self.root / 'local'
        desktop.select(self.plan, local, 1, mode='local')
        with self.assertRaises(hc.JevRequiredError):
            hc.present(desktop, local, require_jev=True)
        (self.repo / 'other/hidden.py').write_text('changed\n')
        for action in (self.present, self.discover):
            with self.assertRaises(rc.ProtocolError):
                action()

    def test_invalid_bounds_and_directory_do_not_escape(self):
        for opts in ({'max_bytes': 1}, {'max_bytes': 25000}, {'offset': -1}, {'lines_per_file': 201}):
            with self.subTest(opts=opts), self.assertRaises(rc.ProtocolError):
                self.present(**opts)
        with self.assertRaises(rc.ProtocolError):
            self.discover(directory='../outside')

    def test_cli_presentation_guard_and_discovery(self):
        entry = Path(desktop.__file__)
        result = subprocess.run([sys.executable, str(entry), 'present', '--selection',
            str(self.selection), '--max-bytes', '1600'], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLessEqual(len(result.stdout), 1600)
        self.assertEqual(json.loads(result.stdout)['status'], 'presentation')
        result = subprocess.run([sys.executable, str(entry), 'discover', '--plan',
            str(self.plan)], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['judgment'], 'unjudged')

    def test_tampered_or_failed_handoff_cannot_be_presented(self):
        context = self.selection / 'context.json'
        context.write_text('{}')
        with self.assertRaises(rc.ProtocolError):
            self.present()
        record_path = self.selection / 'selection.json'
        record = json.loads(record_path.read_text())
        record['status'] = 'failed'
        record_path.write_text(json.dumps(record))
        with self.assertRaises(rc.ProtocolError):
            self.present()


class PureViewTests(unittest.TestCase):
    def test_paging_covers_all_leads_without_exceeding_unicode_budget(self):
        text = '日本語 source\r\n' * 40
        candidates = [lambda n=n: view.excerpt(f'{n}.py', text, 3, 8) for n in range(15)]
        offset, seen = 0, []
        while offset is not None:
            r = view.page({'status': 'fixture'}, candidates, offset, 1024)
            self.assertLessEqual(view.output_size(r), 1024)
            self.assertTrue(r['items'])
            seen.extend(i['path'] for i in r['items'])
            for item in r['items']:
                self.assertEqual(item['text'], ''.join(text.splitlines(keepends=True)[item['start_line']-1:item['end_line']]))
            offset = r['next_offset']
        self.assertEqual(seen, [f'{n}.py' for n in range(15)])

    def test_oversized_line_is_a_reading_lead_not_silently_truncated(self):
        text = 'あ' * 10000 + '\n'
        r = view.page({}, [lambda: view.excerpt('long.py', text, 1, 1)], 0, 1024)
        item = r['items'][0]
        self.assertEqual(item['text'], '')
        self.assertEqual(item['unpresented_ranges'], [[1, 1]])
        self.assertIn('exceeds_output_budget', item['reason'])
        self.assertLessEqual(view.output_size(r), 1024)

    def test_saved_range_guides_source_first_excerpt_without_changing_retention(self):
        text = 'header\nnoise\nneeded\nlast\n'
        record = {'paths': ['impl.py'], 'fragment_decisions': {
            'first': {'path': 'impl.py', 'start_line': 1, 'probability': .1},
            'last': {'path': 'impl.py', 'start_line': 3, 'probability': .9}}}
        r = view.presentation({}, record, {'files': {'impl.py': text}}, 1500, 0, 1)
        self.assertEqual(r['items'][0]['text'], 'needed\n')
        self.assertEqual(r['items'][0]['unpresented_ranges'], [[1, 2], [4, 4]])
        self.assertEqual(r['retained_source_bytes'], len(text.encode()))


if __name__ == '__main__':
    unittest.main()
