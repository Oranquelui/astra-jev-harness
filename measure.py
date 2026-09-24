#!/usr/bin/env python3
"""Compare saved whole-run records. Missing usage stays unknown; no provider calls."""
import argparse
import json
from pathlib import Path
from decimal import Decimal, InvalidOperation


def cache_counts(usage):
    """API nested details or Codex CLI cache reads; absent fields stay unknown."""
    total = usage.get('input_tokens')
    details = usage.get('input_tokens_details')
    details = details if isinstance(details, dict) else {}
    read = details.get('cached_tokens', usage.get('cached_input_tokens'))
    write = details.get('cache_write_tokens', usage.get('cache_write_tokens'))
    valid = lambda n: type(n) is int and 0 <= n <= total
    if not valid(read):
        read = None
    if not valid(write):
        write = None
    if read is not None and write is not None and read + write > total:
        return None, None, None
    ordinary = total - read - write if read is not None and write is not None else None
    return read, write, ordinary


def provider(calls, attempted, cache_required=True):
    live = [c for c in calls if not c.get('reused')]
    known = [c['usage'] for c in live if isinstance(c.get('usage'), dict)
             and all(type(c['usage'].get(k)) is int and c['usage'][k] >= 0
                     for k in ('input_tokens', 'output_tokens'))]
    unknown = None if attempted is None else max(attempted, len(live)) - len(known)
    cache = [cache_counts(u) for u in known]
    cache_unknown = None if unknown is None else unknown + sum(o is None for _, _, o in cache)
    ordinary = sum(o for _, _, o in cache if o is not None)
    return {'known_cached_input_tokens': sum(r for r, _, _ in cache if r is not None),
            'known_cache_write_tokens': sum(w for _, w, _ in cache if w is not None),
            'known_ordinary_input_tokens': ordinary,
            'ordinary_input_tokens': ordinary if cache_unknown == 0 else None,
            'unknown_cache_usage_calls': cache_unknown,
            'complete_cache_usage': cache_unknown == 0 if cache_required else None,
            'cache_accounting_applicable': cache_required,
            'attempted_calls': attempted, 'recorded_live_calls': len(live),
            'reused_calls': len(calls)-len(live), 'unknown_usage_calls': unknown,
            'known_input_tokens': sum(u['input_tokens'] for u in known),
            'known_output_tokens': sum(u['output_tokens'] for u in known),
            'complete_usage': unknown == 0}


def validate_prices(prices):
    if not isinstance(prices, dict):
        raise ValueError('Prices must map model names to USD-per-million rates')
    allowed = {'input', 'output', 'cache_read', 'cache_write'}
    for model, rates in prices.items():
        if not isinstance(model, str) or not isinstance(rates, dict) or set(rates) - allowed:
            raise ValueError('Invalid model price entry')
        for value in rates.values():
            if isinstance(value, bool) or not isinstance(value, (str, int, float)):
                raise ValueError('Invalid price')
            try:
                number = Decimal(str(value))
            except InvalidOperation:
                raise ValueError('Invalid price') from None
            if not number.is_finite() or number < 0:
                raise ValueError('Prices must be finite and nonnegative')


def estimate_cost(calls, attempted, prices, cache_required):
    """User-supplied, model-specific rates; no guesses about absent cache usage."""
    live = [c for c in calls if not c.get('reused')]
    subtotal, priced = Decimal(0), 0
    for call in live:
        usage, rates = call.get('usage'), prices.get(call.get('model'), {})
        if not isinstance(usage, dict) or not all(type(usage.get(k)) is int and usage[k] >= 0
                                                for k in ('input_tokens', 'output_tokens')):
            continue
        if not {'input', 'output'} <= set(rates):
            continue
        ordinary, cached, written = usage['input_tokens'], 0, 0
        if cache_required:
            cached, written, ordinary = cache_counts(usage)
            if ordinary is None or not {'cache_read', 'cache_write'} <= set(rates):
                continue
        amount = ordinary * Decimal(str(rates['input'])) + usage['output_tokens'] * Decimal(str(rates['output']))
        if cache_required:
            amount += cached * Decimal(str(rates['cache_read'])) + written * Decimal(str(rates['cache_write']))
        subtotal += amount / Decimal(1_000_000)
        priced += 1
    unknown = None if attempted is None else max(attempted, len(live)) - priced
    return {'estimated_usd': str(subtotal) if unknown == 0 else None,
            'known_subtotal_usd': str(subtotal), 'unpriced_or_unknown_calls': unknown,
            'complete': unknown == 0, 'basis': 'supplied_model_rates_not_invoice_or_subscription_usage'}


def summarize(paths, prices=None):
    if prices is not None:
        validate_prices(prices)
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
    summary = {'record_count': len(records), 'statuses': [r.get('status', 'unknown') for r in records],
            'astra': provider(astra, acount), 'jev': provider(jev, jcount, cache_required=False),
            'summed_run_seconds': sum(seconds) if all(type(s) in (int, float) and s >= 0 for s in seconds) else None,
            'quality': 'not_established_by_usage_or_exit_status', 'dollar_cost': None}
    if prices is not None:
        costs = {'astra': estimate_cost(astra, acount, prices, True),
                 'jev': estimate_cost(jev, jcount, prices, False)}
        summary['cost_estimates'] = costs
        if all(c['complete'] for c in costs.values()):
            summary['dollar_cost'] = str(sum((Decimal(c['estimated_usd']) for c in costs.values()), Decimal(0)))
    return summary


def compare(baseline, candidate, prices=None):
    left, right = summarize(baseline, prices), summarize(candidate, prices)
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
    p.add_argument('--prices', help='Optional JSON model -> input/output/cache_read/cache_write USD per million')
    a = p.parse_args()
    prices = json.loads(Path(a.prices).read_text()) if a.prices else None
    print(json.dumps(compare(a.baseline, a.candidate, prices), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
