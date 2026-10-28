"""Authenticated direct decisions, transient failures and honest resume provenance."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from test_full_dataset import script
from phishbench import decision_api as api
from phishbench.data import atomic_csv,read_csv


class TestDecisionAPI(unittest.TestCase):
    def test_reset_and_timeout_retry_without_printing_key(self):
        reply={'answers':{'quality':{'choice':'usable','probabilities':{'usable':.8}}}}
        stderr=io.StringIO()
        with patch.object(api.urllib.request,'build_opener') as build, patch.object(api.time,'sleep') as sleep, contextlib.redirect_stderr(stderr):
            build.return_value.open.side_effect=[ConnectionResetError(10054,'reset'),TimeoutError(),io.StringIO(json.dumps(reply))]
            result=api.post_json('https://example.org/v1/systemone',{'state':'neutral data'},
                                 {'Authorization':'Bearer test-secret'},attempts=3)
            self.assertEqual(result,reply)
            self.assertEqual(build.return_value.open.call_count,3)
            self.assertEqual([c.args[0] for c in sleep.call_args_list],[1,2])
            self.assertNotIn('test-secret',stderr.getvalue())
            request=build.return_value.open.call_args.args[0]
            self.assertEqual(request.get_header('Authorization'),'Bearer test-secret')

    def test_auth_failure_is_not_retried_or_converted_to_a_decision(self):
        with patch.object(api.urllib.request,'build_opener') as build, patch.object(api.time,'sleep') as sleep:
            build.return_value.open.side_effect=urllib.error.HTTPError('https://example.org/v1/systemone',401,'unauthorized',{},None)
            with self.assertRaisesRegex(RuntimeError,'HTTP 401'):
                api.post_json('https://example.org/v1/systemone',{}, {},attempts=5)
            self.assertEqual(build.return_value.open.call_count,1)
            sleep.assert_not_called()

    def test_invalid_response_and_auth_redirect_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'chat text'):
            api.choice_answer({'choices':[{'message':{'content':'usable'}}]},'quality',{'usable':'English'})
        with self.assertRaisesRegex(ValueError,'probability'):
            api.choice_answer({'answers':{'q':{'choice':'a','probabilities':{'a':float('nan')}}}},'q',{'a':'A'})
        self.assertIsNone(api.NoRedirect().redirect_request(None,None,302,'redirect',{},'https://other.example/'))
        with patch.dict(os.environ,{'PPLX_API_KEY':'test-secret'}):
            for url in ('http://example.org/systemone','https://example.org/api/chat/completions',
                        'https://user:secret@example.org/systemone','https://example.org/systemone?key=secret'):
                with self.assertRaises(ValueError):api.authenticated_endpoint(url,'PPLX_API_KEY')

    def test_smoke_test_reports_actual_choice_and_probability(self):
        check=script('check_decider');output=io.StringIO()
        result={'answers':{'department':{'choice':'billing','confidence':.9,'probabilities':{'billing':.6}}}}
        argv=['check','--endpoint-url','https://example.org/v1/systemone','--model','test-decider']
        with patch.object(sys,'argv',argv),patch.dict(os.environ,{'PPLX_API_KEY':'test-secret'}),patch.object(check,'post_json',return_value=result),contextlib.redirect_stdout(output):
            self.assertEqual(check.main(),0)
        answer=json.loads(output.getvalue())
        self.assertEqual(answer['selected_option'],'billing')  # Never substitute a locally inferred answer.
        self.assertEqual(answer['probability'],.6)
        self.assertEqual(answer['confidence'],.9)

    def test_failed_smoke_test_reports_no_option(self):
        check=script('check_decider');output=io.StringIO();error=io.StringIO()
        argv=['check','--endpoint-url','https://example.org/v1/systemone','--model','test-decider']
        with patch.object(sys,'argv',argv),patch.dict(os.environ,{'PPLX_API_KEY':'test-secret'}),patch.object(check,'post_json',side_effect=RuntimeError('HTTP 401')),contextlib.redirect_stdout(output),contextlib.redirect_stderr(error):
            self.assertEqual(check.main(),1)
        self.assertEqual(output.getvalue(),'')
        self.assertIn('HTTP 401',error.getvalue())


class TestRemoteCuration(unittest.TestCase):
    def test_only_length_prechecks_migrate_and_remote_run_resumes(self):
        curate=script('curate_meajor')
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'input.csv';old=root/'old';new=root/'new'
            data=[dict(subject='Agenda',body='meeting '*n,label=label,source='test') for n,label in ((32,'1'),(110,'1'),(110,'0'))]
            atomic_csv(source,data,list(data[0]))
            base=['curate','--input',str(source),'--policy','english_length']
            with patch.object(sys,'argv',base+['--provider','ollama','--output-dir',str(old)]),patch.object(curate,'decision',return_value=('usable',.8)):
                self.assertEqual(curate.main(),0)
            before={p.name:p.read_bytes() for p in old.iterdir()}
            args=base+['--provider','decider','--model','remote-test','--endpoint-url','https://example.org/v1/systemone',
                       '--output-dir',str(new),'--resume-prechecks-from',str(old)]
            with patch.dict(os.environ,{'PPLX_API_KEY':'test-secret'}),patch.object(sys,'argv',args),patch.object(curate,'decision',return_value=('usable',.9)) as model:
                self.assertEqual(curate.main(),0)
                self.assertEqual(model.call_count,1)  # Old model decision is recomputed, label 0 is excluded.
            audit=read_csv(new/'quality_audit.csv')
            self.assertEqual(len(audit),2)
            self.assertEqual({r['dataset_label'] for r in audit},{'1'})
            self.assertEqual([r['quality_provider'] for r in audit],['precheck','decider'])
            self.assertEqual(before,{p.name:p.read_bytes() for p in old.iterdir()})
            self.assertNotIn('test-secret',(new/'quality_manifest.json').read_text())
            with patch.dict(os.environ,{'PPLX_API_KEY':'test-secret'}),patch.object(sys,'argv',args),patch.object(curate,'decision') as model:
                self.assertEqual(curate.main(),0)
                model.assert_not_called()
            with patch.dict(os.environ,{'PPLX_API_KEY':'test-secret'}),patch.object(sys,'argv',args+['--endpoint-url','https://example.org/other/systemone']):
                with self.assertRaisesRegex(ValueError,'Manifest changed'):curate.main()

    def test_active_policy_rejects_label_override_before_requests(self):
        curate=script('curate_meajor')
        for label in ('0','all'):
            argv=['curate','--input','unused.csv','--output-dir','unused','--provider','ollama','--label',label]
            with patch.object(sys,'argv',argv),patch.object(curate,'decision') as model,contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:curate.main()
                self.assertEqual(error.exception.code,2)
                model.assert_not_called()


if __name__=='__main__':unittest.main()
