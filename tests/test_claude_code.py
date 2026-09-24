"""Claude Code handoff: surface isolation, freshness, bounded reads, Skill and install."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from claude_code import context as cc
from desktop import context as dc
import install
from shared import repo_context as rc
from shared.jev import ProtocolError

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / 'Claude Code/skills/claude-jev-coding'


class ClaudeCodeContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        for args in (['init', '-q'], ['config', 'user.email', 'test@example.invalid'], ['config', 'user.name', 'Test']):
            subprocess.run(['git', '-C', str(self.repo), *args], check=True, capture_output=True)
        (self.repo / 'main.py').write_text('def value():\n    return 1\n')
        (self.repo / 'noise.py').write_text('answer = 1\n')
        subprocess.run(['git', '-C', str(self.repo), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(self.repo), 'commit', '-qm', 'fixture'], check=True)
        self.plan = self.root / 'plan'
        self.planned = cc.make_plan(self.repo, 'Update value in main.py.', self.plan)
        self.out = self.root / 'selection'

    def response(self, case):
        return {'paths': list(case['files']), 'probabilities': {p: .9 for p in case['files']},
                'fallback': None, 'usage': {'input_tokens': 10, 'output_tokens': 2}, 'model': 'fixture'}

    def test_plan_identifies_claude_code_surface(self):
        self.assertEqual(self.planned['surface'], 'claude-code')
        self.assertEqual(json.loads((self.plan / 'plan.json').read_text())['surface'], 'claude-code')
        text = (self.plan / 'PLAN.md').read_text()
        self.assertTrue(text.startswith('# Claude Code context plan'))
        self.assertIn('grants no edit', text)
        self.assertEqual(cc.load_host_plan(self.plan)['surface'], 'claude-code')

    def test_local_select_check_read_have_neutral_counters_and_no_provider(self):
        before = rc.git(self.repo, 'status', '--porcelain=v1', '-z')
        with patch.object(cc, 'execution_environment') as key, patch.object(rc, 'call_jev') as provider:
            record = cc.select(self.plan, self.out, mode='local')
            self.assertEqual(cc.check(self.out), {'status': 'fresh', 'child_generation_calls': 0, 'target_writes': 0})
            result = cc.read_context(self.out, 'main.py', 2, 2)
        key.assert_not_called()
        provider.assert_not_called()
        self.assertEqual(record['surface'], 'claude-code')
        self.assertEqual(record['route'], 'local')
        self.assertEqual(record['child_generation_calls'], 0)
        self.assertNotIn('astra_child_calls', record)
        self.assertEqual((record['attempted_calls'], record['jev_calls']), (0, []))
        self.assertEqual(sorted(record['paths']), ['main.py', 'noise.py'])
        self.assertEqual(result['text'], '    return 1\n')
        self.assertEqual(result['provider_calls'], 0)
        report = (self.out / 'REPORT.md').read_text()
        self.assertIn('# Claude Code context selected', report)
        self.assertIn('Claude Code conversation usage', report)
        self.assertNotIn('Astra', report)
        self.assertEqual(rc.git(self.repo, 'status', '--porcelain=v1', '-z'), before)

    def test_jev_select_uses_own_credentials_and_restores_parent_key(self):
        with patch.object(cc, 'execution_environment', return_value=({'TYPESAFE_API_KEY': 'fixture'}, 'environment')), \
                patch.object(rc, 'call_jev', side_effect=self.response) as jev, \
                patch.dict(os.environ, {'TYPESAFE_API_KEY': 'parent'}):
            record = cc.select(self.plan, self.out, 1, mode='jev')
            self.assertEqual(os.environ['TYPESAFE_API_KEY'], 'parent')
        self.assertEqual(jev.call_count, 1)
        self.assertEqual(record['route'], 'jev')
        self.assertEqual(record['attempted_calls'], 1)
        saved = (self.out / 'selection.json').read_text()
        self.assertNotIn('fixture', json.dumps(json.loads(saved).get('failure', {})))
        self.assertNotIn('TYPESAFE_API_KEY', saved)

    def test_missing_credential_blocks_before_output_or_provider(self):
        with patch.object(cc, 'execution_environment', return_value=({}, 'absent')), \
                patch.object(rc, 'call_jev') as jev, self.assertRaisesRegex(ProtocolError, 'credential unavailable'):
            cc.select(self.plan, self.out, 1, mode='jev')
        jev.assert_not_called()
        self.assertFalse(self.out.exists())

    def test_source_change_invalidates_handoff_and_reads(self):
        cc.select(self.plan, self.out, mode='local')
        (self.repo / 'main.py').write_text('changed\n')
        for operation in (lambda: cc.check(self.out), lambda: cc.read_context(self.out, 'main.py')):
            with self.assertRaises(ProtocolError):
                operation()
        # Historical replay still works offline but does not refresh consumption rights.
        with patch.object(rc, 'call_jev', side_effect=AssertionError('offline only')):
            self.assertEqual(cc.compare(self.out)['additional_provider_calls'], 0)
        with self.assertRaises(ProtocolError):
            cc.select(self.plan, self.root / 'stale', mode='local')

    def test_change_during_provider_call_leaves_no_usable_context(self):
        def change(case):
            (self.repo / 'main.py').write_text('concurrent change\n')
            return self.response(case)
        with patch.object(cc, 'execution_environment', return_value=({'TYPESAFE_API_KEY': 'fixture'}, 'environment')), \
                patch.object(rc, 'call_jev', side_effect=change), self.assertRaises(ProtocolError):
            cc.select(self.plan, self.out, 1)
        self.assertEqual(json.loads((self.out / 'selection.json').read_text())['status'], 'failed')
        self.assertFalse((self.out / 'context.json').exists())
        with self.assertRaises(ProtocolError):
            cc.check(self.out)

    def test_offline_compare_reports_policy_omissions(self):
        def probabilities(case):
            return {'paths': list(case['files']), 'probabilities': {'main.py': .5, 'noise.py': .01}}
        with patch.object(cc, 'execution_environment', return_value=({'TYPESAFE_API_KEY': 'fixture'}, 'environment')), \
                patch.object(rc, 'call_jev', side_effect=probabilities):
            cc.select(self.plan, self.out, 1)
        before = {p.name: p.read_bytes() for p in self.out.iterdir()}
        with patch.object(rc, 'call_jev', side_effect=AssertionError('offline only')), \
                patch.object(cc, 'execution_environment', side_effect=AssertionError('no credentials')):
            report = cc.compare(self.out, ['main.py', 'noise.py'])
        self.assertEqual(report['policies']['batch']['required_recall'], 1)
        self.assertEqual(report['policies']['per-file']['missing_required_paths'], ['noise.py'])
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.out.iterdir()})

    def test_plans_are_not_accepted_across_surfaces(self):
        desktop_plan, cli_plan = self.root / 'desktop-plan', self.root / 'cli-plan'
        dc.make_plan(self.repo, 'Update value.', desktop_plan)
        rc.snapshot(self.repo, 'Update value.', cli_plan)
        for plan in (desktop_plan, cli_plan):
            with self.subTest(plan=plan.name), patch.object(rc, 'call_jev') as jev:
                with self.assertRaises(ProtocolError):
                    cc.load_host_plan(plan)
                with self.assertRaises(ProtocolError):
                    cc.select(plan, self.root / f'{plan.name}-selection', mode='local')
                jev.assert_not_called()
        with self.assertRaises(ProtocolError):
            dc.load_desktop_plan(self.plan)
        from cli import coding
        with self.assertRaises(ProtocolError):
            coding.load_plan(self.plan)

    def test_selections_are_not_accepted_across_surfaces(self):
        desktop_plan, desktop_out = self.root / 'desktop-plan', self.root / 'desktop-selection'
        dc.make_plan(self.repo, 'Update value.', desktop_plan)
        desktop_record = dc.select(desktop_plan, desktop_out, mode='local')
        self.assertEqual((desktop_record['surface'], desktop_record['route']), ('desktop', 'astra'))
        self.assertEqual(desktop_record['astra_child_calls'], 0)
        self.assertEqual(dc.check(desktop_out)['astra_child_calls'], 0)
        cc.select(self.plan, self.out, mode='local')
        for operation in (lambda: cc.check(desktop_out), lambda: cc.read_context(desktop_out, 'main.py'),
                          lambda: cc.compare(desktop_out), lambda: dc.check(self.out),
                          lambda: dc.read_context(self.out, 'main.py'), lambda: dc.compare(self.out)):
            with self.assertRaises(ProtocolError):
                operation()

    def test_relabelled_plan_fails_the_recorded_hash(self):
        cc.select(self.plan, self.out, mode='local')
        plan = json.loads((self.plan / 'plan.json').read_text())
        plan['surface'] = 'desktop'
        (self.plan / 'plan.json').write_text(json.dumps(plan))
        for operation in (lambda: cc.check(self.out), lambda: cc.compare(self.out), lambda: dc.check(self.out)):
            with self.assertRaises(ProtocolError):
                operation()

    def test_command_line_rejects_desktop_handoff_without_leaking_content(self):
        desktop_plan = self.root / 'desktop plan'
        dc.make_plan(self.repo, 'Update value.', desktop_plan)
        result = subprocess.run([sys.executable, str(ROOT / 'Claude Code/context.py'), 'select',
                                 '--plan', str(desktop_plan), '--out', str(self.root / 'x'), '--mode', 'local'],
                                cwd=self.root, capture_output=True, text=True, env={**os.environ, 'TYPESAFE_API_KEY': 'secret-fixture'})
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, '')
        self.assertIn('Claude Code context operation failed', result.stderr)
        self.assertNotIn('secret-fixture', result.stderr)
        self.assertNotIn('return 1', result.stderr)
        self.assertFalse((self.root / 'x').exists())

    def test_symlinked_skill_launcher_runs_full_local_flow_from_spaced_paths(self):
        skills = self.root / 'user skills dir'
        self.assertEqual(install.install(skills, target='claude-code')[0], 'installed')
        launcher = skills / 'claude-jev-coding/scripts/context.py'
        task = self.root / 'task file.txt'
        task.write_text('Update value in main.py.')
        plan, out = self.root / 'plan dir', self.root / 'selection dir'
        env = {k: v for k, v in os.environ.items() if k != 'TYPESAFE_API_KEY'}

        def run(*args, **extra):
            return subprocess.run([sys.executable, str(launcher), *args], cwd=self.root,
                                  capture_output=True, text=True, env={**env, **extra})
        steps = [run('plan', '--repo', str(self.repo), '--task-file', str(task), '--out', str(plan)),
                 run('select', '--plan', str(plan), '--out', str(out), '--mode', 'local'),
                 run('check', '--selection', str(out)),
                 run('read', '--selection', str(out), '--path', 'main.py', '--start-line', '1', '--end-line', '1')]
        for step in steps:
            self.assertEqual(step.returncode, 0, step.stderr)
        self.assertEqual(json.loads(steps[1].stdout)['route'], 'local')
        self.assertEqual(json.loads(steps[1].stdout)['child_generation_calls'], 0)
        self.assertEqual(json.loads(steps[3].stdout)['text'], 'def value():\n')
        doctor = run('doctor', TYPESAFE_API_KEY='secret-fixture')
        self.assertEqual(doctor.returncode, 0, doctor.stderr)
        self.assertNotIn('secret-fixture', doctor.stdout + doctor.stderr)
        self.assertEqual(json.loads(doctor.stdout)['surface'], 'claude-code')
        self.assertEqual(Path(json.loads(doctor.stdout)['harness_root']), ROOT)


class ClaudeSkillTests(unittest.TestCase):
    def frontmatter(self):
        text = (SKILL / 'SKILL.md').read_text()
        match = re.match(r'---\n(.*?)\n---\n', text, re.S)
        self.assertIsNotNone(match)
        return dict(line.split(':', 1) for line in match.group(1).splitlines()), text

    def test_skill_is_discoverable_and_grants_nothing_extra(self):
        fields, text = self.frontmatter()
        self.assertEqual(set(fields), {'name', 'description'})
        self.assertEqual(fields['name'].strip(), 'claude-jev-coding')
        self.assertLessEqual(len(fields['description']), 1024)
        self.assertNotIn('!`', text)
        self.assertLess(len(text.splitlines()), 80)
        self.assertTrue((SKILL / 'references/workflow.md').is_file())
        self.assertFalse((SKILL / 'agents').exists())
        self.assertEqual(list(SKILL.rglob('openai.yaml')), [])

    def test_codex_desktop_skill_is_unchanged_in_name(self):
        text = (ROOT / 'Codex Desktop/skills/astra-jev-coding/SKILL.md').read_text()
        self.assertIn('name: astra-jev-coding', text)


class ClaudeInstallTests(unittest.TestCase):
    def test_default_target_and_api_remain_codex_desktop(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(install.install(tmp, True)[1], Path(tmp) / 'astra-jev-coding')
            self.assertEqual(install.install(tmp)[0], 'installed')
            self.assertFalse((Path(tmp) / 'claude-jev-coding').exists())
        with patch.dict(os.environ, {'CODEX_HOME': '/fixture/codex'}):
            self.assertEqual(install.default_skills_dir(), Path('/fixture/codex/skills'))
        with patch.object(Path, 'home', return_value=Path('/fixture/home')):
            self.assertEqual(install.default_skills_dir('claude-code'), Path('/fixture/home/.claude/skills'))
        with self.assertRaises(ValueError):
            install.install('/fixture/unused', target='unknown')

    def test_claude_check_is_read_only_and_install_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            skills = Path(tmp) / 'project/.claude/skills'
            self.assertEqual(install.install(skills, check=True, target='claude-code'),
                             ('would-install', skills / 'claude-jev-coding'))
            self.assertFalse(skills.exists())
            self.assertEqual(install.install(skills, target='claude-code')[0], 'installed')
            self.assertEqual(install.install(skills, check=True, target='claude-code')[0], 'already-installed')
            self.assertEqual(install.install(skills, target='claude-code')[0], 'already-installed')
            self.assertEqual((skills / 'claude-jev-coding').resolve(), SKILL)
            self.assertEqual([p.name for p in skills.iterdir()], ['claude-jev-coding'])

    def test_claude_target_preserves_existing_content_and_other_skills(self):
        for kind in ('directory', 'file', 'symlink', 'desktop-legacy-link'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                other = Path(tmp) / 'other-skill'
                other.mkdir()
                (other / 'SKILL.md').write_text('user skill')
                target = Path(tmp) / 'claude-jev-coding'
                if kind == 'directory':
                    target.mkdir()
                    (target / 'SKILL.md').write_text('user content')
                elif kind == 'file':
                    target.write_text('user content')
                elif kind == 'symlink':
                    target.symlink_to(Path(tmp) / 'absent')
                else:
                    target.symlink_to(install.ROOT / 'desktop/skills/astra-jev-coding', target_is_directory=True)
                before = os.readlink(target) if target.is_symlink() else None
                for check in (True, False):
                    with self.assertRaises(ValueError):
                        install.install(tmp, check=check, target='claude-code')
                self.assertEqual(os.readlink(target) if target.is_symlink() else None, before)
                if kind in ('directory', 'file'):
                    self.assertIn('user content', (target / 'SKILL.md' if kind == 'directory' else target).read_text())
                self.assertEqual((other / 'SKILL.md').read_text(), 'user skill')

    def test_both_targets_coexist_in_one_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            install.install(tmp)
            install.install(tmp, target='claude-code')
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ['astra-jev-coding', 'claude-jev-coding'])

    def test_command_line_claude_target_uses_home_and_leaves_codex_and_auth_alone(self):
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as codex, \
                tempfile.TemporaryDirectory() as cwd:
            (Path(home) / '.claude').mkdir()
            (Path(home) / '.claude/.credentials.json').write_text('fixture login data')
            env = {**os.environ, 'HOME': home, 'CODEX_HOME': codex}
            base = [sys.executable, str(install.ROOT / 'install.py'), '--target', 'claude-code']
            checked = subprocess.run([*base, '--check'], cwd=cwd, env=env, capture_output=True, text=True)
            self.assertEqual(checked.returncode, 0, checked.stderr)
            self.assertIn('would-install', checked.stdout)
            self.assertFalse((Path(home) / '.claude/skills').exists())
            for expected in ('installed', 'already-installed'):
                p = subprocess.run(base, cwd=cwd, env=env, capture_output=True, text=True)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertTrue(p.stdout.startswith(expected + ':'))
            link = Path(home) / '.claude/skills/claude-jev-coding'
            self.assertEqual(link.resolve(), SKILL)
            self.assertEqual((Path(home) / '.claude/.credentials.json').read_text(), 'fixture login data')
            self.assertEqual(list(Path(codex).iterdir()), [])
            helped = subprocess.run([sys.executable, str(link / 'scripts/context.py'), 'read', '--help'],
                                    cwd=cwd, capture_output=True, text=True)
            self.assertEqual(helped.returncode, 0, helped.stderr)
            self.assertIn('--start-line', helped.stdout)
            project = Path(cwd) / 'my project/.claude/skills'
            p = subprocess.run([*base, '--skills-dir', str(project)], cwd=cwd, env=env, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual((project / 'claude-jev-coding').resolve(), SKILL)


if __name__ == '__main__':
    unittest.main()
