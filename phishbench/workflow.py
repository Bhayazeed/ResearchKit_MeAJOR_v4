"""Shared input for the defensive curated-cohort workflow."""
import hashlib

CURATED_DATASET = 'outputs/quality_pplx_english_length_v3/quality_accepted.csv'
BASELINE_DIR = 'outputs/curated_english_length_baseline'


def validate_curated_rows(rows):
    if not rows:
        raise ValueError('Curated dataset contains no accepted rows')
    seen=set()
    for row in rows:
        rid=row.get('row_id','')
        if not rid or rid in seen:
            raise ValueError('Curated dataset has missing/duplicate row IDs')
        seen.add(rid)
        if (row.get('dataset_label')!='1' or row.get('quality_accepted')!='1'
                or row.get('curation_policy')!='english_length'
                or row.get('language_screen')!='passed'
                or row.get('quality_status')!='completed'
                or row.get('detected_language')!='en'
                or row.get('language_method')!='decision_model'):
            raise ValueError('Row lacks complete English/length curation: '+rid)
        try:
            minimum=int(row['quality_min_words']);words=int(row['body_word_count'])
        except (KeyError,ValueError,TypeError) as exc:
            raise ValueError('Missing/invalid curation thresholds: '+rid) from exc
        if minimum<1 or words<minimum:
            raise ValueError('Curation thresholds not satisfied: '+rid)
        if hashlib.sha256(row['original_text'].encode('utf-8')).hexdigest()!=row['original_sha256']:
            raise ValueError('Curated text checksum mismatch: '+rid)
