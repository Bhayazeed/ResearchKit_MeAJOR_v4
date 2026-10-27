"""Read-only checks of the supplied accepted CSV against current eligibility."""
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'data/quality_accepted.csv'
LEGACY = ROOT / 'outputs/quality_pplx_label1/quality_accepted.csv'
WORDS = re.compile(r"\b[A-Za-z]+(?:'[A-Za-z]+)?\b")
csv.field_size_limit(2**31-1)


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    counts = Counter()
    categories = {key: Counter() for key in (
        'dataset_label', 'quality_accepted', 'quality_model',
        'quality_provider', 'quality_status', 'detected_language',
        'language_method', 'curation_policy', 'language_screen')}
    ids = set()
    with SOURCE.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        columns = reader.fieldnames
        for row in reader:
            counts['rows'] += 1
            rid = row.get('row_id', '')
            counts['missing_or_duplicate_ids'] += int(not rid or rid in ids)
            ids.add(rid)
            text = row.get('original_text', '')
            body = row.get('meajor_body')
            if body is None:
                body = text.split('\n\n', 1)[1] if text.startswith('Subject: ') and '\n\n' in text else text
            n = len(WORDS.findall(body))
            counts['body_under_100'] += int(n < 100)
            counts['body_exactly_100'] += int(n == 100)
            counts['body_over_100'] += int(n > 100)
            counts['text_hash_mismatch'] += int(hashlib.sha256(text.encode()).hexdigest() != row.get('original_sha256'))
            for key, values in categories.items():
                values[row.get(key, '<missing>')] += 1
    report = {
        'source': str(SOURCE.relative_to(ROOT)),
        'source_sha256': digest(SOURCE),
        'legacy_sha256': digest(LEGACY),
        'columns': columns,
        'counts': dict(counts),
        'categories': {k: dict(v) for k, v in categories.items()},
        'scope': 'No language inference or dataset modifications performed. Counts use the current curator body token rule.',
    }
    report['identical_to_legacy_export'] = report['source_sha256'] == report['legacy_sha256']
    output = Path(__file__).with_name('accepted_reuse_check.json')
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
