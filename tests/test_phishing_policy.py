"""Defensive screening and classifier-contract tests; model replies are mocked."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from test_full_dataset import script
from phishbench.classification import CHAT_PROMPT, CRITERIA, INSTRUCTIONS
from phishbench.data import atomic_csv, read_csv, read_dataset
from phishbench.ollama_backend import Ollama, BackendError, parse_label
from phishbench.workflow import validate_curated_rows


class TestEnglishLengthPolicy(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.source=self.root/'raw.csv'
        raw=[dict(subject='Meeting update',body='agenda '*count,label=label,source='trec5',language='en')
             for count,label in ((100,'1'),(101,'1'),(101,'0'))]
        atomic_csv(self.source,raw,list(raw[0]))
        self.rows=read_dataset(self.source,label='1')
        self.curate=script('curate_meajor')
        self.args=SimpleNamespace(policy='english_length',provider='ollama',min_words=101,
                                  base_url='http://127.0.0.1:11435',timeout=10)
        self.english={'detected_language':'en','english_score':.99,'language_method':'langdetect'}

    def test_word_gate_uses_body_and_inclusive_threshold(self):
        short=copy.deepcopy(self.rows[0]);short['original_text']='Subject: '+('subject '*200)+'\n\n'+short['meajor_body']
        with patch.object(self.curate,'detect_english',return_value=self.english), patch.object(self.curate,'decision',return_value=('usable',.9)) as model:
            rejected=self.curate.annotate_row(short,self.args,'test',True)
            self.assertEqual(rejected['quality_reason'],'body_too_short')
            model.assert_not_called()
            accepted=self.curate.annotate_row(copy.deepcopy(self.rows[1]),self.args,'test',True)
            self.assertEqual(accepted['quality_accepted'],'1')
            self.assertEqual(accepted['body_word_count'],'101')
            self.assertEqual(model.call_count,1)

    def test_curator_judges_language_only(self):
        with patch.object(self.curate,'detect_english') as local_detector, patch.object(self.curate,'decision',return_value=('not_usable',.8)) as model:
            result=self.curate.annotate_row(copy.deepcopy(self.rows[1]),self.args,'test',True)
            self.assertEqual(result['language_screen'],'failed')
            self.assertEqual(result['quality_reason'],'english_requirement_failed')
            self.assertEqual(result['quality_accepted'],'0')
            self.assertEqual(model.call_args.args[3],self.rows[1]['meajor_body'])
            local_detector.assert_not_called()
        self.assertEqual(set(self.curate.CRITERIA),{'usable','not_usable'})
        self.assertIn('predominantly English',self.curate.CRITERIA['usable'])
        self.assertIn('Do not classify phishing intent',self.curate.INSTRUCTIONS)

    def test_curated_handoff_baseline_metrics_and_resume(self):
        dest=self.root/'curated'
        args=['curate','--input',str(self.source),'--output-dir',str(dest),'--provider','ollama']
        with patch.object(sys,'argv',args), patch.object(self.curate,'detect_english',return_value=self.english), patch.object(self.curate,'decision',return_value=('usable',.9)) as model:
            self.assertEqual(self.curate.main(),0)
            self.assertEqual(model.call_count,1)
        accepted=dest/'quality_accepted.csv'
        rows=read_csv(accepted)
        self.assertEqual(len(rows),1)
        validate_curated_rows(rows)
        self.assertEqual(rows[0]['dataset_label'],'1')
        freeze=script('freeze_approved');frozen=self.root/'frozen.csv'
        with patch.object(sys,'argv',['freeze','--input',str(self.source),'--audit',str(dest/'quality_audit.csv'),'--output',str(frozen)]):
            freeze.main()
        validate_curated_rows(read_csv(frozen))
        self.assertEqual(read_csv(frozen),rows)
        with patch.object(sys,'argv',args), patch.object(self.curate,'decision') as model, patch.object(self.curate,'detect_english') as detector:
            self.assertEqual(self.curate.main(),0)
            model.assert_not_called();detector.assert_not_called()
        self.assertEqual(rows,read_csv(accepted))
        with patch.object(sys,'argv',args+['--min-words','50']):
            with self.assertRaisesRegex(ValueError,'Manifest changed'):self.curate.main()
        baseline=script('run_baseline');config=self.root/'models.json';out=self.root/'baseline'
        config.write_text(json.dumps({'ollama_base_url':'http://127.0.0.1:11434','victims':[{'id':'test','tag':'test','kind':'decision','enabled':True}]}))
        with patch.object(sys,'argv',['baseline','--input',str(accepted),'--require-curated','--config',str(config),'--output-dir',str(out)]), patch.object(baseline,'Ollama') as backend:
            backend.return_value.classify_decision.return_value=SimpleNamespace(label=0,confidence=.8,probabilities={'PHISHING':.2,'NON_PHISHING':.8})
            baseline.main()
        result=read_csv(out/'test_baseline.csv')
        self.assertEqual(result[0]['decision_probability_phishing'],'0.2')
        metrics=script('baseline_metrics').metrics(rows,result)
        self.assertEqual(metrics['n_total'],1)
        self.assertEqual(metrics['fn'],1)  # Eligibility never depends on a victim predicting PHISHING.
        self.assertEqual(metrics['metric_scope'],'positive_only')

    def test_legacy_readability_cannot_pass_curated_guard(self):
        row=dict(self.rows[1],quality_accepted='1',quality_status='completed')
        with self.assertRaisesRegex(ValueError,'lacks complete'):validate_curated_rows([row])

    def test_chat_and_decision_share_phishing_task(self):
        captured=[]
        def transport(endpoint,payload):
            captured.append((endpoint,payload))
            if endpoint=='/api/chat':return {'message':{'content':'NON_PHISHING'}}
            return {'answers':{'email_class':{'choice':'PHISHING','probabilities':{'PHISHING':.8,'NON_PHISHING':.2}}}}
        client=Ollama(transport=transport)
        self.assertEqual(client.classify_chat('test','ordinary meeting notes',CHAT_PROMPT).label,0)
        decision=client.classify_decision('test','ordinary meeting notes')
        self.assertEqual(decision.label,1)
        question=captured[1][1]['questions']['email_class']
        self.assertEqual(question['instructions'],INSTRUCTIONS)
        self.assertEqual(question['criteria'],CRITERIA)
        for meaning in CRITERIA.values():self.assertIn(meaning,captured[0][1]['messages'][0]['content'])
        for old_label in ('SPAM','NOT_SPAM'):
            with self.assertRaises(BackendError):parse_label(old_label)


if __name__=='__main__':unittest.main()
