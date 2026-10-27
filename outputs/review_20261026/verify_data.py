"""Independent source/output reconciliation. No model calls; no email text logged."""
import csv, hashlib, json, sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
csv.field_size_limit(2**31-1)
source = ROOT / 'data/meajor_cleaned_preprocessed.csv'
quality = ROOT / 'outputs/quality_pplx_label1'
md5 = hashlib.md5()
sha = hashlib.sha256()
with source.open('rb') as stream:
    for block in iter(lambda: stream.read(1024*1024), b''):
        md5.update(block); sha.update(block)
counts = Counter(); labels = Counter(); sources = Counter(); languages = Counter()
text_labels = defaultdict(set); selected_hashes = Counter(); selected = {}
with source.open(encoding='utf-8-sig', newline='') as stream:
    reader = csv.DictReader(stream); fields = reader.fieldnames
    for index, row in enumerate(reader):
        counts['raw_rows'] += 1
        value = (row.get('label') or '').strip()
        label = {'0':'0','0.0':'0','1':'1','1.0':'1'}.get(value, 'invalid')
        labels[label] += 1
        sources[(row.get('source') or '<empty>')+'|'+label] += 1
        subject = (row.get('subject') or '').strip()
        body = (row.get('body') or '').strip()
        text = ('Subject: '+subject+'\n\n' if subject else '')+body
        digest = hashlib.sha256(text.encode()).hexdigest()
        text_labels[digest].add(label)
        if label != '1': continue
        counts['label1_empty_body'] += not bool(body)
        counts['label1_empty_text'] += not bool(text)
        counts['label1_text_over_20000_chars'] += len(text)>20000
        counts['label1_text_over_6000_chars'] += len(text)>6000
        languages[row.get('language') or '<empty>'] += 1
        selected_hashes[digest] += 1
        rid = f'meajor-{index:06d}-{digest[:24]}'
        selected[rid] = (digest, row)
audit_ids = set(); accepted_ids = set(); issues = Counter(); decisions = Counter(); by_source = Counter()
with (quality/'quality_audit.csv').open(encoding='utf-8-sig', newline='') as stream:
    for row in csv.DictReader(stream):
        rid = row['row_id']; issues['duplicate_audit_ids'] += rid in audit_ids; audit_ids.add(rid)
        if rid not in selected: issues['unexpected_audit_id'] += 1; continue
        digest, original = selected[rid]
        issues['hash_mismatch'] += row['original_sha256'] != digest
        issues['text_hash_mismatch'] += hashlib.sha256(row['original_text'].encode()).hexdigest() != digest
        issues['non_label1_audit_row'] += row['dataset_label'] != '1'
        issues['metadata_row_mismatch'] += any(row.get('meajor_'+k) != original[k] for k in fields)
        decisions[row['quality_category']] += 1
        by_source[row['source_corpus']+'|'+row['quality_category']] += 1
        if row['quality_accepted']=='1': accepted_ids.add(rid)
        issues['category_acceptance_mismatch'] += (row['quality_accepted']=='1') != (row['quality_category']=='usable')
issues['missing_audit_ids'] = len(set(selected)-audit_ids)
export_ids = set(); export_n = 0
with (quality/'quality_accepted.csv').open(encoding='utf-8-sig', newline='') as stream:
    for row in csv.DictReader(stream):
        export_n += 1; export_ids.add(row['row_id'])
        issues['non_label1_accepted_row'] += row['dataset_label']!='1'
issues['accepted_subset_symmetric_difference'] = len(export_ids ^ accepted_ids)
issues['duplicate_accepted_ids'] = export_n-len(export_ids)
journal_ids = set(); journal_n = 0
with (quality/'quality_checkpoint.jsonl').open(encoding='utf-8') as stream:
    for line in stream:
        journal_n += 1; row = json.loads(line); journal_ids.add(row['row_id'])
issues['checkpoint_id_symmetric_difference'] = len(journal_ids ^ audit_ids)
issues['duplicate_checkpoint_ids'] = journal_n-len(journal_ids)
summary = json.loads((quality/'quality_summary.json').read_text())
manifest = json.loads((quality/'quality_manifest.json').read_text())
issues['summary_mismatch'] = int(summary['cohort_n']!=len(audit_ids) or summary['accepted_n']!=len(accepted_ids) or summary['counts']!=dict(decisions))
issues['manifest_source_hash_mismatch'] = int(manifest['source_sha256']!=sha.hexdigest())
result = {'source_md5':md5.hexdigest(), 'source_sha256':sha.hexdigest(), 'column_count':len(fields), 'columns':fields,
          'counts':dict(counts), 'labels':dict(labels), 'sources_by_label':dict(sources),
          'label1_source_languages':dict(languages), 'label1_unique_texts':len(selected_hashes),
          'label1_duplicate_excess':sum(n-1 for n in selected_hashes.values()),
          'conflicting_label_text_hashes':sum(len(v-{'invalid'})>1 for v in text_labels.values()),
          'pplx_audit_rows':len(audit_ids), 'pplx_accepted_rows':len(accepted_ids),
          'pplx_decisions':dict(decisions), 'pplx_by_source':dict(by_source), 'integrity_issues':dict(issues)}
target = Path(__file__).with_name('data_verification.json')
target.write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
if any(issues.values()): raise SystemExit('Integrity mismatch found')
