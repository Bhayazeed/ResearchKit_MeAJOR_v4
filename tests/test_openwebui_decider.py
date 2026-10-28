import copy
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_full_dataset import script
from phishbench import openwebui_decider as webui
from phishbench.data import atomic_csv,read_csv


class TestWebUIToolEvidence(unittest.TestCase):
    def setUp(self):
        self.expected={'state':'Neutral meeting notes','questions':{'quality':{
            'type':'choice','instructions':'Check English only','criteria':{'usable':'English','not_usable':'Other'}}}}
        self.result={'answers':{'quality':{'choice':'usable','probabilities':{'usable':.8}}}}
        self.response={
            'choices':[{'message':{'content':'This prose is deliberately not the decision.'}}],
            'sources':[{
                'source':{'name':'server:pplxdeciderflash/pplxdeciderflash_systemone'},
                'tool_result':True,'metadata':[{'parameters':copy.deepcopy(self.expected)}],
                'document':[json.dumps(self.result)],
            }],
        }

    def wrapper_fixture(self):
        response=json.loads((Path(__file__).parent/'fixtures/openwebui_pplx_wrapped.json').read_text(encoding='utf-8'))
        check=script('check_decider')
        expected={'state':'A customer reports HTTP 401 errors after rotating their API credentials.',
                  'questions':{'department':{'type':'choice','instructions':'Which department should handle the issue?',
                                             'criteria':check.CRITERIA}}}
        return response,expected

    def test_actual_server_wrapper_response_preserves_probability_and_provenance(self):
        response,expected=self.wrapper_fixture()
        result,evidence=webui.extract_decision(response,expected,'server:pplxdeciderflash')
        answer=result['answers']['department']
        self.assertEqual(answer['choice'],'technical')
        self.assertEqual(answer['probabilities']['technical'],0.9991184698158921)
        self.assertEqual(answer['confidence'],0.9986777047238382)
        original=json.loads(response['sources'][0]['document'][0])
        self.assertEqual(answer,original['answers']['decision'])
        self.assertEqual(evidence['decision_tool_result_sha256'],webui.digest(original))
        self.assertEqual(evidence['decision_tool_question_mapping'],'decision->department')

    def test_saved_server_response_passes_complete_smoke_test_without_network(self):
        check=script('check_decider');response,_=self.wrapper_fixture();output=io.StringIO()
        with patch.object(sys,'argv',['check','--transport','openwebui']),patch.dict(os.environ,{'OPENWEBUI_API_KEY':'test-secret'}),patch.object(webui,'post_json',return_value=response),contextlib.redirect_stdout(output):
            self.assertEqual(check.main(),0)
        report=json.loads(output.getvalue())
        self.assertEqual(report['selected_option'],'technical')
        self.assertEqual(report['probability'],0.9991184698158921)

    def test_flat_wrapper_rejects_changed_inputs_ambiguous_answers_and_multiple_questions(self):
        response,expected=self.wrapper_fixture()
        for field in ('state','instructions','criteria'):
            altered=copy.deepcopy(response)
            altered['sources'][0]['metadata'][0]['parameters'][field]='changed'
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'arguments differ'):
                webui.extract_decision(altered,expected,'server:pplxdeciderflash')
        altered=copy.deepcopy(response)
        altered['sources'][0]['document']=[json.dumps({'answers':{'department':{'choice':'technical'}}})]
        with self.assertRaisesRegex(ValueError,'exactly answers.decision'):
            webui.extract_decision(altered,expected,'server:pplxdeciderflash')
        multiple=copy.deepcopy(expected);multiple['questions']['other']=multiple['questions']['department']
        with self.assertRaisesRegex(ValueError,'exactly one choice question'):
            webui.extract_decision(response,multiple,'server:pplxdeciderflash')

    def test_flat_wrapper_maps_quality_question_without_changing_eligibility(self):
        response,_=self.wrapper_fixture();expected=copy.deepcopy(self.expected)
        question=expected['questions']['quality']
        response['sources'][0]['metadata'][0]['parameters']={
            'state':expected['state'],'instructions':question['instructions'],'criteria':question['criteria']}
        answer={'type':'choice','choice':'not_usable','confidence':.9,'probabilities':{'usable':.1,'not_usable':.9}}
        response['sources'][0]['document']=[json.dumps({'answers':{'decision':answer}})]
        result,evidence=webui.extract_decision(response,expected,'server:pplxdeciderflash')
        self.assertEqual(result['answers']['quality'],answer)
        self.assertEqual(evidence['decision_tool_question_mapping'],'decision->quality')

    def test_argument_mismatch_retries_identical_request_and_records_attempts(self):
        response,expected=self.wrapper_fixture()
        wrong=copy.deepcopy(response)
        wrong['sources'][0]['metadata'][0]['parameters']['state']='unexpected state'
        with patch.dict(os.environ,{'OPENWEBUI_API_KEY':'test-secret'}),patch.object(webui,'post_json',side_effect=[wrong,response]) as post,patch.object(webui.time,'sleep'),contextlib.redirect_stderr(io.StringIO()):
            result,evidence=webui.request_decision('https://llms.si-lab.org','openai/gpt-oss-120b','server:pplxdeciderflash',expected)
        self.assertEqual(result['answers']['department']['choice'],'technical')
        self.assertEqual(evidence['decision_tool_validation_attempts'],2)
        self.assertEqual(post.call_args_list[0],post.call_args_list[1])

    def test_argument_retry_does_not_repeat_auth_failures(self):
        with patch.dict(os.environ,{'OPENWEBUI_API_KEY':'test-secret'}),patch.object(webui,'post_json',side_effect=RuntimeError('Decision HTTP 401')) as post,patch.object(webui.time,'sleep') as sleep:
            with self.assertRaisesRegex(RuntimeError,'401'):
                webui.request_decision('https://llms.si-lab.org','openai/gpt-oss-120b','server:pplxdeciderflash',self.expected)
        self.assertEqual(post.call_count,1)
        sleep.assert_not_called()

    def test_exhausted_mismatch_saves_diagnostic_without_checkpointing_failed_row(self):
        curate=script('curate_meajor')
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'input.csv';dest=root/'output'
            data=[dict(subject='Agenda',body='meeting '*110,label='1',source='test')]
            atomic_csv(source,data,list(data[0]))
            response,_=self.wrapper_fixture()
            response['sources'][0]['metadata'][0]['parameters']={
                'state':'do-not-log-this-raw-text','instructions':curate.INSTRUCTIONS,'criteria':curate.CRITERIA}
            response['sources'][0]['document']=[json.dumps({'answers':{'decision':{'choice':'usable','confidence':.8}}})]
            args=['curate','--input',str(source),'--output-dir',str(dest),'--provider','openwebui']
            with patch.dict(os.environ,{'OPENWEBUI_API_KEY':'test-secret'}),patch.object(sys,'argv',args),patch.object(webui,'post_json',return_value=response) as post,patch.object(webui.time,'sleep'),contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(curate.main(),1)
                self.assertEqual(post.call_count,3)
            self.assertFalse((dest/'quality_checkpoint.jsonl').exists())
            diagnostic=json.loads((dest/'quality_last_error.json').read_text())
            self.assertEqual(diagnostic['diagnostics']['attempts'],3)
            self.assertEqual(set(diagnostic['diagnostics']['failures'][0]['changed_fields']),{'state'})
            self.assertNotIn('do-not-log-this-raw-text',json.dumps(diagnostic))
            self.assertNotIn('test-secret',json.dumps(diagnostic))
            # Fixing the response resumes the same manifest and records this row once.
            response['sources'][0]['metadata'][0]['parameters']['state']=data[0]['body']
            with patch.dict(os.environ,{'OPENWEBUI_API_KEY':'test-secret'}),patch.object(sys,'argv',args),patch.object(webui,'post_json',return_value=response) as post:
                self.assertEqual(curate.main(),0)
                self.assertEqual(post.call_count,1)
            self.assertEqual(len(read_csv(dest/'quality_accepted.csv')),1)

    def test_uses_verified_tool_result_and_exact_example_transport(self):
        with patch.dict(os.environ,{'OPENWEBUI_API_KEY':'test-secret'}),patch.object(webui,'post_json',return_value=self.response) as post:
            result,evidence=webui.request_decision('https://llms.si-lab.org','openai/gpt-oss-120b',
                                                 'server:pplxdeciderflash',self.expected)
        self.assertEqual(result,self.result)
        url,body,headers=post.call_args.args[:3]
        self.assertEqual(url,'https://llms.si-lab.org/api/chat/completions')
        self.assertEqual(body['model'],'openai/gpt-oss-120b')
        self.assertEqual(body['params'],{'function_calling':'legacy'})
        self.assertEqual(body['tool_ids'],['server:pplxdeciderflash'])
        self.assertFalse(body['stream'])
        self.assertEqual(json.loads(body['messages'][1]['content']),self.expected)
        self.assertEqual(evidence['decision_tool_result_sha256'],webui.digest(self.result))

    def test_chat_only_unexecuted_calls_wrong_tool_and_modified_input_fail(self):
        cases=[]
        chat_only=copy.deepcopy(self.response);chat_only.pop('sources')
        chat_only['choices'][0]['message']['content']=json.dumps(self.result)
        chat_only['choices'][0]['message']['tool_calls']=[{'function':{'name':'systemone'}}]
        cases.append(chat_only)
        wrong=copy.deepcopy(self.response);wrong['sources'][0]['source']['name']='server:other/systemone';cases.append(wrong)
        changed=copy.deepcopy(self.response);changed['sources'][0]['metadata'][0]['parameters']['state']='rewritten';cases.append(changed)
        changed=copy.deepcopy(self.response);changed['sources'][0]['metadata'][0]['parameters']['questions']['quality']['instructions']='Classify something else';cases.append(changed)
        duplicate=copy.deepcopy(self.response);duplicate['sources']*=2;cases.append(duplicate)
        failed=copy.deepcopy(self.response);failed['sources'][0]['document']=[json.dumps({'error':'backend unavailable'})];cases.append(failed)
        for response in cases:
            with self.subTest(response=response),self.assertRaises(ValueError):
                webui.extract_decision(response,self.expected,'server:pplxdeciderflash')

    def test_resume_same_backend_preserves_model_decisions_and_only_calls_remaining(self):
        curate=script('curate_meajor')
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'input.csv';old=root/'old';new=root/'new'
            data=[dict(subject='Agenda',body='meeting '*n,label=label,source='test')
                  for n,label in ((32,'1'),(110,'1'),(120,'1'),(110,'0'))]
            atomic_csv(source,data,list(data[0]))
            base=['curate','--input',str(source),'--policy','english_length']
            with patch.object(sys,'argv',base+['--provider','ollama','--output-dir',str(old)]),patch.object(curate,'decision',side_effect=[('usable',.8),RuntimeError('offline')]):
                self.assertEqual(curate.main(),1)
            before={p.name:p.read_bytes() for p in old.iterdir()}
            args=base+['--provider','openwebui','--output-dir',str(new),'--resume-from',str(old),'--same-decider-backend']
            trace={'decision_tool_source':'server:pplxdeciderflash/systemone',
                   'decision_tool_arguments_sha256':'test-args-hash','decision_tool_result_sha256':'test-result-hash'}
            with patch.dict(os.environ,{'OPENWEBUI_API_KEY':'test-secret'}),patch.object(sys,'argv',args),patch.object(curate,'webui_decision',return_value=(self.result,trace)) as model:
                self.assertEqual(curate.main(),0)
                self.assertEqual(model.call_count,1)
            rows=read_csv(new/'quality_audit.csv')
            self.assertEqual(len(rows),3)
            self.assertEqual({r['dataset_label'] for r in rows},{'1'})
            self.assertEqual([r['quality_provider'] for r in rows],['precheck','ollama','openwebui'])
            self.assertEqual(rows[-1]['decision_tool_result_sha256'],'test-result-hash')
            self.assertEqual(rows[-1]['decision_orchestrator'],'openai/gpt-oss-120b')
            self.assertEqual(before,{p.name:p.read_bytes() for p in old.iterdir()})
            manifest=json.loads((new/'quality_manifest.json').read_text())
            self.assertTrue(manifest['checkpoint_import']['same_decider_backend_confirmed_by_operator'])
            self.assertNotIn('test-secret',json.dumps(manifest))
            with patch.dict(os.environ,{'OPENWEBUI_API_KEY':'test-secret'}),patch.object(sys,'argv',args),patch.object(curate,'webui_decision') as model:
                self.assertEqual(curate.main(),0)
                model.assert_not_called()


if __name__=='__main__':unittest.main()
