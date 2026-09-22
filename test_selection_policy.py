"""Policy quality boundaries, without changing live model probabilities."""
import unittest
from unittest.mock import patch
from shared import repo_context as rc


def plan(files):
    return {'task': 'fix pagination', 'files': {p: {'content': s} for p, s in files.items()}, 'excluded': {'.env': 'credential_or_database_file'}}


def call(values):
    return {'probabilities': values}


class SelectionPolicyTests(unittest.TestCase):
    def setUp(self):
        self.plan = plan({'main.py': 'import helper\n', 'helper.py': 'value=1\n',
                          'maybe.py': 'pass\n', 'noise.py': 'pass\n', 'AGENTS.md': 'Follow task scope.\n'})
        self.calls = [call({'main.py': .9, 'helper.py': .02, 'maybe.py': .5, 'noise.py': .01, 'AGENTS.md': .01})]

    def test_per_file_keeps_uncertainty_dependencies_and_guidance_but_drops_noise(self):
        old = rc.resolve_selection(self.plan, self.calls)
        new = rc.resolve_selection(self.plan, self.calls, policy='per-file')
        self.assertIn('noise.py', old['paths'])
        self.assertEqual(new['paths'], ['AGENTS.md', 'helper.py', 'main.py', 'maybe.py'])
        self.assertIn('guidance_or_dependency', new['decisions']['helper.py']['reasons'])
        self.assertEqual(new['decisions']['maybe.py']['judgment'], 'uncertain')
        self.assertEqual(new['decisions']['noise.py']['probability'], .01)
        self.assertFalse(new['decisions']['noise.py']['kept'])
        self.assertLess(new['metrics']['selected_bytes'], old['metrics']['selected_bytes'])

    def test_unjudged_files_are_retained_and_never_reported_as_judged(self):
        result = rc.resolve_selection(self.plan, [call({'main.py': .9})], policy='per-file')
        self.assertEqual(set(result['unjudged_paths']), set(self.plan['files']) - {'main.py'})
        self.assertTrue(set(result['unjudged_paths']) <= set(result['paths']))
        self.assertIsNone(result['decisions']['noise.py']['probability'])
        self.assertEqual(result['metrics']['judged_files'], 1)
        self.assertEqual(result['metrics']['excluded_files'], 1)

    def test_empty_global_match_keeps_everything(self):
        for policy in ['batch', 'per-file']:
            result = rc.resolve_selection(self.plan, [call({p: .01 for p in self.plan['files']})], policy)
            self.assertEqual(set(result['paths']), set(self.plan['files']))
            self.assertIn('global_no_match', result['decisions']['noise.py']['reasons'])

    def test_probability_boundaries_and_no_fabricated_usage(self):
        p = plan({'yes.py': 'pass', 'no.py': 'pass', 'uncertain.py': 'pass'})
        result = rc.resolve_selection(p, [call({'yes.py': .8, 'no.py': .2, 'uncertain.py': .20001})], 'per-file')
        self.assertEqual(result['paths'], ['uncertain.py', 'yes.py'])
        self.assertEqual(result['decisions']['yes.py']['judgment'], 'relevant')
        self.assertNotIn('usage', result['metrics'])

    def test_duplicate_unknown_invalid_scores_and_unknown_policy_are_rejected(self):
        for calls in [[call({'no-such.py': .9})], [call({'main.py': .9}), call({'main.py': .9})],
                      [call({'main.py': float('nan')})], [call({'main.py': True})], [call({'main.py': 2})]]:
            with self.subTest(calls=calls), self.assertRaises(rc.ProtocolError):
                rc.resolve_selection(self.plan, calls)
        with self.assertRaises(rc.ProtocolError):
            rc.resolve_selection(self.plan, self.calls, 'guess')

    def test_policy_rejected_before_live_call(self):
        with patch.object(rc, 'call_jev') as provider, self.assertRaises(rc.ProtocolError):
            rc.select(self.plan, 'jev', policy='guess')
        provider.assert_not_called()

    def test_no_provider_data_preserves_all_context(self):
        result = rc.resolve_selection(self.plan, [], 'per-file')
        self.assertEqual(set(result['paths']), set(self.plan['files']))
        self.assertEqual(result['metrics']['judged_files'], 0)


if __name__ == '__main__':
    unittest.main()
