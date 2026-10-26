"""Label-1 workflow, provenance, and metric-denominator regressions."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from test_full_dataset import script
from phishbench.data import atomic_csv, read_csv, read_dataset


class TestResearchPipeline(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'raw.csv'
        rows = [dict(subject='Meeting', body='Hello team, please review the attached agenda.',
                     label=label, source='trec5', language='en') for label in ('0', '1.0', '', '1')]
        atomic_csv(self.source, rows, list(rows[0]))
        self.selected = read_dataset(self.source, label='1')

    def test_filter_preserves_ids_and_prepared_input(self):
        full = read_dataset(self.source)
        self.assertEqual(self.selected, [r for r in full if r['dataset_label'] == '1'])
        self.assertEqual([r['source_index'] for r in self.selected], ['1', '3'])
        self.assertEqual(len({r['row_id'] for r in self.selected}), 2)
        prepared = self.root / 'prepared.csv'
        atomic_csv(prepared, full, list(full[0]))
        self.assertEqual(self.selected, read_dataset(prepared, label='1'))

    def test_curation_label1_default_and_resume(self):
        curate = script('curate_meajor')
        for provider in ('ollama', 'openrouter', 'none'):
            dest = self.root / provider
            args = ['curate', '--input', str(self.source), '--output-dir', str(dest), '--provider', provider]
            with patch.object(sys, 'argv', args), patch.object(curate, 'decision', return_value=('usable', .9)) as backend:
                self.assertEqual(curate.main(), 0)
                self.assertEqual(backend.call_count, 0 if provider == 'none' else 2)
            audit = read_csv(dest / 'quality_audit.csv')
            self.assertEqual([r['row_id'] for r in audit], [r['row_id'] for r in self.selected])
            self.assertEqual({r['dataset_label'] for r in audit}, {'1'})
            with patch.object(sys, 'argv', args), patch.object(curate, 'decision') as backend:
                self.assertEqual(curate.main(), 0)
                backend.assert_not_called()
            with patch.object(sys, 'argv', args + ['--label', 'all']):
                with self.assertRaisesRegex(ValueError, 'Manifest changed'):
                    curate.main()

    def test_baseline_label1_default(self):
        baseline = script('run_baseline')
        config = self.root / 'models.json'
        config.write_text(json.dumps({'ollama_base_url': 'http://127.0.0.1:11434', 'victims': [
            {'id': 'test', 'tag': 'test', 'kind': 'decision', 'enabled': True}]}))
        dest = self.root / 'baseline'
        args = ['baseline', '--input', str(self.source), '--config', str(config), '--output-dir', str(dest)]
        with patch.object(sys, 'argv', args), patch.object(baseline, 'Ollama') as client:
            client.return_value.classify_decision.return_value = SimpleNamespace(label=1, confidence=.9, probabilities={})
            baseline.main()
            self.assertEqual(client.return_value.classify_decision.call_count, 2)
        result = read_csv(dest / 'test_baseline.csv')
        self.assertEqual({r['dataset_label'] for r in result}, {'1'})
        self.assertEqual(len(result), 2)
        with patch.object(sys, 'argv', args + ['--label', 'all']):
            with self.assertRaisesRegex(ValueError, 'Baseline changed'):
                baseline.main()
        metrics = script('baseline_metrics')
        report = self.root / 'metrics.csv'
        with patch.object(sys, 'argv', ['metrics', '--dataset', str(self.source), '--dir', str(dest), '--output', str(report)]):
            metrics.main()
        self.assertEqual(read_csv(report)[0]['metric_scope'], 'positive_only')

    def test_freeze_all_accepted_label1_and_provenance(self):
        freeze = script('freeze_approved')
        audit = [dict(r, quality_accepted='1') for r in self.selected]
        path = self.root / 'audit.csv'
        atomic_csv(path, audit, list(audit[0]))
        output = self.root / 'frozen.csv'
        args = ['freeze', '--input', str(self.source), '--audit', str(path), '--output', str(output)]
        with patch.object(sys, 'argv', args):
            freeze.main()
        self.assertEqual(read_csv(output), self.selected)
        self.assertEqual(json.loads(Path(str(output)+'.source.json').read_text())['per_class'], None)
        audit[0]['original_sha256'] = 'changed'
        atomic_csv(path, audit, list(audit[0]))
        with patch.object(sys, 'argv', args):
            with self.assertRaisesRegex(ValueError, 'provenance mismatch'):
                freeze.main()

    def test_compare_checks_hash_and_label(self):
        compare = script('compare_curations')
        audit = [dict(r, quality_accepted='1', quality_model='test') for r in self.selected]
        a, b = self.root / 'a.csv', self.root / 'b.csv'
        atomic_csv(a, audit, list(audit[0]))
        audit[0]['original_sha256'] = 'changed'
        atomic_csv(b, audit, list(audit[0]))
        with patch.object(sys, 'argv', ['compare', '--a', str(a), '--b', str(b), '--output', str(self.root/'comparison.csv')]):
            with self.assertRaisesRegex(ValueError, 'provenance mismatch'):
                compare.main()

    def test_metrics_disclose_single_class_and_missing(self):
        metrics = script('baseline_metrics')
        baseline = [dict(r, baseline_status='ok', baseline_prediction='1') for r in self.selected]
        baseline[1].update(baseline_status='model_refusal', baseline_prediction='')
        result = metrics.metrics(self.selected, baseline)
        self.assertEqual(result['recall_phishing'], 1)
        self.assertEqual(result['detection_rate_all_positives'], .5)
        self.assertEqual(result['classification_coverage'], .5)
        self.assertEqual(result['metric_scope'], 'positive_only')
        self.assertEqual(result['n_positive'], 2)
        self.assertEqual(result['n_negative'], 0)

    def test_checkpoint_recovers_torn_tail_and_rejects_corruption(self):
        from phishbench.data import append_checkpoint, load_row_checkpoint
        path = self.root / 'checkpoint.jsonl'
        row = {'row_id':'one','original_sha256':'abc'}
        append_checkpoint(path, row)
        with path.open('ab') as stream:
            stream.write(b'{"row_id":')
        self.assertEqual(load_row_checkpoint(path), {'one':row})
        append_checkpoint(path, dict(row, row_id='two'))
        self.assertEqual(len(load_row_checkpoint(path)), 2)
        with path.open('ab') as stream:
            stream.write(b'broken\n')
        with self.assertRaisesRegex(ValueError, 'Checkpoint corruption'):
            load_row_checkpoint(path)

    def test_checkpoint_rejects_duplicate_ids(self):
        from phishbench.data import append_checkpoint, load_row_checkpoint
        path = self.root / 'duplicates.jsonl'
        row = {'row_id':'one','original_sha256':'abc'}
        append_checkpoint(path, row)
        append_checkpoint(path, row)
        with self.assertRaisesRegex(ValueError, 'Duplicate checkpoint'):
            load_row_checkpoint(path)


if __name__ == '__main__':
    unittest.main()
