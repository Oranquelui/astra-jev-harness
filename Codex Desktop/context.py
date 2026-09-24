#!/usr/bin/env python3
"""Read-only Jev context handoff for the active Codex Desktop conversation."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from shared import repo_context as rc
from shared.credentials import execution_environment
from shared.jev import ProtocolError, failure_record, read_cache, jev_request


def write_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def fresh(plan):
    rc.check_plan_fresh(plan)


def make_plan(repo, task, out, include_paths=None, focus_paths=None, scope_max_calls=4):
    plan = rc.snapshot(repo, task, out, include_paths=include_paths,
                       focus_paths=focus_paths, scope_max_calls=scope_max_calls)
    out = Path(out).resolve()
    out.chmod(0o700)
    plan['surface'] = 'desktop'
    write_json(out / 'plan.json', plan)
    (out / 'PLAN.md').write_text('\n'.join([
        '# Desktop context plan', '', f"Repository: {plan['repo']}", f"HEAD: {plan['head']}",
        f"Candidate files: {len(plan['files'])}; Jev requests: {len(rc.jev_batches(plan))}",
        *([f"Local shortlist: {plan['scope']['eligible_files']} eligible files / "
           f"{plan['scope']['eligible_bytes']} bytes; {plan['scope']['scoped_out_files']} files / "
           f"{plan['scope']['scoped_out_bytes']} bytes scoped out before Jev.",
           'Required-file recall is unknown. Review scoped-out paths below.'
           ] if plan.get('scope') else []),
        *([f"Source ranges: {plan['inference']['source_fragments']}. Budget method: {plan['inference']['budget_method']}.",
           f"Largest estimated state + question: {plan['inference']['max_estimated_state_and_question']}; full request: {plan['inference']['max_estimated_request']}."] if plan.get('inference') else []),
        'Local snapshot only. No provider calls or target writes.',
        'This plan grants no edit, apply, or external-action permission.',
        'Untracked files are included only when explicitly listed. Follow the current task and repository instructions.',
        '', '## Task', task, '', '## Files potentially sent to Jev',
        *['- ' + p for p in plan['files']], '', '## Scoped out before Jev',
        *[f'- {p}: {r["bytes"]} bytes' for p, r in plan.get('scoped_out', {}).items()],
        '', '## Excluded',
        *[f'- {p}: {why}' for p, why in plan['excluded'].items()]]) + '\n')
    return plan


def load_desktop_plan(path):
    plan = rc.load_plan(path)
    if plan.get('surface') != 'desktop':
        raise ProtocolError('Expected a Desktop context plan')
    return plan


def select(plan_dir, out, max_calls=4, policy='batch', cache_dir=None, evidence_dir=None, mode='jev'):
    if policy not in rc.SELECTION_POLICIES:
        raise ProtocolError('Unknown selection policy')
    plan_dir, out = Path(plan_dir).resolve(), Path(out).resolve()
    plan = load_desktop_plan(plan_dir)
    fresh(plan)
    packet = None
    if evidence_dir:
        from shared.evidence import check as check_evidence
        packet = check_evidence(evidence_dir)
        if packet['task'] != plan['task']:
            raise ProtocolError('Evidence task must match the coding plan')
    if out.is_relative_to(Path(plan['repo'])) or out.exists():
        raise ProtocolError('Use a new output directory outside the source repository')
    if cache_dir and Path(cache_dir).resolve().is_relative_to(Path(plan['repo'])):
        raise ProtocolError('Cache must be outside the source repository')
    route = rc.selection_route(plan, 'astra' if mode == 'local' else mode)
    required = (sum(read_cache(jev_request(rc.selection_case(plan, batch)), cache_dir) is None
                    for batch in rc.jev_batches(plan)) if route == 'jev' else 0)
    if type(max_calls) is not int or not 1 <= max_calls <= 24 or required > max_calls:
        raise ProtocolError(f'Plan needs {required} Jev calls; max_calls must cover it and be 1..24')
    env, source = execution_environment() if required else ({}, 'not_needed')
    if required and not env.get('TYPESAFE_API_KEY'):
        raise ProtocolError('Jev credential unavailable: ' + source)
    out.mkdir(parents=True, mode=0o700)
    result_path = out / 'selection.json'
    record = {'version': 1, 'surface': 'desktop', 'status': 'selecting',
              'plan_dir': str(plan_dir), 'plan_sha256': rc.digest((plan_dir / 'plan.json').read_bytes()),
              'max_calls': max_calls, 'planned_calls': required, 'attempted_calls': 0, 'policy': policy,
              'jev_calls': [], 'astra_child_calls': 0, 'selection_mode': mode, 'route': route}
    write_json(result_path, record)

    def attempt():
        record['attempted_calls'] += 1
        write_json(result_path, record)

    def completed(value):
        record['jev_calls'].append(value)
        write_json(result_path, record)

    started = time.monotonic()
    previous = os.environ.get('TYPESAFE_API_KEY')
    try:
        if env.get('TYPESAFE_API_KEY'):
            os.environ['TYPESAFE_API_KEY'] = env['TYPESAFE_API_KEY']
        selected = rc.select(plan, route, on_call=completed, max_calls=max_calls, on_attempt=attempt, policy=policy, cache_dir=cache_dir)
        fresh(plan)
        if rc.digest((plan_dir / 'plan.json').read_bytes()) != record['plan_sha256']:
            raise ProtocolError('Plan changed during selection')
        context = {'task': plan['task'], 'repo': plan['repo'], 'head': plan['head'],
                   'files': {p: plan['files'][p]['content'] for p in selected['paths']}}
        if packet is not None:
            check_evidence(evidence_dir)
            context['evidence'] = packet
            record['evidence_selection_dir'] = str(Path(evidence_dir).resolve())
        write_json(out / 'context.json', context)
        record.update(status='selected', paths=selected['paths'], decisions=selected['decisions'],
                      metrics=selected['metrics'], unjudged_paths=selected['unjudged_paths'],
                      fragment_decisions=selected['fragment_decisions'], reason=selected.get('reason'),
                      context_sha256=rc.digest((out / 'context.json').read_bytes()))
    except Exception as exc:
        # No transport exception bodies or credential values are persisted.
        record['status'] = 'failed'
        record['failure'] = failure_record(exc, 'context_selection')
        record['seconds'] = time.monotonic()-started
        write_json(result_path, record)
        raise
    finally:
        if previous is None:
            os.environ.pop('TYPESAFE_API_KEY', None)
        else:
            os.environ['TYPESAFE_API_KEY'] = previous
    record['seconds'] = time.monotonic()-started
    write_json(result_path, record)
    (out / 'REPORT.md').write_text(
        f"# Desktop context selected\n\nFiles: {len(record['paths'])}/{len(plan['files'])}. "
        f"Jev completed calls: {sum(not c.get('reused', False) for c in record['jev_calls'])}; attempted: {record['attempted_calls']}. "
        'Astra child calls: 0.\n\nThis is context selection, not implementation or verification. '
        'Read the metadata first, then use the read command for needed line ranges; do not dump context.json. '
        'Run check before edits. If the source changes, refresh the plan before selecting again.\n'
        + f"\nRoute: {route}. Policy: {policy}. Judged: {selected['metrics']['judged_files']}; "
        + f"unjudged: {selected['metrics']['unjudged_files']}; excluded: {selected['metrics']['excluded_files']}.\n"
        + f"Retained source bytes after Jev: {selected['metrics']['selected_bytes']}/{selected['metrics']['candidate_bytes']}.\n"
        + f"Locally scoped out before Jev: {selected['metrics']['prefiltered_files']} files / "
        + f"{selected['metrics']['prefiltered_bytes']} bytes. Required-file recall is unknown without labels.\n"
        + 'Source bytes are not tokens, cost, or proof of correctness. See selection.json decisions for per-file reasons.\n')
    return record


def check(selection_dir):
    selection_dir = Path(selection_dir).resolve()
    record = json.loads((selection_dir / 'selection.json').read_text())
    if record.get('surface') != 'desktop' or record.get('status') != 'selected':
        raise ProtocolError('Selection did not complete; inspect saved attempts before retrying')
    plan_dir = Path(record['plan_dir'])
    if rc.digest((plan_dir / 'plan.json').read_bytes()) != record['plan_sha256']:
        raise ProtocolError('Context plan changed')
    if rc.digest((selection_dir / 'context.json').read_bytes()) != record['context_sha256']:
        raise ProtocolError('Selected context changed')
    fresh(load_desktop_plan(plan_dir))
    if record.get('evidence_selection_dir'):
        from shared.evidence import check as check_evidence
        check_evidence(record['evidence_selection_dir'])
    return {'status': 'fresh', 'astra_child_calls': 0, 'target_writes': 0}


def read_context(selection_dir, path, start_line=1, end_line=None):
    """Expose only a requested range after checking provenance and source freshness."""
    check(selection_dir)
    if type(start_line) is not int or start_line < 1:
        raise ProtocolError('Start line must be positive')
    end_line = start_line + 79 if end_line is None else end_line
    if type(end_line) is not int or end_line < start_line or end_line - start_line >= 200:
        raise ProtocolError('Read at most 200 lines per request')
    directory = Path(selection_dir).resolve()
    record = json.loads((directory / 'selection.json').read_text())
    if path not in record['paths']:
        raise ProtocolError('Path is not part of the selected context')
    context = json.loads((directory / 'context.json').read_text())
    text = context['files'][path]
    lines = text.splitlines(keepends=True)
    if start_line > max(1, len(lines)):
        raise ProtocolError('Start line is outside the file')
    end_line = min(end_line, len(lines))
    excerpt = ''.join(lines[start_line-1:end_line])
    if len(excerpt.encode()) > 24000:
        raise ProtocolError('Requested range exceeds 24KB; use a narrower range or inspect the long line locally')
    return {'path': path, 'source_sha256': rc.digest(text.encode()),
            'start_line': start_line, 'end_line': end_line, 'total_lines': len(lines),
            'next_start_line': end_line + 1 if end_line < len(lines) else None,
            'text': excerpt, 'returned_bytes': len(excerpt.encode()), 'provider_calls': 0}


def compare(selection_dir, required_paths=None):
    """Compare policies against identical saved evidence, without network or writes."""
    selection_dir = Path(selection_dir).resolve()
    record = json.loads((selection_dir / 'selection.json').read_text())
    if record.get('surface') != 'desktop' or record.get('status') not in ('selected', 'failed', 'selecting'):
        raise ProtocolError('Expected a Desktop selection record')
    plan_dir = Path(record['plan_dir'])
    if rc.digest((plan_dir / 'plan.json').read_bytes()) != record['plan_sha256']:
        raise ProtocolError('Recorded plan changed; comparison refused')
    plan = load_desktop_plan(plan_dir)
    required_paths = [] if required_paths is None else required_paths
    if (not isinstance(required_paths, list) or any(not isinstance(p, str) for p in required_paths)
            or len(set(required_paths)) != len(required_paths)
            or not set(required_paths) <= set(plan['files']) | set(plan.get('scoped_out', {}))):
        raise ProtocolError('Required labels must be unique eligible paths from the recorded plan')
    missing_in_scope = sorted(set(required_paths) & set(plan.get('scoped_out', {})))
    scope_recall = (1 - len(missing_in_scope) / len(required_paths)) if required_paths else None
    within_scope_labels = set(required_paths) & set(plan['files'])
    compared = {}
    for policy in rc.SELECTION_POLICIES:
        selected = rc.resolve_selection(plan, record['jev_calls'], policy)
        missing = sorted(set(required_paths) - set(selected['paths']))
        missing_within_scope = within_scope_labels - set(selected['paths'])
        compared[policy] = {**selected['metrics'], 'paths': selected['paths'],
                            'unjudged_paths': selected['unjudged_paths'],
                            'missing_required_paths': missing,
                            'required_recall': 1 - len(missing) / len(required_paths) if required_paths else None,
                            'within_scope_required_recall':
                                1 - len(missing_within_scope) / len(within_scope_labels)
                                if within_scope_labels else None}
    return {'status': 'historical_comparison', 'source_status': record['status'],
            'additional_provider_calls': 0, 'required_paths': required_paths,
            'quality_basis': 'caller_supplied_required_files' if required_paths else 'unlabeled_no_quality_claim',
            'scope_required_recall': scope_recall, 'missing_in_scope': missing_in_scope,
            'policies': compared,
            'additional_omitted_paths': sorted(set(compared['batch']['paths']) - set(compared['per-file']['paths'])),
            'additional_omitted_bytes': compared['batch']['selected_bytes'] - compared['per-file']['selected_bytes']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('doctor')
    p = sub.add_parser('plan')
    p.add_argument('--repo', required=True)
    p.add_argument('--include-file', action='append', default=[])
    p.add_argument('--focus-file', action='append', default=[])
    p.add_argument('--scope-max-calls', type=int, default=4)
    p.add_argument('--task-file', required=True)
    p.add_argument('--out', required=True)
    p = sub.add_parser('select')
    p.add_argument('--plan', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--max-calls', type=int, default=4)
    p.add_argument('--cache-dir')
    p.add_argument('--evidence')
    p.add_argument('--policy', choices=rc.SELECTION_POLICIES, default='batch')
    p.add_argument('--mode', choices=('auto', 'jev', 'local'), default='jev',
                   help='auto keeps contexts under 12KB locally; local always skips Jev')
    p = sub.add_parser('check')
    p.add_argument('--selection', required=True)
    p = sub.add_parser('read', help='Read a bounded selected source range after freshness checks')
    p.add_argument('--selection', required=True)
    p.add_argument('--path', required=True)
    p.add_argument('--start-line', type=int, default=1)
    p.add_argument('--end-line', type=int)
    p = sub.add_parser('compare', help='Replay saved judgments without API calls or source writes')
    p.add_argument('--selection', required=True)
    p.add_argument('--required-file', action='append', default=[])
    args = parser.parse_args()
    try:
        if args.command == 'doctor':
            env, source = execution_environment()
            print(json.dumps({'surface': 'desktop', 'harness_root': str(ROOT),
                              'key_source': source, 'typesafe_key_present': bool(env.get('TYPESAFE_API_KEY'))}))
            return 0 if env.get('TYPESAFE_API_KEY') else 1
        if args.command == 'plan':
            plan = make_plan(args.repo, Path(args.task_file).read_text(), args.out,
                             args.include_file, args.focus_file, args.scope_max_calls)
            result = {'status': 'planned', 'files': len(plan['files']), 'planned_calls': len(rc.jev_batches(plan))}
        elif args.command == 'select':
            record = select(args.plan, args.out, args.max_calls, args.policy, args.cache_dir, args.evidence, args.mode)
            result = {'status': record['status'], 'selected_files': len(record['paths']), 'route': record['route'],
                      'jev_completed_calls': sum(not c.get('reused', False) for c in record['jev_calls']),
                      'jev_reused_calls': sum(bool(c.get('reused')) for c in record['jev_calls']), 'astra_child_calls': 0}
        elif args.command == 'read':
            result = read_context(args.selection, args.path, args.start_line, args.end_line)
        elif args.command == 'compare':
            result = compare(args.selection, args.required_file)
        else:
            result = check(args.selection)
        print(json.dumps(result))
        return 0
    except (ProtocolError, OSError, ValueError, KeyError, TypeError):
        # Keep error output independent of file contents and provider response bodies.
        print('Desktop context operation failed; inspect plan freshness, call budget, credential availability and saved selection status.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
