"""Regression coverage for project dependencies, evidence provenance and accounting."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

from shared import repo_context as rc, evidence as ev
from shared import jev
from desktop import context as dc
import measure


def fake_response(payload):
    value = {'model': jev.JEV_MODEL, 'usage': {'input_tokens': 100, 'output_tokens': 10},
             'answers': {key: {'type': 'noul', 'noul': .01} for key in payload['questions']}}
    return value, {'model': jev.JEV_MODEL, 'usage': value['usage'], 'seconds': .1,
                   'request_sha256': jev.request_hash(payload), 'reused': False}


class DependencyTests(unittest.TestCase):
    def test_src_layout_absolute_and_namespace_imports(self):
        files = {'src/pkg/main.py': 'from pkg.helper import run\nimport pkg.other',
                 'src/pkg/helper.py': 'from .deep import value', 'src/pkg/deep.py': 'value=1',
                 'src/pkg/other.py': 'pass', 'noise.py': 'pass'}
        self.assertEqual(rc.dependencies(files, ['src/pkg/main.py']), sorted(set(files)-{'noise.py'}))

    def test_inherited_jsonc_alias_and_mts(self):
        files = {'tsconfig.json': '{"compilerOptions":{"baseUrl":".","paths":{"@/*":["src/*"]}}}',
                 'src/tsconfig.json': '{// comment\n"extends":"../tsconfig.json",}',
                 'src/main.mts': 'import { run } from "@/helper.js"',
                 'src/helper.ts': 'export const run = 1'}
        self.assertIn('src/helper.ts', rc.dependencies(files, ['src/main.mts']))
        self.assertIsNone(rc.eligibility('src/main.mts'))

    def test_workspace_package_and_bad_config_are_conservative(self):
        files = {'apps/a.ts': 'import {x} from "@local/lib"',
                 'packages/lib/package.json': '{"name":"@local/lib"}',
                 'packages/lib/src/x.ts': 'export const x=1'}
        self.assertIn('packages/lib/src/x.ts', rc.dependencies(files, ['apps/a.ts']))
        files = {'tsconfig.json': '{bad', 'main.ts': 'import x from "@/x"', 'x.ts': 'export default 1'}
        self.assertIn('x.ts', rc.dependencies(files, ['main.ts']))


class RepoFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root/'repo'
        self.repo.mkdir()
        for args in [('init','-q'),('config','user.name','Fixture'),('config','user.email','fixture@example.invalid')]:
            rc.git(self.repo,*args)
        (self.repo/'main.py').write_text('value=1\n')
        rc.git(self.repo,'add','.')
        rc.git(self.repo,'commit','-qm','fixture')

    def test_explicit_untracked_is_included_without_staging_and_freshness_checked(self):
        (self.repo/'new.py').write_text('value=2\n')
        before = rc.git(self.repo,'status','--porcelain')
        plan = dc.make_plan(self.repo,'Fix value',self.root/'plan',['new.py'])
        self.assertIn('new.py',plan['files'])
        self.assertEqual(before,rc.git(self.repo,'status','--porcelain'))
        (self.repo/'new.py').write_text('value=3\n')
        with self.assertRaises(jev.ProtocolError):
            dc.fresh(plan)

    def test_ignored_and_secret_explicit_includes_refused(self):
        (self.repo/'.gitignore').write_text('ignored.py\n')
        (self.repo/'ignored.py').write_text('pass')
        (self.repo/'secret.py').write_text('key="apikey_'+'x'*45+'"')
        for name in ['ignored.py','secret.py','../escape.py']:
            with self.subTest(name=name), self.assertRaises(jev.ProtocolError):
                rc.snapshot(self.repo,'Fix',self.root/name.replace('/','_'),include_paths=[name])

    def test_desktop_cache_has_no_live_calls_and_source_changes_invalidate_it(self):
        plan_dir=self.root/'plan'; cache=self.root/'cache'
        dc.make_plan(self.repo,'Fix value',plan_dir)
        with patch.object(rc,'request_jev',side_effect=fake_response) as provider, \
                patch.object(dc,'execution_environment',return_value=({'TYPESAFE_API_KEY':'fixture'},'fixture')):
            first=dc.select(plan_dir,self.root/'first',1,cache_dir=cache)
        self.assertEqual(provider.call_count,1)
        with patch.object(rc,'request_jev',side_effect=AssertionError('No network')), \
                patch.object(dc,'execution_environment',side_effect=AssertionError('No keychain')):
            second=dc.select(plan_dir,self.root/'second',1,cache_dir=cache)
        self.assertEqual(first['attempted_calls'],1)
        self.assertEqual(second['attempted_calls'],0)
        self.assertTrue(second['jev_calls'][0]['reused'])
        (self.repo/'main.py').write_text('value=2\n')
        dc.make_plan(self.repo,'Fix value',self.root/'next-plan')
        with patch.object(rc,'request_jev',side_effect=fake_response) as provider, \
                patch.object(dc,'execution_environment',return_value=({'TYPESAFE_API_KEY':'fixture'},'fixture')):
            dc.select(self.root/'next-plan',self.root/'next',1,cache_dir=cache)
        self.assertEqual(provider.call_count,1)

    def test_failure_record_preserves_status_not_provider_message(self):
        dc.make_plan(self.repo,'Fix',self.root/'plan')
        error=jev.ProtocolError('PRIVATE BODY',error_kind='http_error',http_status=403,seconds=.1)
        with patch.object(rc,'call_jev',side_effect=error), \
                patch.object(dc,'execution_environment',return_value=({'TYPESAFE_API_KEY':'fixture'},'fixture')):
            with self.assertRaises(jev.ProtocolError):
                dc.select(self.root/'plan',self.root/'failed',1)
        record=json.loads((self.root/'failed/selection.json').read_text())
        self.assertEqual(record['failure']['http_status'],403)
        self.assertEqual(record['attempted_calls'],1)
        self.assertNotIn('PRIVATE BODY',json.dumps(record))

    def test_cli_failure_records_attempt_and_diagnostic(self):
        from cli import coding
        rc.snapshot(self.repo,'Fix',self.root/'plan')
        error=jev.ProtocolError('safe failure',error_kind='http_error',http_status=429)
        with patch.object(rc,'call_jev',side_effect=error), \
                patch.object(coding,'read_model_settings',return_value={'model': None, 'reasoning': None}):
            r=coding.run(self.root/'plan',self.root/'run','jev',None,2)
        self.assertEqual(r['attempted_jev_calls'],1)
        self.assertEqual(r['attempted_astra_calls'],0)
        self.assertEqual(r['failure']['http_status'],429)
        self.assertEqual(r['failure']['stage'],'context_selection')

    def test_evidence_artifacts_and_cache_refuse_unrelated_git_repo(self):
        source = self.root/'status.json'
        source.write_text('{"status":"failed"}')
        with self.assertRaises(jev.ProtocolError):
            ev.make_plan('Fix', [], [source], self.repo/'evidence-plan')
        self.assertFalse((self.repo/'evidence-plan').exists())
        ev.make_plan('Fix', [], [source], self.root/'evidence-plan')
        with self.assertRaises(jev.ProtocolError):
            ev.select(self.root/'evidence-plan', self.root/'evidence-run', 0,
                      cache_dir=self.repo/'evidence-cache')
        self.assertFalse((self.repo/'evidence-cache').exists())

    def test_evidence_attaches_to_desktop_and_invalidation_follows_source(self):
        source=self.root/'status.json';source.write_text('{"status":"failed"}')
        ev.make_plan('Fix',[],[source],self.root/'eplan')
        ev.select(self.root/'eplan',self.root/'evidence',0)
        dc.make_plan(self.repo,'Fix',self.root/'plan')
        with patch.object(rc,'call_jev',return_value={'probabilities':{'main.py':.9}}), \
                patch.object(dc,'execution_environment',return_value=({'TYPESAFE_API_KEY':'fixture'},'fixture')):
            dc.select(self.root/'plan',self.root/'run',1,evidence_dir=self.root/'evidence')
        packet=json.loads((self.root/'run/context.json').read_text())['evidence']
        self.assertEqual(packet['fragments'][0]['text'],source.read_text())
        dc.check(self.root/'run')
        source.write_text('{"status":"changed"}')
        with self.assertRaises(jev.ProtocolError):
            dc.check(self.root/'run')

    def test_evidence_task_mismatch_stops_before_model(self):
        from cli import coding
        source=self.root/'status.json';source.write_text('{"status":"failed"}')
        ev.make_plan('Other task',[],[source],self.root/'eplan')
        ev.select(self.root/'eplan',self.root/'evidence',0)
        rc.snapshot(self.repo,'Fix',self.root/'plan')
        with patch.object(coding,'generate') as generate, self.assertRaises(jev.ProtocolError):
            coding.run(self.root/'plan',self.root/'run','astra',None,2,evidence_dir=self.root/'evidence')
        generate.assert_not_called()


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.noise=self.root/'noise.txt';self.noise.write_text('ordinary unrelated data\n'*200)
        self.pin=self.root/'status.json';self.pin.write_text('{"status":"failed","usage":null}\n')
        ev.make_plan('Fix failing validation',[self.noise],[self.pin],self.root/'plan')

    def test_keeps_pinned_failure_and_exact_quotes_and_reuses_without_credentials(self):
        with patch.object(ev,'request_jev',side_effect=fake_response), \
                patch.object(ev,'execution_environment',return_value=({'TYPESAFE_API_KEY':'fixture'},'fixture')):
            record=ev.select(self.root/'plan',self.root/'run',4,self.root/'cache')
        packet=ev.check(self.root/'run')
        self.assertEqual(len(packet['fragments']),1)
        self.assertEqual(packet['fragments'][0]['text'],self.pin.read_text())
        self.assertEqual(packet['fragments'][0]['start_line'],1)
        self.assertLess(record['selected_bytes'],record['candidate_bytes'])
        with patch.object(ev,'request_jev',side_effect=AssertionError('No API')), \
                patch.object(ev,'execution_environment',side_effect=AssertionError('No credentials')):
            replay=ev.select(self.root/'plan',self.root/'replay',0,self.root/'cache')
        self.assertEqual(replay['attempted_calls'],0)
        self.noise.write_text('changed')
        with self.assertRaises(jev.ProtocolError):
            ev.check(self.root/'run')

    def test_uncertainty_and_conflict_keep_source_neighbors(self):
        plan=ev.load_plan(self.root/'plan')
        scores={f['id']:{'relevant':.01,'conflict':.01,'review':.01} for f in plan['fragments']}
        scores['e2']['conflict']=.7
        kept={f['id'] for f in ev.resolve(plan,scores)}
        self.assertTrue({'e1','e2','e3'} <= kept)

    def test_cap_refuses_before_provider_and_tampered_excerpt_is_rejected(self):
        with patch.object(ev,'request_jev') as provider, self.assertRaises(jev.ProtocolError):
            ev.select(self.root/'plan',self.root/'out',0)
        provider.assert_not_called()
        plan=json.loads((self.root/'plan/plan.json').read_text())
        plan['fragments'][0]['text']='fabricated'
        ev.save(self.root/'plan/plan.json',plan)
        with self.assertRaises(jev.ProtocolError):
            ev.load_plan(self.root/'plan')

    def test_failed_request_is_recorded_and_no_packet_created(self):
        with patch.object(ev,'request_jev',side_effect=jev.ProtocolError('private',error_kind='timeout')) as provider, \
                patch.object(ev,'execution_environment',return_value=({'TYPESAFE_API_KEY':'fixture'},'fixture')):
            with self.assertRaises(jev.ProtocolError):
                ev.select(self.root/'plan',self.root/'out',4)
        r=json.loads((self.root/'out/selection.json').read_text())
        self.assertEqual(provider.call_count,1)
        self.assertEqual(r['failure']['error_kind'],'timeout')
        self.assertEqual(r['attempted_calls'],1)
        self.assertFalse((self.root/'out/packet.json').exists())

    def test_credentials_and_oversized_lines_not_sent(self):
        for value in ['apikey_'+'x'*45, 'x'*4001]:
            source=self.root/'unsafe.log';source.write_text(value)
            with self.assertRaises(jev.ProtocolError):
                ev.make_plan('Fix',[source],[],self.root/'unsafe-plan')

    def test_packet_tampering_rejected(self):
        with patch.object(ev,'request_jev',side_effect=fake_response), \
                patch.object(ev,'execution_environment',return_value=({'TYPESAFE_API_KEY':'fixture'},'fixture')):
            ev.select(self.root/'plan',self.root/'run',4)
        (self.root/'run/packet.json').write_text('{}')
        with self.assertRaises(jev.ProtocolError):
            ev.check(self.root/'run')


class UsageTests(unittest.TestCase):
    def test_unknown_failed_calls_not_zero_and_cache_not_double_charged(self):
        calls=[{'usage':{'input_tokens':100,'output_tokens':10}}, {'reused':True,'usage':None}]
        r=measure.provider(calls,2)
        self.assertEqual(r['unknown_usage_calls'],1)
        self.assertEqual(r['known_input_tokens'],100)
        self.assertFalse(r['complete_usage'])
        self.assertIsNone(measure.provider([],None)['unknown_usage_calls'])

    def test_measure_combines_auxiliary_evidence_without_losing_cli_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            run={'attempted_astra_calls':1,'astra_calls':[{'usage':{'input_tokens':100,'output_tokens':10}}],
                 'attempted_jev_calls':0,'seconds':1,'status':'verified'}
            aux={'kind':'evidence_selection','attempted_calls':1,'jev_calls':[{'usage':{'input_tokens':50,'output_tokens':5}}],
                 'seconds':.1,'status':'selected'}
            for name,data in [('run',run),('aux',aux)]:
                (root/name).write_text(json.dumps(data))
            both=measure.summarize([root/'run',root/'aux'])
            self.assertTrue(both['astra']['complete_usage'])
            self.assertEqual(both['astra']['known_input_tokens'],100)
            self.assertFalse(measure.summarize([root/'aux'])['astra']['complete_usage'])

    def test_subprocess_timeout_preserves_partial_output(self):
        from cli.coding import bounded_process
        with tempfile.TemporaryDirectory() as cwd, self.assertRaises(jev.ProtocolError) as caught:
            bounded_process([sys.executable,'-u','-c','import time; print("progress"); time.sleep(5)'],
                            cwd,os.environ.copy(),.15)
        self.assertEqual(caught.exception.diagnostic['error_kind'],'timeout')
        self.assertIn('progress',caught.exception.partial_output['stdout'])

    def test_http_failure_diagnostic_and_invalid_model(self):
        payload=jev.jev_request({'task':'Fix','files':{'a.py':'pass'}})
        with patch.dict(os.environ,{'TYPESAFE_API_KEY':'PRIVATE'}), patch.object(jev.urllib.request,'build_opener') as opener:
            opener.return_value.open.side_effect=urllib.error.HTTPError('https://api.typesafe.ai',403,'PRIVATE',{},None)
            with self.assertRaises(jev.ProtocolError) as caught:
                jev.request_jev(payload)
        r=jev.failure_record(caught.exception,'selection')
        self.assertEqual(r['http_status'],403)
        self.assertNotIn('PRIVATE',json.dumps(r))
        value,_=fake_response(payload);value['model']='unexpected'
        with self.assertRaises(jev.ProtocolError):
            jev.validate_response(payload,value)


if __name__=='__main__':
    unittest.main()
