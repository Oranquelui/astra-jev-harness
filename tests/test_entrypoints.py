"""Each distribution entrypoint must work without relying on the caller's cwd."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent.parent


class EntrypointTests(unittest.TestCase):
    def test_cli_and_legacy_entrypoints_from_another_directory(self):
        with tempfile.TemporaryDirectory() as cwd:
            for script, args in [('Codex cli/main.py', ['plan', '--help']),
                                 ('Codex cli/coding.py', ['plan', '--help']), ('coding.py', ['plan', '--help']),
                                 ('Codex cli/benchmark.py', ['--help']), ('harness.py', ['--help']),
                                 ('Codex Desktop/context.py', ['plan', '--help'])]:
                with self.subTest(script=script):
                    result = subprocess.run([sys.executable, str(ROOT / script), *args], cwd=cwd,
                                            text=True, capture_output=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn('usage:', result.stdout)

    def test_shared_context_can_load_without_cli_or_benchmark(self):
        result = subprocess.run([sys.executable, '-c',
            'import sys; import shared.repo_context; '
            'assert "cli.coding" not in sys.modules; '
            'assert "cli.benchmark" not in sys.modules; '
            'assert "harness" not in sys.modules'], cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
