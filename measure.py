#!/usr/bin/env python3
"""Compare saved whole-run records. Missing usage stays unknown; no provider calls."""
import argparse
import json
from pathlib import Path


def provider(calls, attempted):
    live = [c for c in calls if not c.get('reused')]
    known = [c['usage'] for c in live if isinstance(c.get('usage'), dict)
             and all(type(c['usage'].get(k)) is int and c['usage'][k] >= 0
                     for k in ('input_tokens', 'output_tokens'))]
    unknown = None if attempted is None else max(attempted, len(live)) - len(known)
    return {'attempted_calls': attempted, 'recorded_live_calls': len(live),
            'reused_calls': len(calls)-len(live), 'unknown_usage_calls': unknown,
            'known_input_tokens': sum(u['input_tokens'] for u in known),
            'known_output_tokens': sum(u['output_tokens'] for u in known),
            'complete_usage': unknown == 0}


def summarize(paths):
    # Duplicate artifacts must not count as extra runs.
    paths = list(dict.fromkeys(str(Path(p).resolve()) for p in paths))
    records = [json.loads(Path(p).read_text()) for p in paths]
    astra, jev = [], []
    acount, jcount = 0, 0
    seconds = []
    for r in records:
        astra.extend(r.get('astra_calls', []))
        jev.extend(r.get('completed_jev_calls', r.get('jev_calls', [])))
        a = 0 if r.get('kind') == 'evidence_selection' else r.get('attempted_astra_calls')
        # Desktop records describe selection only, never the whole conversation.
        acount = None if acount is None or a is None else acount+a
        j = r.get('attempted_jev_calls', r.get('attempted_calls'))
        jcount = None if jcount is None or j is None else jcount+j
        seconds.append(r.get('seconds'))
    if not any('astra_calls' in r for r in records):
        acount = None
    return {'record_count': len(records), 'statuses': [r.get('status', 'unknown') for r in records],
            'astra': provider(astra, acount), 'jev': provider(jev, jcount),
            'summed_run_seconds': sum(seconds) if all(type(s) in (int, float) and s >= 0 for s in seconds) else None,
            'quality': 'not_established_by_usage_or_exit_status', 'dollar_cost': None}


def compare(baseline, candidate):
    left, right = summarize(baseline), summarize(candidate)
    complete = left['astra']['complete_usage'] and right['astra']['complete_usage']
    before, after = left['astra']['known_input_tokens'], right['astra']['known_input_tokens']
    return {'baseline': left, 'candidate': right,
            'astra_input_reduction': (before-after)/before if complete and before else None,
            'comparable_task_and_acceptance': 'must_be_checked_independently',
            'different_provider_tokens_are_not_added': True}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline', action='append', required=True, help='Saved result.json or selection.json')
    p.add_argument('--candidate', action='append', required=True)
    a = p.parse_args()
    print(json.dumps(compare(a.baseline, a.candidate), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
