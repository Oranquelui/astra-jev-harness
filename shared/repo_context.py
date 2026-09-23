"""Local repository snapshots and conservative context selection."""
import ast
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import subprocess

from shared.jev import (ProtocolError, call_jev, jev_request, read_cache, write_cache, request_jev, select_context, request_hash)
from shared.dependency_paths import local_candidates, variants

EXTENSIONS = {'.py', '.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs', '.mts', '.cts', '.json', '.jsonc', '.toml', '.yaml', '.yml', '.md', '.txt', '.css', '.html', '.sql'}
EXCLUDED_DIRS = {'.git', '.venv', 'venv', 'node_modules', 'dist', 'build', '.next', '__pycache__'}
SECRET = re.compile(r'apikey_[a-zA-Z0-9_]{40,}|sk-(?:proj-)?[a-zA-Z0-9_-]{25,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|(?:api_key|password|secret|token)\s*[:=]\s*[\"\'][^\"\'\n]{24,}[\"\']', re.I)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def git(repo, *args):
    p = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, timeout=15)
    if p.returncode:
        raise ProtocolError('Git query failed: ' + args[0])
    return p.stdout


def safe_path(root, rel):
    if not isinstance(rel, str) or not rel or '\\' in rel:
        raise ProtocolError('Invalid relative path')
    parts = PurePosixPath(rel).parts
    if PurePosixPath(rel).is_absolute() or '..' in parts or str(PurePosixPath(rel)) != rel or rel == '.' or any(c in rel for c in '\x00\n\r'):
        raise ProtocolError('Path escape refused')
    p = root
    for part in parts:
        p = p / part
        if p.is_symlink():
            raise ProtocolError('Symlink path refused')
    if not p.resolve().is_relative_to(root.resolve()):
        raise ProtocolError('Path escape refused')
    return p


def eligibility(rel):
    p = PurePosixPath(rel.lower())
    if any(x in EXCLUDED_DIRS for x in p.parts) or p.parts[0] in {'data', 'uploads'}:
        return 'generated_or_data_directory'
    if p.name.startswith('.env') or p.suffix.lower() in {'.pem', '.key', '.p12', '.sqlite', '.db'} or p.name in {'auth.json', 'credentials.json', 'secrets.json'}:
        return 'credential_or_database_file'
    if p.name.endswith(('-lock.json', '-lock.yaml')) or p.name in {'yarn.lock', 'uv.lock', 'poetry.lock'}:
        return 'lockfile'
    if p.suffix.lower() not in EXTENSIONS:
        return 'unsupported_file_type'
    return None


def is_instruction(path):
    p = PurePosixPath(path.lower())
    return p.name == 'agents.md' or 'policies' in p.parts


def is_test(path):
    p = PurePosixPath(path)
    return any(x in p.parts for x in ('test', 'tests', '__tests__')) or p.name == 'conftest.py' or p.name.startswith('test_') or p.name.endswith('_test.py') or '.test.' in p.name or '.spec.' in p.name


def validate_change_scope(plan):
    """Validate explicit grants, path conflicts, and protected targets."""
    creates, tests = plan.get('create_paths', []), plan.get('test_edit_paths', [])
    for paths in (creates, tests):
        if not isinstance(paths, list) or any(not isinstance(p, str) for p in paths):
            raise ProtocolError('Change permissions must be lists of relative paths')
        if len(set(p.casefold() for p in paths)) != len(paths):
            raise ProtocolError('Duplicate or case-aliased change paths')
        for p in paths:
            safe_path(Path(plan['repo']), p)
            if eligibility(p.lower()) or is_instruction(p):
                raise ProtocolError('Protected or ineligible change path: ' + p)
    if len(plan['files']) + len(creates) > 1500:
        raise ProtocolError('Planned files exceed 1500 file limit')
    occupied = list(plan['files']) + list(plan.get('excluded', {}))
    for p in creates:
        folded = p.casefold()
        for other in occupied + creates:
            if other == p and other in creates and other not in occupied:
                continue
            other_folded = other.casefold()
            if folded == other_folded or folded.startswith(other_folded + '/') or other_folded.startswith(folded + '/'):
                raise ProtocolError('Creation path conflicts with another planned or tracked path: ' + p)
    for p in tests:
        if p not in plan['files'] or not is_test(p):
            raise ProtocolError('Test edit must name an existing included test: ' + p)


def check_creation_destinations(plan):
    """Refuse occupied targets, symlinks, and non-directory parents, including ignored files."""
    repo = Path(plan['repo'])
    for p in plan.get('create_paths', []):
        target = safe_path(repo, p)
        if target.exists():
            raise ProtocolError('Creation destination already exists: ' + p)
        for parent in target.parents:
            if parent == repo:
                break
            if parent.exists() and not parent.is_dir():
                raise ProtocolError('Creation parent is not a directory: ' + p)


def editable_paths(plan, paths):
    return sorted({p for p in paths if not is_instruction(p) and
                   (not is_test(p) or p in plan.get('test_edit_paths', []))} | set(plan.get('create_paths', [])))


def snapshot(repo, task, out, create_paths=None, test_edit_paths=None, include_paths=None):
    repo = Path(repo).resolve()
    if Path(git(repo, 'rev-parse', '--show-toplevel').decode().strip()).resolve() != repo:
        raise ProtocolError('Pass the exact Git repository root')
    out = Path(out).resolve()
    if out.is_relative_to(repo):
        raise ProtocolError('Store the plan outside the source repository')
    if out.exists():
        raise ProtocolError('Plan output already exists; choose a new directory')
    if not task.strip() or len(task.encode()) > 4000 or SECRET.search(task):
        raise ProtocolError('Task is empty, oversized, or contains a credential-like value')
    before = git(repo, 'status', '--porcelain=v1', '-z')
    files, excluded = {}, {}
    included = include_paths or []
    if not isinstance(included, list) or any(not isinstance(p, str) for p in included):
        raise ProtocolError('Explicit includes must be relative paths')
    for name in included:
        safe_path(repo, name)
        if eligibility(name) or not safe_path(repo, name).is_file():
            raise ProtocolError('Explicit include is protected, missing, or unsupported')
        ignored = subprocess.run(['git', '-C', str(repo), 'check-ignore', '--quiet', '--', name], capture_output=True)
        if ignored.returncode != 1:
            raise ProtocolError('Explicit include is ignored or cannot be checked')
    tracked = [r for r in git(repo, 'ls-files', '-z').split(b'\0') if r]
    for raw in sorted(set(tracked + [p.encode() for p in included])):
        if not raw:
            continue
        rel = raw.decode('utf-8')
        why = eligibility(rel)
        if why:
            excluded[rel] = why
            continue
        try:
            path = safe_path(repo, rel)
            if not path.is_file() or path.stat().st_size > 100000:
                excluded[rel] = 'missing_or_over_100KB'
                continue
            raw = path.read_bytes()
            source = raw.decode('utf-8')
            if '\0' in source or SECRET.search(source):
                excluded[rel] = 'binary_or_credential_pattern'
                continue
            files[rel] = {'sha256': digest(raw), 'bytes': len(raw), 'mode': path.stat().st_mode & 0o777,
                          'content': source}
        except (ProtocolError, UnicodeError):
            excluded[rel] = 'symlink_or_non_utf8'
    if any(p not in files for p in included):
        raise ProtocolError('Explicit include failed content eligibility checks')
    if not files or sum(f['bytes'] for f in files.values()) > 2000000 or len(files) > 1500:
        raise ProtocolError('Snapshot empty or exceeds v0.1 bounds: 2MB / 1500 files')
    if git(repo, 'status', '--porcelain=v1', '-z') != before:
        raise ProtocolError('Repository status changed during snapshot; try again')
    for rel, record in files.items():
        if digest(safe_path(repo, rel).read_bytes()) != record['sha256']:
            raise ProtocolError('Repository content changed during snapshot; try again')
    manifest = {'version': 1, 'repo': str(repo), 'head': git(repo, 'rev-parse', 'HEAD').decode().strip(),
                'branch': git(repo, 'branch', '--show-current').decode().strip(),
                'status_sha256': digest(before), 'task': task, 'files': files, 'excluded': excluded,
                'explicit_includes': included}
    if create_paths or test_edit_paths:
        manifest.update(version=2, create_paths=create_paths or [], test_edit_paths=test_edit_paths or [])
    validate_change_scope(manifest)
    check_creation_destinations(manifest)
    out.mkdir(parents=True)
    (out / 'plan.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    lines = ['# Repository plan', '', f"Repository: {repo}", f"HEAD: {manifest['head']}",
             f"Included: {len(files)} files / {sum(f['bytes'] for f in files.values())} bytes",
             f"Excluded: {len(excluded)} files. No API calls or repository writes have occurred.", '',
             '## Task', task, '', '## Permitted new files', *['- ' + p for p in manifest.get('create_paths', [])],
             '', '## Permitted existing test edits', *['- ' + p for p in manifest.get('test_edit_paths', [])],
             '', 'Existing source files remain editable; other tests and instructions are read-only.',
             'Review existing regression tests and task acceptance checks separately from generated tests.',
             '', '## Files potentially sent when running', *['- ' + p for p in files],
             '', '## Excluded', *[f'- {p}: {reason}' for p, reason in excluded.items()]]
    (out / 'PLAN.md').write_text('\n'.join(lines) + '\n')
    return manifest


def load_plan(path):
    plan = json.loads((Path(path) / 'plan.json').read_text())
    if plan.get('version') not in (1, 2):
        raise ProtocolError('Unsupported plan version')
    if plan['version'] == 1 and (plan.get('create_paths') or plan.get('test_edit_paths')):
        raise ProtocolError('Explicit change permissions require plan version 2')
    for rel, r in plan['files'].items():
        safe_path(Path(path), rel)
        if digest(r['content'].encode()) != r['sha256'] or eligibility(rel) or SECRET.search(r['content']):
            raise ProtocolError('Plan file integrity or eligibility check failed')
    validate_change_scope(plan)
    return plan


def dependencies(files, selected):
    """Follow resolvable Python and relative JS imports; preserve configs/instructions."""
    keep = set(selected)
    config = {'package.json', 'tsconfig.json', 'pyproject.toml', 'requirements.txt', 'pytest.ini', 'setup.cfg', 'conftest.py'}
    keep.update(p for p in files if is_instruction(p) or PurePosixPath(p).name in config
                or (PurePosixPath(p).name.startswith('tsconfig') and p.endswith('.json')))
    queue = list(keep)
    while queue:
        path = queue.pop()
        if path.endswith('.py'):
            for parent in PurePosixPath(path).parents:
                init = str(parent / '__init__.py')
                if init in files and init not in keep:
                    keep.add(init)
                    queue.append(init)
        source = files[path]
        imports = []
        if path.endswith('.py'):
            try:
                for node in ast.walk(ast.parse(source)):
                    if isinstance(node, ast.Import):
                        imports.extend(stem for x in node.names for stem in local_candidates(files, path, x.name.replace('.', '/'), python=True))
                    elif isinstance(node, ast.ImportFrom):
                        base = PurePosixPath(path).parent
                        for _ in range(max(0, node.level - 1)):
                            base = base.parent
                        module = (node.module or '').replace('.', '/')
                        stem = str(base / module) if node.level else module
                        bases = [stem] if node.level else local_candidates(files, path, stem, python=True)
                        imports.extend(bases)
                        imports.extend(str(PurePosixPath(b) / x.name) for b in bases for x in node.names)
            except SyntaxError:
                pass
        else:
            specs = re.findall(r'''(?:from\s+|require\s*\(\s*|import\s*\(?\s*)["']([^"']+)["']''', source)
            imports = [stem for spec in specs for stem in local_candidates(files, path, spec)]
        for stem in imports:
            for dep in variants(stem):
                if dep in files and dep not in keep:
                    keep.add(dep)
                    queue.append(dep)
    return sorted(keep)


def jev_batches(plan):
    files = {p: r['content'] for p, r in plan['files'].items()}
    # Batch full file contents. No silent excerpting or token-limit truncation.
    batches, batch, count = [], {}, 0
    for p, content in files.items():
        cost = len(content.encode()) + len(p.encode()) + 500
        if cost > 22000:
            continue  # Always include large files; never classify a truncated excerpt.
        if count + cost > 22000 or len(batch) >= 32:
            batches.append(batch)
            batch, count = {}, 0
        batch[p] = content
        count += cost
    if batch:
        batches.append(batch)
    return batches


SELECTION_POLICIES = ('batch', 'per-file')


def resolve_selection(plan, calls, policy='batch'):
    """Replay recorded probabilities locally; retain uncertain/unjudged evidence.

    The default reproduces the existing whole-batch fallback. Per-file is an
    opt-in experiment that keeps uncertainty without keeping unrelated siblings.
    No model response is evidence of permission or completed implementation.
    """
    if policy not in SELECTION_POLICIES:
        raise ProtocolError('Unknown selection policy')
    files = {p: r['content'] for p, r in plan['files'].items()}
    probabilities, reasons = {}, {p: [] for p in files}
    chosen = set()
    for call in calls:
        scores = call.get('probabilities') if isinstance(call, dict) else None
        if not isinstance(scores, dict) or not scores:
            raise ProtocolError('Invalid recorded probability map')
        for path, value in scores.items():
            if (path not in files or path in probabilities or type(value) not in (int, float)
                    or not math.isfinite(value) or not 0 <= value <= 1):
                raise ProtocolError('Invalid, duplicate or unknown recorded probability')
        probabilities.update(scores)
        uncertain_batch = any(.2 < v < .8 for v in scores.values())
        for path, value in scores.items():
            if value > .2:
                chosen.add(path)
                reasons[path].append('relevant' if value >= .8 else 'uncertain')
            elif policy == 'batch' and uncertain_batch:
                chosen.add(path)
                reasons[path].append('batch_uncertainty')
    unjudged = sorted(set(files) - set(probabilities))
    for path in unjudged:
        chosen.add(path)
        reasons[path].append('unjudged')
    if not chosen:
        chosen.update(files)
        for path in files:
            reasons[path].append('global_no_match')
    selected = dependencies(files, chosen)
    for path in set(selected) - chosen:
        reasons[path].append('guidance_or_dependency')
    kept = set(selected)
    decisions = {}
    for path in files:
        value = probabilities.get(path)
        judgment = ('unjudged' if value is None else 'relevant' if value >= .8
                    else 'irrelevant' if value <= .2 else 'uncertain')
        decisions[path] = {'probability': value, 'judgment': judgment, 'kept': path in kept,
                           'reasons': reasons[path] or ['confidently_irrelevant']}
    before = sum(len(s.encode()) for s in files.values())
    after = sum(len(files[p].encode()) for p in selected)
    return {'paths': selected, 'policy': policy, 'decisions': decisions, 'unjudged_paths': unjudged,
            'metrics': {'candidate_files': len(files), 'selected_files': len(selected),
                        'judged_files': len(probabilities), 'unjudged_files': len(unjudged),
                        'excluded_files': len(plan.get('excluded', {})), 'candidate_bytes': before,
                        'selected_bytes': after, 'omitted_bytes': before - after,
                        'retained_byte_ratio': after / before if before else None}}


def select(plan, mode='auto', on_call=None, max_calls=24, on_attempt=None, policy='batch', cache_dir=None):
    if policy not in SELECTION_POLICIES:
        raise ProtocolError('Unknown selection policy')
    files = {p: r['content'] for p, r in plan['files'].items()}
    size = sum(len(s.encode()) for s in files.values())
    if mode == 'astra' or (mode == 'auto' and size < 12000):
        return {**resolve_selection(plan, [], policy), 'route': 'astra', 'reason': 'explicit_or_small_context', 'jev_calls': []}
    batches = jev_batches(plan)
    if type(max_calls) is not int or not 1 <= max_calls <= 24:
        raise ProtocolError('Jev max_calls must be between 1 and 24')
    needed = sum(read_cache(jev_request({'task': plan['task'], 'files': batch}), cache_dir) is None
                 for batch in batches)
    if needed > max_calls:
        raise ProtocolError(f'Jev request budget exceeds {max_calls} calls; narrow the plan')
    if cache_dir is not None and Path(cache_dir).resolve().is_relative_to(Path(plan['repo']).resolve()):
        raise ProtocolError('Cache must be outside the source repository')
    calls = []
    for batch in batches:
        case = {'task': plan['task'], 'files': batch}
        payload = jev_request(case)
        cached = read_cache(payload, cache_dir)
        if cached is not None:
            result = {**select_context(batch, cached), 'reused': True, 'seconds': 0, 'usage': None,
                      'model': cached['model'], 'request_sha256': request_hash(payload)}
        else:
            if on_attempt:
                on_attempt()
            if cache_dir is None:
                result = call_jev(case)
            else:
                value, meta = request_jev(payload)
                result = {**select_context(batch, value), **meta}
                write_cache(payload, value, cache_dir)
        calls.append(result)
        if on_call:
            on_call(result)
    return {**resolve_selection(plan, calls, policy), 'route': 'jev',
            'reason': 'explicit_or_large_context', 'jev_calls': calls}
