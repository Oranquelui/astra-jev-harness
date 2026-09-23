"""Installation must be reversible and must preserve other skills and user credentials."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import install


class InstallTests(unittest.TestCase):
    def test_check_does_not_create_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'missing/skills'
            self.assertEqual(install.install(target, check=True)[0], 'would-install')
            self.assertFalse(target.exists())

    def test_install_is_idempotent_and_resolves_complete_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(install.install(tmp)[0], 'installed')
            self.assertEqual(install.install(tmp)[0], 'already-installed')
            link = Path(tmp) / 'astra-jev-coding'
            self.assertEqual(link.resolve(), install.ROOT / 'desktop/skills/astra-jev-coding')
            p = subprocess.run([sys.executable, str(link / 'scripts/context.py'), '--help'],
                               cwd=tmp, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn('compare', p.stdout)

    def test_does_not_overwrite_a_directory_file_or_broken_link(self):
        for kind in ('directory', 'file', 'symlink'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                target = Path(tmp) / 'astra-jev-coding'
                if kind == 'directory': target.mkdir()
                elif kind == 'file': target.write_text('user content')
                else: target.symlink_to(Path(tmp) / 'absent')
                with self.assertRaises(ValueError): install.install(tmp)
                self.assertTrue(target.exists() or target.is_symlink())

    def test_respects_codex_home_without_reading_or_copying_auth(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / 'auth.json').write_text('fixture login data')
            p = subprocess.run([sys.executable, str(install.ROOT / 'install.py')],
                               env={**os.environ, 'CODEX_HOME': tmp}, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual((home / 'auth.json').read_text(), 'fixture login data')
            self.assertTrue((home / 'skills/astra-jev-coding').is_symlink())


if __name__ == '__main__':
    unittest.main()
