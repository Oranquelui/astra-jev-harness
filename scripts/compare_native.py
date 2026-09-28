#!/usr/bin/env python3
"""Compare native primitives with v0.6.0 contracts; never call a provider.

Output contains aggregate measurements and fixture names, never source text.
Python is a development test oracle, not a dependency of astra-jev-core.
"""
import argparse
from collections import Counter
import json
import math
import os
from pathlib import Path
import platform
import random
import statistics
import struct
import subprocess
import sys
import tempfile
import time

from native_reference import execute

ROOT = Path(__file__).resolve().parents[1]


def fixtures():
    result = []
    def add(name, op, **fields):
        result.append((name, {'op': op, **fields}))
    sources = {
        'empty': '', 'simple': 'import os.path as p, sys\n',
        'relative': 'from ..pkg import (one as x, two)\nfrom . import sibling\nfrom ...root import *\n',
        'future': 'from __future__ import annotations\n',
        'comments-and-strings': '# import fake\n"""from false import imaginary"""\ns = "import pretend"\nimport real\n',
        'nested': 'try:\n    import pkg\nexcept ImportError:\n    import fallback\ndef f():\n    from .nested import value\n',
        'continued': 'import one, \\\n    two\nfrom package import (\n first, # note\n second as alias,\n)\n',
        'spaces': 'import package . module\nfrom package . module import value\n',
        'unicode': 'import K as alias\nfrom 日本 import 変数\n',
        'crlf': 'import one\r\nfrom pkg import two\r\n',
        'match': 'match obj:\n    case 1:\n        import inside\n',
        'type-parameter': 'def f[T](x: T):\n    import inside\n',
        'template-string': 'value = t"Hello {name}"\nimport after\n',
        'invalid': 'from pkg import (\n', 'python2': 'print 1\nimport after\n',
    }
    for name, source in sources.items():
        add('imports/' + name, 'imports', source=source)
    paths = set(subprocess.check_output(['git', 'ls-files', '-z', '*.py'], cwd=ROOT).decode().split('\0'))
    paths.update(('scripts/native_reference.py', 'scripts/compare_native.py'))
    for rel in sorted(paths):
        if not rel:
            continue
        source = (ROOT / rel).read_text()
        if len(source.encode()) <= 100000:
            add('tracked/' + rel, 'imports', source=source)
    values = [None, True, False, {}, [], '', '\0\b\f\n\r\t<>&日本😀\u2028\u2029',
              {'z': 1.0, 'a': [1, -0.0, 9007199254740993, 10**100, 1e-5, 1e-4, 1e15, 1e16]},
              {'😀': 1, '\uffff': 2, '日本': {'nested': [0, 1.0]}},
              {'model': 'jev-1.13.0', 'state': {'task': '修正', 'files': {'a.py': 'import b\n'}},
               'questions': {'f0': {'type': 'noul', 'instructions': 'Is the file relevant?'}}}]
    rng = random.Random(60728)
    for _ in range(1000):
        number = struct.unpack('!d', rng.randbytes(8))[0]
        if math.isfinite(number):
            values.append(number)
    for n, value in enumerate(values):
        add(f'hash/{n}', 'hash', value=value)
    texts = ['', 'one', 'one\n', 'a\r\nb\rc\nd', '日本\u2028😀\u2029last',
             'a\vb\fc\x1cd\x1de\x1ef\u0085g', '日' * 2000 + '\nnext\n']
    for n, text in enumerate(texts):
        for start in (1, 2, 100):
            for count in (1, 2, 200):
                add(f'excerpt/{n}/{start}/{count}', 'excerpt', path='日本.py', text=text,
                    start_line=start, lines=count)
    items = [execute({'op': 'excerpt', 'path': f'{n}.py', 'text': text,
                      'start_line': 1, 'lines': 200}) for n, text in enumerate(texts)]
    for limit in (1024, 2048, 8192, 24000):
        for offset in range(len(items) + 1):
            add(f'page/{limit}/{offset}', 'page', base={'status': 'test'}, items=items,
                offset=offset, max_bytes=limit)
    add('page/metadata-overflow', 'page', base={'metadata': 'x' * 2000}, items=[], offset=0, max_bytes=1024)
    add('page/offset-rejected', 'page', base={}, items=[], offset=1, max_bytes=1024)
    add('page/bool-rejected', 'page', base={}, items=[], offset=False, max_bytes=1024)
    return result


def run(command, data, env=None):
    start = time.perf_counter_ns()
    proc = subprocess.run(command, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          env=env, timeout=120)
    elapsed = (time.perf_counter_ns() - start) / 1e6
    if proc.returncode not in (0, 2):
        raise RuntimeError('compatibility executable failed')
    return proc, elapsed


def summary(samples):
    return {'samples': len(samples), 'median_ms': round(statistics.median(samples), 3),
            'p95_ms': round(sorted(samples)[math.ceil(.95 * len(samples)) - 1], 3)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--samples', type=int, default=0,
                        help='Optional local timing repetitions (3..101); default 0 runs correctness only')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.samples != 0 and not 3 <= args.samples <= 101:
        parser.error('Use 0 (correctness only) or 3..101 timing samples')
    binary = args.binary.resolve()
    cases = fixtures()
    encode = lambda rows: ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows).encode()
    data = encode([request for _, request in cases])
    commands = {'python': [sys.executable, str(ROOT / 'scripts/native_reference.py')], 'go': [str(binary)]}
    # The executable receives no PATH, HOME, credentials, proxy or provider setup.
    with tempfile.TemporaryDirectory() as empty:
        native_env = {'PATH': empty}
        python, _ = run(commands['python'], data)
        native, _ = run(commands['go'], data, native_env)
        left, right = [json.loads(line) for line in python.stdout.splitlines()], [json.loads(line) for line in native.stdout.splitlines()]
        if len(left) != len(cases) or len(right) != len(cases):
            raise RuntimeError('wrong result count')
        mismatches = []
        errors = 0
        for (name, _), a, b in zip(cases, left, right):
            a_error = isinstance(a, dict) and a.get('status') == 'error'
            b_error = isinstance(b, dict) and b.get('status') == 'error'
            if a_error and b_error:
                errors += 1
            elif a != b:
                mismatches.append({'fixture': name, 'python_error': a_error, 'go_error': b_error})
        timings = {}
        # A complete matched batch includes startup, parsing and serialization.
        # Each individual timing check also validates its output against the first run.
        jobs = {'startup_hash': encode([{'op': 'hash', 'value': {'check': 1}}]),
                'matched_batch': data}
        for job, payload in (jobs.items() if args.samples else []):
            samples = {'python': [], 'go': []}
            references = {name: run(command, payload, native_env if name == 'go' else None)[0].stdout
                          for name, command in commands.items()}
            for n in range(args.samples):
                for name in (('python', 'go') if n % 2 == 0 else ('go', 'python')):
                    proc, ms = run(commands[name], payload, native_env if name == 'go' else None)
                    if proc.stdout != references[name]:
                        raise RuntimeError('nondeterministic measurement output')
                    samples[name].append(ms)
            timings[job] = {name: summary(values) for name, values in samples.items()}
        result = {'scope': 'offline_native_core_compatibility_not_full_runtime',
                  'source_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip(),
                  'python_version': platform.python_version(), 'platform': platform.platform(),
                  'architecture': platform.machine(), 'binary_bytes': binary.stat().st_size,
                  'fixtures': len(cases), 'fixture_groups': dict(Counter(name.split('/')[0] for name, _ in cases)),
                  'matched': len(cases) - len(mismatches), 'both_rejected': errors,
                  'mismatches': mismatches, 'empty_path_native_run': True,
                  'provider_attempts': 0, 'provider_tokens': 0,
                  'end_to_end_coding_accuracy_cost_speed': 'not_measured',
                  'ready_for_runtime_cutover': False, 'timings': timings}
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if mismatches else 0


if __name__ == '__main__':
    raise SystemExit(main())
