"""Separate entrypoints share private credential loading."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


LAUNCHER = Path(__file__).parent / 'desktop/skills/astra-jev-coding/scripts/context.py'


class SkillLauncherTests(unittest.TestCase):
    def load_launcher(self):
        from shared import credentials
        return credentials

    def test_existing_environment_key_takes_precedence(self):
        launcher = self.load_launcher()
        with patch.dict(os.environ, {'TYPESAFE_API_KEY': 'fixture-environment'}), \
                patch.object(launcher.subprocess, 'run', side_effect=AssertionError('must not read Keychain')):
            env, source = launcher.execution_environment()
        self.assertEqual(source, 'environment')
        self.assertEqual(env['TYPESAFE_API_KEY'], 'fixture-environment')

    def test_keychain_value_is_passed_in_memory_without_mutating_parent_environment(self):
        launcher = self.load_launcher()
        with patch.dict(os.environ, {}, clear=True), patch.object(launcher.sys, 'platform', 'darwin'), \
                patch.object(launcher.subprocess, 'run', return_value=subprocess.CompletedProcess(
                    [], 0, stdout='fixture-keychain\n', stderr='')):
            env, source = launcher.execution_environment()
            self.assertNotIn('TYPESAFE_API_KEY', os.environ)
        self.assertEqual(source, 'keychain')
        self.assertEqual(env['TYPESAFE_API_KEY'], 'fixture-keychain')

    def test_missing_keychain_does_not_fabricate_a_key(self):
        launcher = self.load_launcher()
        with patch.dict(os.environ, {}, clear=True), patch.object(launcher.sys, 'platform', 'darwin'), \
                patch.object(launcher.subprocess, 'run', return_value=subprocess.CompletedProcess(
                    [], 44, stdout='', stderr='unavailable')):
            env, source = launcher.execution_environment()
        self.assertEqual(source, 'absent')
        self.assertNotIn('TYPESAFE_API_KEY', env)

    def test_help_through_installed_style_symlink_from_other_cwd(self):
        with tempfile.TemporaryDirectory() as tmp:
            link = Path(tmp) / 'skill'
            link.symlink_to(LAUNCHER.resolve().parents[1], target_is_directory=True)
            p = subprocess.run([sys.executable, str(link / 'scripts/context.py'), 'plan', '--help'],
                               cwd=tmp, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('--task-file', p.stdout)
        self.assertNotIn('--allow-create', p.stdout)

    def test_keychain_timeout_is_distinct_from_missing_credential(self):
        launcher = self.load_launcher()
        with patch.dict(os.environ, {}, clear=True), patch.object(launcher.sys, 'platform', 'darwin'), \
                patch.object(launcher.subprocess, 'run', side_effect=subprocess.TimeoutExpired('security', 60)):
            env, source = launcher.execution_environment()
        self.assertEqual(source, 'keychain_timeout')
        self.assertNotIn('TYPESAFE_API_KEY', env)

    def test_explicit_astra_mode_does_not_read_keychain(self):
        from cli import main as launcher
        for mode in (['--mode', 'astra'], ['--mode=astra']):
            with self.subTest(mode=mode), patch.object(sys, 'argv', [str(LAUNCHER), 'run', *mode]), \
                    patch.object(launcher, 'execution_environment', side_effect=AssertionError('must not unlock')), \
                    patch.object(launcher.os, 'execve') as execute:
                launcher.main()
            self.assertEqual(execute.call_args.args[1][-len(mode):], mode)


if __name__ == '__main__':
    unittest.main()
