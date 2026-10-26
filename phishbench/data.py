"""Deterministic dataset adapter for official Zenodo CSVs; no data downloads."""
import csv
import hashlib
import json
import random
import os
import sys
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path


def hash_file(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for buf in iter(lambda:f.read(1024*1024),b''):h.update(buf)
    return h.hexdigest()


def atomic_csv(path,rows,columns):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.tmp')
    with tmp.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=columns,extrasaction='ignore');writer.writeheader();writer.writerows(rows)
    tmp.replace(path)


def read_csv(path):
    try:csv.field_size_limit(sys.maxsize)
    except OverflowError:csv.field_size_limit(2**31-1)
    with open(path,encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f)
        if not reader.fieldnames:raise ValueError('Input file has no header')
        return list(reader)


def read_dataset(path, label=None):
    """Read a raw/prepared dataset, optionally selecting a single gold label.

    Source position is part of raw row IDs so repeated email text retains its
    own checkpoint and label. Original source values are preserved as meajor_*.
    Invalid labels remain present but cannot be used as binary ground truth.
    With label=0/1 they are excluded; source indexes and IDs never renumber.
    """
    if label not in (None, 'all', '0', '1', 0, 1):
        raise ValueError('label must be 0, 1, all, or None')
    selected_label=None if label in (None, 'all') else str(label)
    try:csv.field_size_limit(sys.maxsize)
    except OverflowError:csv.field_size_limit(2**31-1)
    prepared={'row_id','dataset_label','original_text','original_sha256'}
    words=re.compile(r"\b[A-Za-z]+(?:'[A-Za-z]+)?\b")
    placeholders=re.compile(r'\[[A-Z][A-Z_]*\]')
    rows=[]
    with open(path,encoding='utf-8-sig',newline='') as stream:
        reader=csv.DictReader(stream)
        columns=reader.fieldnames or []
        if prepared.issubset(columns):
            for row in reader:
                if selected_label is not None:
                    try:gold=str(parse_gold(row['dataset_label']))
                    except ValueError:continue
                    if gold!=selected_label:continue
                rows.append(row)
            return rows
        if not {'subject','body','label','source'}.issubset(columns):
            raise ValueError('Expected raw MeAJOR CSV (subject, body, label, source) or a prepared cohort')
        for index,source in enumerate(reader):
            if None in source:
                raise ValueError(f'Malformed CSV record at source_index {index}: extra fields')
            try:gold_label=str(parse_gold(source.get('label','')));label_status='valid'
            except ValueError:gold_label='';label_status='invalid'
            if selected_label is not None and gold_label!=selected_label:continue
            subject=(source.get('subject') or '').strip()
            body=(source.get('body') or '').strip()
            text=('Subject: '+subject+'\n\n' if subject else '')+body
            digest=hashlib.sha256(text.encode('utf-8')).hexdigest()
            language=(source.get('language') or '').strip().lower()
            row={
                'row_id':f'meajor-{index:06d}-{digest[:24]}',
                'source_index':str(index),'dataset_label':gold_label,
                'dataset_label_status':label_status,'original_text':text,
                'original_sha256':digest,'source_dataset':'meajor_2026',
                'source_corpus':source.get('source') or 'unknown',
                'word_count':str(len(words.findall(body))),'char_count':str(len(body)),
                'detected_language':'en' if language=='english' else language or 'und',
                'english_score':'','language_method':'source_language_field_only',
                'placeholder_count':str(len(placeholders.findall(text))),
                'placeholder_types':'|'.join(sorted(set(placeholders.findall(text)))),
                'quality_status':'not_annotated',
            }
            row.update({'meajor_'+key:value for key,value in source.items()})
            rows.append(row)
    return rows


def parse_gold(label):
    s=str(label).strip().lower()
    if s in ('1','phishing'):return 1
    if s in ('0','benign','non_phishing','non-phishing'):return 0
    # Some official/exported CSVs use numeric floats 0.0/1.0; accept only exact binary values.
    try:
        number=Decimal(s)
        if number.is_finite() and number in (Decimal(0),Decimal(1)):
            return int(number)
    except InvalidOperation:
        pass
    raise ValueError('Unexpected gold label '+repr(label))


def choose(items,*names):
    for name in names:
        if name in items and str(items[name] or '').strip():return str(items[name]).strip()
    return ''


def prepare(source,dataset_id,seed=42,per_class=1500,disallow_shas=None):
    """Reservoir sampling prevents holding very large corpora in memory.
    Rows are content-hash deduplicated across and within datasets.
    """
    randomizer=random.Random(seed)
    pools={0:[],1:[]};counts={0:0,1:0};seen=set();excluded=set(disallow_shas or set())
    with open(source,encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f)
        if not reader.fieldnames:raise ValueError('CSV missing header')
        if 'label' not in reader.fieldnames and 'true_label' not in reader.fieldnames:
            raise ValueError('Need label or true_label column')
        for i,row in enumerate(reader):
            label=parse_gold(row.get('label',row.get('true_label','')))
            body=choose(row,'body','text_combined','text','email','original_text')
            subject=choose(row,'subject')
            if subject and not body.lower().startswith('subject:'):body='Subject: '+subject+'\n\n'+body
            if not body:continue
            digest=hashlib.sha256(body.strip().encode('utf-8')).hexdigest()
            if digest in seen or digest in excluded:continue
            seen.add(digest)
            counts[label]+=1
            item={'row_id':digest[:20],'source_index':str(i),'dataset_label':str(label), 'original_text':body,
                  'source_dataset':dataset_id,'source_corpus':choose(row,'source','corpus','dataset') or dataset_id,'original_sha256':digest}
            if len(pools[label])<per_class:pools[label].append(item)
            else:
                j=randomizer.randrange(counts[label])
                if j<per_class:pools[label][j]=item
    if any(len(pools[k])<per_class for k in (0,1)):
        raise ValueError('Insufficient unique class members: '+repr({k:len(v) for k,v in pools.items()}))
    chosen=pools[0]+pools[1]
    randomizer.shuffle(chosen)
    # Keep source_index as the original corpus row number after shuffling.
    return chosen,{'dataset':dataset_id,'source_file_sha256':hash_file(source),'seed':seed,'per_class':per_class,'n':len(chosen),'distinct_seen':len(seen),'source_counts':counts}


def atomic_json(path, payload):
    """Safely publish run metadata before first durable checkpoint."""
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.tmp')
    with tmp.open('w',encoding='utf-8') as stream:
        json.dump(payload,stream,sort_keys=True,indent=2)
        stream.flush();os.fsync(stream.fileno())
    tmp.replace(path)


def append_checkpoint(path, payload):
    """One complete JSON object per line, flushed and fsynced per completed row."""
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('ab') as stream:
        stream.write((json.dumps(payload,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n').encode('utf-8'))
        stream.flush();os.fsync(stream.fileno())


def read_checkpoint(path, required_fields=('row',)):
    """Recover a torn final write; reject corruption in a fully written record."""
    path=Path(path)
    if not path.exists():return []
    output=[]
    with path.open('rb+') as stream:
        while True:
            pos=stream.tell()
            line=stream.readline()
            if not line:break
            if not line.endswith(b'\n'):
                # A power-loss-torn trailing entry was never committed.
                stream.seek(pos);stream.truncate();break
            try:row=json.loads(line)
            except (UnicodeDecodeError,json.JSONDecodeError) as exc:
                raise ValueError(f'Checkpoint corruption at byte {pos}: {path}') from exc
            if not isinstance(row,dict) or not set(required_fields).issubset(row):
                raise ValueError(f'Invalid checkpoint entry at byte {pos}: {path}')
            output.append(row)
    return output


def load_row_checkpoint(path, required_fields=()):
    """Recover only a torn final write; never silently ignore committed corruption."""
    records=read_checkpoint(path, ('row_id','original_sha256',*required_fields))
    cached={}
    for row in records:
        if row['row_id'] in cached:
            raise ValueError('Duplicate checkpoint row ID: '+str(row['row_id']))
        cached[row['row_id']]=row
    return cached
