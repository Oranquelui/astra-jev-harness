"""Large-context coverage and cache accounting regressions; no paid providers."""
import json
import unittest
from unittest.mock import patch
from shared import repo_context as rc
from shared.jev import jev_request
import measure


def plan(files):
    return {'context_format': 'fragments-v1', 'task': 'Fix checkout', 'repo': '/synthetic',
            'files': {p: {'content': s} for p, s in files.items()}, 'excluded': {}}


class FragmentBudgetTests(unittest.TestCase):
    def test_large_unicode_and_long_line_are_fully_covered_with_bounded_requests(self):
        from shared.context_chunks import units, request_bounds
        p = plan({'big.py': '# 日本語🙂\\"\n' * 4000, 'long.md': 'あ' * 15000})
        fragments = units(p)
        for path, record in p['files'].items():
            parts = [u for u in fragments.values() if u['path'] == path]
            self.assertGreater(len(parts), 1)
            self.assertEqual(''.join(u['text'] for u in parts), record['content'])
            self.assertEqual(parts[0]['start_byte'], 0)
            self.assertEqual(parts[-1]['end_byte'], len(record['content'].encode()))
            for left, right in zip(parts, parts[1:]):
                self.assertEqual(left['end_byte'], right['start_byte'])
        sent = set()
        for batch in rc.jev_batches(p):
            payload = jev_request(rc.selection_case(p, batch))
            bounds = request_bounds(payload)
            self.assertLessEqual(bounds['state_and_longest_question'], 30000)
            self.assertLessEqual(bounds['total'], 60000)
            sent.update(batch)
        self.assertEqual(sent, set(fragments))

    def test_late_relevant_fragment_keeps_file_and_unjudged_tail_is_not_discarded(self):
        from shared.context_chunks import units
        p = plan({'a.py': '# irrelevant\n' * 4000, 'b.py': 'pass\n'})
        ids = [i for i, u in units(p).items() if u['path'] == 'a.py']
        scores = {i: .01 for i in units(p)}
        scores['b.py'] = .9
        scores[ids[-1]] = .9
        result = rc.resolve_selection(p, [{'probabilities': scores}], 'per-file')
        self.assertIn('a.py', result['paths'])
        scores.pop(ids[-1])
        result = rc.resolve_selection(p, [{'probabilities': scores}], 'per-file')
        self.assertIn('a.py', result['unjudged_paths'])
        self.assertIn('a.py', result['paths'])
        self.assertEqual(result['metrics']['unjudged_fragments'], 1)

    def test_all_irrelevant_fragments_omit_only_the_unneeded_file(self):
        from shared.context_chunks import units
        p = plan({'large.md': 'irrelevant\n' * 4000, 'main.py': 'pass\n'})
        scores = {i: (.9 if u['path'] == 'main.py' else .01) for i, u in units(p).items()}
        r = rc.resolve_selection(p, [{'probabilities': scores}], 'per-file')
        self.assertEqual(r['paths'], ['main.py'])
        self.assertEqual(r['metrics']['unjudged_files'], 0)
        self.assertEqual(r['metrics']['judged_files'], 2)
        self.assertIsNone(r['decisions']['large.md']['probability'])

    def test_legacy_plan_keeps_original_oversize_behavior(self):
        p = plan({'large.md': 'x' * 40000, 'main.py': 'pass'})
        p.pop('context_format')
        self.assertEqual(list(rc.jev_batches(p)[0]), ['main.py'])
        self.assertIn('large.md', rc.resolve_selection(p, [{'probabilities': {'main.py': .9}}])['unjudged_paths'])

    def test_budget_failure_precedes_provider(self):
        p = plan({'large.md': 'abc\n' * 20000})
        with patch.object(rc, 'call_jev') as provider, self.assertRaises(rc.ProtocolError):
            rc.select(p, 'jev', max_calls=1)
        provider.assert_not_called()


class CacheUsageTests(unittest.TestCase):
    def test_prices_count_each_input_category_once_and_reuse_is_free(self):
        prices = {'test-model': {'input': 10, 'output': 20, 'cache_read': 1, 'cache_write': 12.5}}
        calls = [{'model': 'test-model', 'usage': {'input_tokens': 1000, 'output_tokens': 10,
                  'input_tokens_details': {'cached_tokens': 600, 'cache_write_tokens': 300}}},
                 {'reused': True, 'usage': None}]
        result = measure.estimate_cost(calls, 1, prices, True)
        self.assertEqual(result['estimated_usd'], '0.00555')
        self.assertIsNone(measure.estimate_cost(calls, 2, prices, True)['estimated_usd'])
        calls[0]['usage']['input_tokens_details'].pop('cache_write_tokens')
        self.assertIsNone(measure.estimate_cost(calls, 1, prices, True)['estimated_usd'])

    def test_jev_flat_price_and_invalid_rates(self):
        prices = {'jev-test': {'input': '.042', 'output': 0}}
        measure.validate_prices(prices)
        result = measure.estimate_cost([{'model': 'jev-test', 'usage': {'input_tokens': 1000000, 'output_tokens': 500}}], 1, prices, False)
        self.assertEqual(result['estimated_usd'], '0.042')
        for value in ('NaN', 'Infinity', -1, True, 'secret'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                measure.validate_prices({'model': {'input': value}})

    def test_api_cache_categories_are_disjoint(self):
        r = measure.provider([{'usage': {'input_tokens': 1000, 'output_tokens': 10,
            'input_tokens_details': {'cached_tokens': 600, 'cache_write_tokens': 300}}}], 1)
        self.assertEqual(r['known_cached_input_tokens'], 600)
        self.assertEqual(r['known_cache_write_tokens'], 300)
        self.assertEqual(r['known_ordinary_input_tokens'], 100)
        self.assertTrue(r['complete_cache_usage'])

    def test_cli_cache_read_is_known_but_missing_write_is_not_zero(self):
        r = measure.provider([{'usage': {'input_tokens': 1000, 'cached_input_tokens': 800, 'output_tokens': 10}}], 1)
        self.assertEqual(r['known_cached_input_tokens'], 800)
        self.assertFalse(r['complete_cache_usage'])
        self.assertEqual(r['unknown_cache_usage_calls'], 1)
        self.assertIsNone(r['ordinary_input_tokens'])

    def test_invalid_cache_counts_and_failed_calls_remain_unknown(self):
        for details in [{'cached_tokens': 900, 'cache_write_tokens': 200},
                        {'cached_tokens': True, 'cache_write_tokens': 0}]:
            r = measure.provider([{'usage': {'input_tokens': 1000, 'output_tokens': 10,
                                            'input_tokens_details': details}}], 2)
            self.assertFalse(r['complete_cache_usage'])
            self.assertEqual(r['unknown_usage_calls'], 1)
            self.assertIsNone(r['ordinary_input_tokens'])


if __name__ == '__main__':
    unittest.main()
