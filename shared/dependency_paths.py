"""Resolve local module candidates without importing or executing project code."""
import json
from pathlib import PurePosixPath
import posixpath
import re


def jsonc(text):
    # Preserve quoted strings, including URLs and escaped quotes.
    text = re.sub(r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*[\s\S]*?\*/',
                  lambda m: m[0] if m[0].startswith('"') else ' ', text)
    text = re.sub(r'"(?:\\.|[^"\\])*"|,\s*(?=[}\]])',
                  lambda m: m[0] if m[0].startswith('"') else '', text)
    return json.loads(text)


def normalized(base, path):
    value = posixpath.normpath(posixpath.join(base, path))
    return None if value.startswith(('../', '/')) or value == '..' else value


def ts_options(files, config, seen=()):
    if config in seen:
        raise ValueError('cyclic tsconfig')
    obj = jsonc(files[config])
    base = str(PurePosixPath(config).parent)
    result = {}
    parent = obj.get('extends')
    if parent:
        if not isinstance(parent, str) or not parent.startswith('.'):
            raise ValueError('unresolved tsconfig extends')
        parent = normalized(base, parent)
        if parent and parent not in files:
            parent += '.json'
        if parent not in files:
            raise ValueError('missing tsconfig extends')
        result = ts_options(files, parent, (*seen, config))
    options = obj.get('compilerOptions', {})
    if 'baseUrl' in options:
        result['base'] = normalized(base, options['baseUrl'])
    if 'paths' in options:
        # Keep declaration-relative paths when inherited by another config.
        anchor = result.get('base') or base
        result['paths'] = {key: [normalized(anchor, p) for p in values]
                           for key, values in options['paths'].items()}
    return result


def local_candidates(files, path, specifier, python=False):
    if python:
        roots = {'.'}
        for name in files:
            parts = PurePosixPath(name).parts
            if 'src' in parts:
                roots.add('/'.join(parts[:parts.index('src') + 1]))
        return [posixpath.join(root, specifier) for root in sorted(roots)]
    parent = PurePosixPath(path).parent
    if specifier.startswith('.'):
        return [normalized(str(parent), specifier)]
    configs = [str(p / 'tsconfig.json') for p in (parent, *parent.parents)]
    config = next((p for p in configs if p in files), None)
    candidates = []
    if config:
        try:
            options = ts_options(files, config)
            for pattern, targets in options.get('paths', {}).items():
                before, star, after = pattern.partition('*')
                if (specifier == pattern if not star else
                        specifier.startswith(before) and specifier.endswith(after)
                        and len(specifier) >= len(before) + len(after)):
                    middle = specifier[len(before):len(specifier)-len(after) if after else None]
                    candidates.extend(t.replace('*', middle) if star else t for t in targets if t)
            if options.get('base'):
                candidates.append(normalized(options['base'], specifier))
        except (ValueError, TypeError, KeyError, AttributeError):
            # Unknown config: retain local scope rather than silently trust omission.
            scope = str(PurePosixPath(config).parent)
            candidates.extend(p for p in files if scope == '.' or p.startswith(scope + '/'))
    for name, source in files.items():
        if PurePosixPath(name).name != 'package.json':
            continue
        try:
            package = json.loads(source).get('name')
        except (ValueError, AttributeError):
            continue
        if package and (specifier == package or specifier.startswith(package + '/')):
            scope = str(PurePosixPath(name).parent)
            # Workspace exports may be conditional; keep the whole local package.
            candidates.extend(p for p in files if scope == '.' or p.startswith(scope + '/'))
    return candidates


def variants(stem):
    if not stem:
        return []
    stem = posixpath.normpath(stem)
    stems = [stem]
    if stem.endswith(('.js', '.mjs', '.cjs')):
        stems.append(stem.rsplit('.', 1)[0])
    suffixes = ('', '.py', '/__init__.py', '.ts', '.tsx', '.js', '.jsx', '.mts', '.cts',
                '.mjs', '.cjs', '/index.ts', '/index.tsx', '/index.js', '/index.mts')
    return [s + ext for s in stems for ext in suffixes]
