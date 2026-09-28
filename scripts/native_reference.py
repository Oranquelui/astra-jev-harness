#!/usr/bin/env python3
"""Development-only reference for the offline Go compatibility protocol."""
import ast
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shared import context_view


def execute(request):
    op = request['op']
    if op == 'imports':
        source = request['source']
        if not isinstance(source, str) or len(source.encode()) > 100000:
            raise ValueError('invalid source')
        imports = []
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imports.append({'module': getattr(node, 'module', None) or '',
                                'level': getattr(node, 'level', 0),
                                'names': sorted(alias.name for alias in node.names)})
        return sorted(imports, key=lambda item: (item['module'], item['level'], item['names']))
    if op == 'hash':
        value = json.dumps(request['value'], ensure_ascii=False, sort_keys=True,
                           separators=(',', ':'), allow_nan=False)
        return {'canonical_json': value, 'sha256': hashlib.sha256(value.encode()).hexdigest()}
    if op == 'excerpt':
        start, count = request['start_line'], request['lines']
        if type(start) is not int or start < 1 or type(count) is not int or not 1 <= count <= 200:
            raise ValueError('invalid range')
        return context_view.excerpt(request['path'], request['text'], start, count)
    if op == 'page':
        context_view.bounds(request['max_bytes'], request['offset'], 1)
        return context_view.page(request['base'], [lambda item=item: item for item in request['items']],
                                 request['offset'], request['max_bytes'])
    raise ValueError('unknown operation')


def main():
    status = 0
    for line in sys.stdin:
        try:
            value = execute(json.loads(line))
            encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
        except (ValueError, TypeError, KeyError, SyntaxError, OverflowError):
            status = 2
            encoded = '{"status":"error","error":"reference_operation_failed"}'
        print(encoded)
    return status


if __name__ == '__main__':
    raise SystemExit(main())
