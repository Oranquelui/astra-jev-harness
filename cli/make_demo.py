"""Create an isolated synthetic Git repository for exercising the CLI."""
import argparse
from pathlib import Path
import subprocess


def create(root):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=False)
    app = root / 'app'
    app.mkdir()
    (app / '__init__.py').write_text('')
    (root / 'AGENTS.md').write_text('Keep public function signatures. Preserve tests. Use the existing settings module. No network calls.\n')
    (app / 'settings.py').write_text('DEFAULT_PAGE_SIZE = 3\n')
    (app / 'pagination.py').write_text('from .settings import DEFAULT_PAGE_SIZE\n\ndef page_items(items, page=1, size=None):\n    size = size or DEFAULT_PAGE_SIZE\n    return items[page * size:(page + 1) * size]\n')
    domains = ['inventory', 'catalog', 'labels', 'notifications', 'sessions', 'search', 'exports', 'analytics',
               'sorting', 'filters', 'themes', 'regions', 'tags', 'discounts', 'calendar', 'locales']
    for domain in domains:
        for kind in ['summary', 'format', 'validation']:
            text = f'"""{domain} {kind} helpers. These helpers preserve already prepared values.\n'
            text += '\n'.join(f'Rule {i}: this {domain} helper operates on a complete collection, without pagination.' for i in range(8))
            text += '\n"""\n\ndef describe(values):\n    return {"count": len(values), "empty": not values}\n'
            (app / f'{domain}_{kind}.py').write_text(text)
    (root / 'test_pagination.py').write_text('''import unittest
from app.pagination import page_items

class PaginationTests(unittest.TestCase):
    def test_boundaries(self):
        items = list(range(7))
        cases = [(1, None, [0,1,2]), (2, 3, [3,4,5]), (3,3,[6]),
                 (0,3,[0,1,2]), (-1,3,[0,1,2]), (1,0,[0]), (1,-2,[0]), (8,3,[])]
        for page, size, expected in cases:
            with self.subTest(page=page, size=size):
                self.assertEqual(page_items(items, page, size), expected)
        self.assertEqual(page_items([], 1, None), [])

if __name__ == '__main__': unittest.main()
''')
    (root / '.gitignore').write_text('__pycache__/\n')
    subprocess.run(['git', 'init', '-q', str(root)], check=True)
    subprocess.run(['git', '-C', str(root), 'add', '.'], check=True)
    subprocess.run(['git', '-C', str(root), '-c', 'user.name=Harness Fixture', '-c', 'user.email=harness@example.invalid',
                    'commit', '-qm', 'Synthetic benchmark fixture'], check=True)
    print(root)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory', type=Path)
    create(p.parse_args().directory)
