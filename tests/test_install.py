"""Installation must be reversible and must preserve other skills and user credentials."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
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
            self.assertEqual(link.resolve(), install.ROOT / 'Codex Desktop/skills/astra-jev-coding')
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

    def test_migrates_only_this_clones_legacy_link_and_check_is_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            link = Path(tmp) / 'astra-jev-coding'
            legacy = install.ROOT / 'desktop/skills/astra-jev-coding'
            link.symlink_to(legacy, target_is_directory=True)
            self.assertEqual(install.install(tmp, check=True)[0], 'would-update')
            self.assertEqual(link.readlink(), legacy)
            self.assertEqual(install.install(tmp)[0], 'updated')
            self.assertEqual(link.resolve(), install.ROOT / 'Codex Desktop/skills/astra-jev-coding')
            self.assertEqual(install.install(tmp)[0], 'already-installed')

    def test_failed_migration_preserves_the_original_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            link = Path(tmp) / 'astra-jev-coding'
            legacy = install.ROOT / 'desktop/skills/astra-jev-coding'
            link.symlink_to(legacy, target_is_directory=True)
            with patch.object(Path, 'replace', side_effect=OSError('fixture failure')):
                with self.assertRaises(OSError):
                    install.install(tmp)
            self.assertEqual(link.readlink(), legacy)
            self.assertEqual(list(Path(tmp).iterdir()), [link])

    def test_does_not_replace_a_link_to_existing_legacy_skill_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = (Path(tmp) / 'checkout').resolve()
            new = root / 'Codex Desktop/skills/astra-jev-coding'
            new.mkdir(parents=True)
            (new / 'SKILL.md').write_text('new fixture')
            legacy = root / 'desktop/skills/astra-jev-coding'
            legacy.mkdir(parents=True)
            (legacy / 'SKILL.md').write_text('user content')
            link = Path(tmp) / 'astra-jev-coding'
            link.symlink_to(legacy, target_is_directory=True)
            with patch.object(install, 'ROOT', root), self.assertRaises(ValueError):
                install.install(tmp)
            self.assertEqual(link.resolve(), legacy)
            self.assertEqual((legacy / 'SKILL.md').read_text(), 'user content')

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
