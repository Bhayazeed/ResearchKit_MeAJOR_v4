"""Regression coverage for complete raw datasets and resumable curation."""
import csv
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from phishbench.data import read_csv, read_dataset


def script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestFullDataset(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'raw.csv'
        self.original = [
            {'subject': 'Office update', 'body': 'The meeting is scheduled for tomorrow. Please read the attached notes. ' * 15,
             'label': '0.0', 'source': 'trec5', 'language': 'de', 'sender': 'sender_hash'},
            {'subject': '', 'body': '', 'label': 'invalid', 'source': 'trec6', 'language': '', 'sender': ''},
            {'subject': 'Brief', 'body': 'hi', 'label': '1', 'source': 'trec7', 'language': 'fr', 'sender': ''},
        ]
        # Identical email, distinct record and gold label: never deduplicate.
        self.original.append(dict(self.original[0], label='1'))
        with self.source.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(self.original[0]))
            writer.writeheader()
            writer.writerows(self.original)

    def test_adapter_keeps_all_rows_and_metadata(self):
        rows = read_dataset(self.source)
        self.assertEqual(len(rows), 4)
        self.assertEqual(len({r['row_id'] for r in rows}), 4)
        self.assertEqual(rows, read_dataset(self.source))
        self.assertEqual(rows[0]['original_sha256'], rows[3]['original_sha256'])
        self.assertEqual([r['dataset_label'] for r in rows], ['0', '', '1', '1'])
        self.assertEqual(rows[1]['dataset_label_status'], 'invalid')
        self.assertEqual(rows[1]['original_text'], '')
        for row, original in zip(rows, self.original):
            for key, value in original.items():
                self.assertEqual(row['meajor_' + key], value)

    def test_pplx_interruption_resume_and_manifest(self):
        curate = script('curate_meajor')
        dest = self.root / 'quality'
        args = ['curate', '--input', str(self.source), '--output-dir', str(dest), '--provider', 'ollama', '--policy', 'readability', '--label', 'all']
        with patch.object(sys, 'argv', args), patch.object(curate, 'decision', side_effect=[('usable', .9), RuntimeError('offline')]):
            self.assertEqual(curate.main(), 1)
        with patch.object(sys, 'argv', args), patch.object(curate, 'decision', return_value=('not_usable', .8)) as backend:
            self.assertEqual(curate.main(), 0)
            self.assertEqual(backend.call_count, 3)
        self.assertEqual(len(read_csv(dest / 'quality_audit.csv')), 4)
        self.assertEqual(len(read_csv(dest / 'quality_accepted.csv')), 1)
        journal = dest / 'quality_checkpoint.jsonl'
        self.assertEqual(len(journal.read_text().splitlines()), 4)
        with patch.object(sys, 'argv', args), patch.object(curate, 'decision') as backend:
            self.assertEqual(curate.main(), 0)
            backend.assert_not_called()
        with self.source.open('a') as stream:
            stream.write('\n')
        with patch.object(sys, 'argv', args):
            with self.assertRaisesRegex(ValueError, 'Manifest changed'):
                curate.main()

    def test_raw_langdetect_and_cached_language_fields(self):
        curate = script('curate_meajor')
        dest = self.root / 'language'
        args = ['curate', '--input', str(self.source), '--output-dir', str(dest), '--provider', 'langdetect', '--policy', 'readability', '--label', 'all']
        with patch.object(sys, 'argv', args):
            self.assertEqual(curate.main(), 0)
        first = read_csv(dest / 'quality_audit.csv')
        self.assertEqual(first[0]['detected_language'], 'en')
        self.assertEqual(first[0]['meajor_language'], 'de')
        self.assertEqual(first[0]['quality_provider'], 'langdetect')
        self.assertEqual(first[1]['quality_status'], 'language_detection_failed')
        with patch.object(sys, 'argv', args), patch('langdetect.detect_langs', side_effect=AssertionError('must use checkpoint')):
            self.assertEqual(curate.main(), 0)
        self.assertEqual(first, read_csv(dest / 'quality_audit.csv'))

    def test_baseline_raw_input_and_metrics(self):
        baseline = script('run_baseline')
        metrics = script('baseline_metrics')
        dest = self.root / 'baseline'
        config = self.root / 'models.json'
        config.write_text(json.dumps({'ollama_base_url': 'http://127.0.0.1:11434', 'victims': [
            {'id': 'test', 'tag': 'test', 'kind': 'decision', 'enabled': True}
        ]}))
        args = ['baseline', '--input', str(self.source), '--config', str(config), '--output-dir', str(dest), '--label', 'all']
        from types import SimpleNamespace
        with patch.object(sys, 'argv', args), patch.object(baseline, 'Ollama') as client:
            client.return_value.classify_decision.return_value = SimpleNamespace(label=1, confidence=.8, probabilities={})
            baseline.main()
            self.assertEqual(client.return_value.classify_decision.call_count, 4)
        rows = read_csv(dest / 'test_baseline.csv')
        result = metrics.metrics(read_dataset(self.source), rows)
        self.assertEqual(result['n_total'], 4)
        self.assertEqual(result['n_invalid_label'], 1)
        self.assertEqual(result['n_classified'], 3)
        self.assertEqual((result['tp'], result['fp']), (2, 1))
        report = self.root / 'metadata.csv'
        proc = subprocess.run([sys.executable, str(ROOT / 'scripts/analyze_metadata.py'), '--dataset', str(self.source),
                               '--baseline', str(dest / 'test_baseline.csv'), '--output', str(report), '--label', 'all'], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        groups = read_csv(report)
        invalid = next(r for r in groups if r['group_type'] == 'source' and r['group_value'] == 'trec6')
        self.assertEqual(invalid['invalid_label_n'], '1')
        self.assertEqual(invalid['benign_class_n'], '0')
        self.assertTrue(any(r['group_value'] == '<100 words' for r in groups))


if __name__ == '__main__':
    unittest.main()
