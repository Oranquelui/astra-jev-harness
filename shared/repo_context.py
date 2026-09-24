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
from shared import context_chunks as chunks

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
    occupied = list(plan['files']) + list(plan.get('excluded', {})) + list(plan.get('scoped_out', {}))
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


SCOPE_STOPWORDS = {'add', 'and', 'code', 'coding', 'file', 'files', 'fix', 'for', 'from',
                   'implement', 'into', 'new', 'repo', 'repository', 'task', 'test',
                   'tests', 'the', 'then', 'this', 'update', 'use', 'using', 'with'}


def scope_terms(value):
    """Cheap, deterministic search terms; cross-language recall is not assumed."""
    split_camel = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', value)
    return {term for term in re.findall(r'[a-z][a-z0-9]*', split_camel.casefold())
            if len(term) >= 3 and term not in SCOPE_STOPWORDS}


def scoped_shortlist(files, task, includes, focus, test_edits, max_calls, max_bytes):
    """Local fast-search stage. Jev judges only the reviewed, bounded shortlist."""
    if type(max_calls) is not int or not 1 <= max_calls <= 24:
        raise ProtocolError('Scope max_calls must be between 1 and 24')
    if type(max_bytes) is not int or not 1 <= max_bytes <= 2000000:
        raise ProtocolError('Scope max_bytes must be between 1 and 2,000,000')
    contents = {p: record['content'] for p, record in files.items()}
    required = set(includes) | set(focus) | set(test_edits)
    required.update(p for p in files if p in task)
    missing = required - set(files)
    if missing:
        raise ProtocolError('Focused or required path is not an eligible snapshot file: ' + sorted(missing)[0])

    def bounded(paths):
        chosen = {p: files[p] for p in sorted(paths)}
        return (len(chosen) <= 1500 and sum(r['bytes'] for r in chosen.values()) <= max_bytes
                and len(jev_batches({'files': chosen, 'task': task, 'context_format': chunks.FORMAT})) <= max_calls)

    selected = set(dependencies(contents, required))
    if not bounded(selected):
        raise ProtocolError('Required focus, guidance, configuration or dependency closure exceeds scope budget; narrow --focus-file or raise --scope-max-calls')
    terms = scope_terms(task)
    ranked = []
    for path, source in contents.items():
        if path in selected:
            continue
        leaf = scope_terms(PurePosixPath(path).stem)
        path_terms = scope_terms(path)
        content_terms = scope_terms(source)
        score = sum(12 for term in terms & leaf) + sum(4 for term in terms & (path_terms - leaf))
        score += len(terms & content_terms)
        if score:
            ranked.append((-score, path))
    ranked.sort()
    if not ranked and not required:
        raise ProtocolError('No local task match for a large repository; pass --focus-file for reviewed source paths')
    accepted = 0
    for _, path in ranked:
        expanded = set(dependencies(contents, selected | {path}))
        if bounded(expanded):
            selected = expanded
            accepted += 1
        elif not accepted and not required:
            raise ProtocolError('Top local match exceeds the scope budget; pass --focus-file or raise --scope-max-calls')
    if not selected or (not accepted and not required):
        raise ProtocolError('No task candidate fits the scope budget; pass --focus-file or raise --scope-max-calls')
    return selected


def snapshot(repo, task, out, create_paths=None, test_edit_paths=None, include_paths=None,
             focus_paths=None, scope_max_calls=4, scope_max_bytes=2000000):
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
    focused = focus_paths or []
    if not isinstance(included, list) or any(not isinstance(p, str) for p in included):
        raise ProtocolError('Explicit includes must be relative paths')
    if not isinstance(focused, list) or any(not isinstance(p, str) for p in focused):
        raise ProtocolError('Focused files must be relative paths')
    if len(set(focused)) != len(focused):
        raise ProtocolError('Duplicate focused file')
    for name in focused:
        safe_path(repo, name)
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
    if not files:
        raise ProtocolError('Snapshot has no eligible files')
    if any(p not in files for p in focused):
        raise ProtocolError('Focused file is not an eligible tracked or explicitly included file')
    if type(scope_max_calls) is not int or not 1 <= scope_max_calls <= 24:
        raise ProtocolError('Scope max_calls must be between 1 and 24')
    if type(scope_max_bytes) is not int or not 1 <= scope_max_bytes <= 2000000:
        raise ProtocolError('Scope max_bytes must be between 1 and 2,000,000')
    eligible_count, eligible_bytes = len(files), sum(f['bytes'] for f in files.values())
    all_files = files
    scoped_out, scope = {}, None
    if (eligible_bytes > 2000000 or eligible_count > 1500
            or len(jev_batches({'files': files, 'task': task, 'context_format': chunks.FORMAT})) > scope_max_calls):
        kept = scoped_shortlist(files, task, included, focused, test_edit_paths or [],
                                scope_max_calls, scope_max_bytes)
        scoped_out = {p: {key: r[key] for key in ('sha256', 'bytes', 'mode')}
                      for p, r in files.items() if p not in kept}
        files = {p: r for p, r in files.items() if p in kept}
        scope = {'strategy': 'local_task_shortlist', 'eligible_files': eligible_count,
                 'eligible_bytes': eligible_bytes, 'scoped_out_files': len(scoped_out),
                 'scoped_out_bytes': sum(r['bytes'] for r in scoped_out.values()),
                 'max_calls': scope_max_calls, 'max_bytes': scope_max_bytes,
                 'planned_calls': len(jev_batches({'files': files, 'task': task, 'context_format': chunks.FORMAT})),
                 'focus_paths': focused}
    if git(repo, 'status', '--porcelain=v1', '-z') != before:
        raise ProtocolError('Repository status changed during snapshot; try again')
    for rel, record in all_files.items():
        if digest(safe_path(repo, rel).read_bytes()) != record['sha256']:
            raise ProtocolError('Repository content changed during snapshot; try again')
    manifest = {'version': 1, 'context_format': chunks.FORMAT, 'repo': str(repo), 'head': git(repo, 'rev-parse', 'HEAD').decode().strip(),
                'branch': git(repo, 'branch', '--show-current').decode().strip(),
                'status_sha256': digest(before), 'task': task, 'files': files, 'excluded': excluded,
                'explicit_includes': included}
    if focused:
        manifest['focus_paths'] = focused
    if scope is not None:
        manifest.update(scoped_out=scoped_out, scope=scope)
    if create_paths or test_edit_paths:
        manifest.update(version=2, create_paths=create_paths or [], test_edit_paths=test_edit_paths or [])
    manifest['inference'] = chunks.summary(manifest)
    validate_change_scope(manifest)
    check_creation_destinations(manifest)
    out.mkdir(parents=True)
    (out / 'plan.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    lines = ['# Repository plan', '', f"Repository: {repo}", f"HEAD: {manifest['head']}",
             f"Included: {len(files)} files / {sum(f['bytes'] for f in files.values())} bytes",
             f"Excluded: {len(excluded)} files. No API calls or repository writes have occurred.", '',
             *([f"Local shortlist: {eligible_count} eligible files / {eligible_bytes} bytes; "
                f"{len(scoped_out)} files / {scope['scoped_out_bytes']} bytes scoped out; "
                f"{scope['planned_calls']} planned Jev calls.",
                'Scoped-out files were not judged by Jev. Required-file recall is unknown.', ''] if scope else []),
             f"Jev plan: {manifest['inference']['source_fragments']} complete-coverage source ranges / {manifest['inference']['planned_calls']} calls.",
             'Budgets estimate serialized UTF-8 bytes plus reserve, not exact Jev tokens.', '',
             '## Task', task, '', '## Permitted new files', *['- ' + p for p in manifest.get('create_paths', [])],
             '', '## Permitted existing test edits', *['- ' + p for p in manifest.get('test_edit_paths', [])],
             '', 'Existing source files remain editable; other tests and instructions are read-only.',
             'Review existing regression tests and task acceptance checks separately from generated tests.',
             '', '## Files potentially sent when running', *['- ' + p for p in files],
             '', '## Scoped out before Jev', *[f'- {p}: {r["bytes"]} bytes' for p, r in scoped_out.items()],
             '', '## Excluded', *[f'- {p}: {reason}' for p, reason in excluded.items()]]
    (out / 'PLAN.md').write_text('\n'.join(lines) + '\n')
    return manifest


def load_plan(path):
    plan = json.loads((Path(path) / 'plan.json').read_text())
    if plan.get('context_format') not in (None, chunks.FORMAT):
        raise ProtocolError('Unsupported context format')
    if plan.get('version') not in (1, 2):
        raise ProtocolError('Unsupported plan version')
    if plan['version'] == 1 and (plan.get('create_paths') or plan.get('test_edit_paths')):
        raise ProtocolError('Explicit change permissions require plan version 2')
    for rel, r in plan['files'].items():
        safe_path(Path(path), rel)
        if digest(r['content'].encode()) != r['sha256'] or eligibility(rel) or SECRET.search(r['content']):
            raise ProtocolError('Plan file integrity or eligibility check failed')
    scoped_out = plan.get('scoped_out', {})
    if not isinstance(scoped_out, dict) or set(scoped_out) & set(plan['files']):
        raise ProtocolError('Invalid scoped-out file index')
    for rel, record in scoped_out.items():
        safe_path(Path(plan['repo']), rel)
        if (not isinstance(record, dict) or set(record) != {'sha256', 'bytes', 'mode'}
                or not isinstance(record['sha256'], str) or not re.fullmatch(r'[0-9a-f]{64}', record['sha256'])
                or type(record['bytes']) is not int or not 0 <= record['bytes'] <= 100000
                or type(record['mode']) is not int or not 0 <= record['mode'] <= 0o777
                or eligibility(rel)):
            raise ProtocolError('Invalid scoped-out file metadata')
    if sum(r['bytes'] for r in plan['files'].values()) > 2000000 or len(plan['files']) > 1500:
        raise ProtocolError('Plan exceeds repository snapshot bounds')
    focused = plan.get('focus_paths', [])
    if (not isinstance(focused, list) or any(not isinstance(p, str) for p in focused)
            or len(set(focused)) != len(focused) or not set(focused) <= set(plan['files'])):
        raise ProtocolError('Invalid focused-file record')
    scope = plan.get('scope')
    if scope is not None:
        if (not isinstance(scope, dict) or scope.get('strategy') != 'local_task_shortlist'
                or scope.get('eligible_files') != len(plan['files']) + len(scoped_out)
                or scope.get('eligible_bytes') != sum(r['bytes'] for r in plan['files'].values()) + sum(r['bytes'] for r in scoped_out.values())
                or scope.get('scoped_out_files') != len(scoped_out)
                or scope.get('scoped_out_bytes') != sum(r['bytes'] for r in scoped_out.values())
                or scope.get('planned_calls') != len(jev_batches(plan))
                or scope.get('focus_paths') != focused
                or type(scope.get('max_calls')) is not int or not 1 <= scope['max_calls'] <= 24
                or type(scope.get('max_bytes')) is not int or not 1 <= scope['max_bytes'] <= 2000000
                or scope['planned_calls'] > scope['max_calls']
                or sum(r['bytes'] for r in plan['files'].values()) > scope['max_bytes']):
            raise ProtocolError('Invalid local shortlist record')
    elif scoped_out:
        raise ProtocolError('Scoped-out files require scope metadata')
    validate_change_scope(plan)
    return plan


def check_plan_fresh(plan):
    """Verify both sent and locally omitted source against the reviewed plan."""
    repo = Path(plan['repo'])
    if (git(repo, 'rev-parse', 'HEAD').decode().strip() != plan['head']
            or git(repo, 'branch', '--show-current').decode().strip() != plan['branch']
            or digest(git(repo, 'status', '--porcelain=v1', '-z')) != plan['status_sha256']):
        raise ProtocolError('Repository state changed; create a fresh context plan')
    for name, record in {**plan['files'], **plan.get('scoped_out', {})}.items():
        path = safe_path(repo, name)
        if (not path.is_file() or digest(path.read_bytes()) != record['sha256']
                or path.stat().st_mode & 0o777 != record['mode']):
            raise ProtocolError('Repository content changed; create a fresh context plan')


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


def selection_case(plan, batch):
    if plan.get('context_format') == chunks.FORMAT:
        return chunks.case(plan, batch)
    return {'task': plan['task'], 'files': batch}


def jev_batches(plan):
    if plan.get('context_format') == chunks.FORMAT:
        return chunks.batches(plan)
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
    catalog = chunks.units(plan) if plan.get('context_format') == chunks.FORMAT else {p: {'path': p} for p in files}
    probabilities, reasons = {}, {p: [] for p in files}
    chosen = set()
    for call in calls:
        scores = call.get('probabilities') if isinstance(call, dict) else None
        if not isinstance(scores, dict) or not scores:
            raise ProtocolError('Invalid recorded probability map')
        for path, value in scores.items():
            if (path not in catalog or path in probabilities or type(value) not in (int, float)
                    or not math.isfinite(value) or not 0 <= value <= 1):
                raise ProtocolError('Invalid, duplicate or unknown recorded probability')
        probabilities.update(scores)
        uncertain_batch = any(.2 < v < .8 for v in scores.values())
        for unit_id, value in scores.items():
            path = catalog[unit_id]['path']
            if value > .2:
                chosen.add(path)
                reasons[path].append('relevant' if value >= .8 else 'uncertain')
            elif policy == 'batch' and uncertain_batch:
                chosen.add(path)
                reasons[path].append('batch_uncertainty')
    unjudged_units = set(catalog) - set(probabilities)
    unjudged = sorted({catalog[key]['path'] for key in unjudged_units})
    for path in unjudged:
        chosen.add(path)
        reasons[path].append('unjudged')
    for path in plan.get('focus_paths', []):
        chosen.add(path)
        reasons[path].append('explicit_focus')
    if not chosen:
        chosen.update(files)
        for path in files:
            reasons[path].append('global_no_match')
    selected = dependencies(files, chosen)
    for path in set(selected) - chosen:
        reasons[path].append('guidance_or_dependency')
    kept = set(selected)
    decisions = {}
    by_path = {path: [key for key, unit in catalog.items() if unit['path'] == path] for path in files}
    for path in files:
        keys = by_path[path]
        scores = [probabilities[key] for key in keys if key in probabilities]
        value = max(scores) if scores and path not in unjudged else None
        judgment = ('unjudged' if value is None else 'relevant' if value >= .8
                    else 'irrelevant' if value <= .2 else 'uncertain')
        decisions[path] = {'probability': value if len(keys) == 1 else None, 'judgment': judgment, 'kept': path in kept,
                           'reasons': sorted(set(reasons[path])) or ['confidently_irrelevant']}
        if len(keys) > 1:
            decisions[path].update(fragment_ids=keys, max_fragment_probability=max(scores) if scores else None,
                                   fully_judged=path not in unjudged)
    before = sum(len(s.encode()) for s in files.values())
    after = sum(len(files[p].encode()) for p in selected)
    prefiltered = plan.get('scoped_out', {})
    prefiltered_bytes = sum(r['bytes'] for r in prefiltered.values())
    return {'paths': selected, 'policy': policy, 'decisions': decisions, 'unjudged_paths': unjudged,
            'fragment_decisions': {key: {**{k: v for k, v in unit.items() if k != 'text'},
                                        'probability': probabilities.get(key)} for key, unit in catalog.items()},
            'metrics': {'candidate_files': len(files), 'selected_files': len(selected),
                        'judged_files': len(files) - len(unjudged), 'unjudged_files': len(unjudged),
                        'candidate_fragments': len(catalog), 'judged_fragments': len(probabilities),
                        'unjudged_fragments': len(unjudged_units),
                        'unjudged_bytes': sum(len(files[p].encode()) for p in unjudged),
                        'excluded_files': len(plan.get('excluded', {})), 'candidate_bytes': before,
                        'selected_bytes': after, 'omitted_bytes': before - after,
                        'retained_byte_ratio': after / before if before else None,
                        'prefiltered_files': len(prefiltered), 'prefiltered_bytes': prefiltered_bytes,
                        'eligible_files': len(files) + len(prefiltered),
                        'eligible_bytes': before + prefiltered_bytes}}


def selection_route(plan, mode):
    if mode not in ('auto', 'astra', 'jev'):
        raise ProtocolError('Unknown selection mode')
    size = sum(len(r['content'].encode()) for r in plan['files'].values())
    return 'astra' if mode == 'astra' or (mode == 'auto' and size < 12000) else 'jev'


def select(plan, mode='auto', on_call=None, max_calls=24, on_attempt=None, policy='batch', cache_dir=None):
    if policy not in SELECTION_POLICIES:
        raise ProtocolError('Unknown selection policy')
    files = {p: r['content'] for p, r in plan['files'].items()}
    if selection_route(plan, mode) == 'astra':
        return {**resolve_selection(plan, [], policy), 'route': 'astra', 'reason': 'explicit_or_small_context', 'jev_calls': []}
    batches = jev_batches(plan)
    if type(max_calls) is not int or not 1 <= max_calls <= 24:
        raise ProtocolError('Jev max_calls must be between 1 and 24')
    needed = sum(read_cache(jev_request(selection_case(plan, batch)), cache_dir) is None
                 for batch in batches)
    if needed > max_calls:
        raise ProtocolError(f'Jev request budget exceeds {max_calls} calls; narrow the plan')
    if cache_dir is not None and Path(cache_dir).resolve().is_relative_to(Path(plan['repo']).resolve()):
        raise ProtocolError('Cache must be outside the source repository')
    calls = []
    for batch in batches:
        case = selection_case(plan, batch)
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
