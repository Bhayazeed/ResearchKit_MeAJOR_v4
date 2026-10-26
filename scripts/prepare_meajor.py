#!/usr/bin/env python3
"""Prepare frozen balanced MeAJOR samples from the original public release.

Uses a deterministic hash-ranked candidate pool, preserves labels and every
original metadata column (prefixed meajor_), with provenance and audit counts.
No classifier or model API calls. Language scoring uses local langdetect unless
--language-mode supplied is requested as an explicitly weaker fallback.
"""
import argparse,csv,hashlib,heapq,json,re,sys
from collections import Counter
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from phishbench.data import atomic_csv,hash_file,parse_gold

REQUIRED=('subject','body','label','source')
WORDS=re.compile(r"\b[A-Za-z]+(?:'[A-Za-z]+)?\b")
PLACEHOLDER=re.compile(r'\[[A-Z][A-Z_]*\]')

def detected(text,mode):
    if mode=='supplied':return 'en', '', 'source_language_field_only'
    try:
        from langdetect import DetectorFactory,detect_langs
    except ImportError as exc:
        raise RuntimeError('Install langdetect first: python -m pip install -r requirements.txt') from exc
    DetectorFactory.seed=42
    try:
        probs=detect_langs(text[:6000])
        return (max(probs,key=lambda x:x.prob).lang,round(max((x.prob for x in probs if x.lang=='en'),default=0),5),'langdetect')
    except Exception:return 'und',0,'langdetect_failed'

def prepare(input_path,per_class,seed,min_words,min_chars,threshold,multiplier,language_mode):
    import csv
    try:csv.field_size_limit(sys.maxsize)
    except OverflowError:csv.field_size_limit(2**31-1)
    stats=Counter();source_labels=Counter();heap={0:[],1:[]};seen=set();columns=None
    limit=per_class*multiplier
    with open(input_path,'r',newline='',encoding='utf-8-sig',errors='replace') as f:
        reader=csv.DictReader(f);columns=reader.fieldnames or []
        missing=[k for k in REQUIRED if k not in columns]
        if missing:raise ValueError('MeAJOR missing columns: '+str(missing))
        for original_index,row in enumerate(reader):
            stats['total_rows']+=1
            row['_internal_index']=str(original_index)
            try:label=parse_gold(row.get('label',''))
            except ValueError:stats['invalid_label']+=1;continue
            stats['class_'+str(label)]+=1
            subject=(row.get('subject') or '').strip();body=(row.get('body') or '').strip()
            if not body:stats['empty_body']+=1;continue
            text=('Subject: '+subject+'\n\n' if subject else '')+body
            digest=hashlib.sha256(text.encode('utf-8')).hexdigest()
            if digest in seen:stats['duplicate_text']+=1;continue
            seen.add(digest)
            nwords=len(WORDS.findall(body))
            if nwords<min_words or len(body)<min_chars:
                stats['too_short']+=1;continue
            # Source language is a first-pass filter. Actual langdetect
            # is applied to deterministic shortlists in the second pass.
            if (row.get('language') or '').strip().lower() not in ('en','english'):
                stats['not_english_by_source']+=1;continue
            stats['length_and_source_language_pass']+=1
            source_labels[(row.get('source') or 'unknown',label)]+=1
            score=int(hashlib.sha256((str(seed)+'|'+digest).encode()).hexdigest(),16)
            item=(-score,digest,row,nwords,len(body),text)
            if len(heap[label])<limit:heapq.heappush(heap[label],item)
            elif item[0]>heap[label][0][0]:heapq.heapreplace(heap[label],item)
    samples={}
    for label in (0,1):
        ranked=sorted(heap[label],key=lambda item:-item[0]);chosen=[]
        for neg_score,digest,row,nwords,nchars,text in ranked:
            lang,en_score,method=detected(text,language_mode)
            stats['language_checked']+=1
            if language_mode=='langdetect' and (lang!='en' or float(en_score)<threshold):
                stats['langdetect_reject']+=1;continue
            record={
             'row_id':digest[:24], 'source_index':row.get('_internal_index',''),
             'dataset_label':str(label), 'original_text':text,
             'original_sha256':digest,'source_dataset':'meajor_2026',
             'source_corpus':row.get('source','') or 'unknown',
             'word_count':str(nwords),'char_count':str(nchars),
             'detected_language':lang,'english_score':en_score,
             'language_method':method,'placeholder_count':str(len(PLACEHOLDER.findall(text))),
             'placeholder_types':'|'.join(sorted(set(PLACEHOLDER.findall(text)))),
             'quality_status':'not_annotated'
            }
            record.update({'meajor_'+k:row.get(k,'') for k in columns})
            chosen.append(record)
            if len(chosen)>=per_class:break
        if len(chosen)<per_class:raise ValueError(f'Only {len(chosen)} valid class {label} samples after sampling; increase --multiplier or relax filters')
        samples[label]=chosen
    # Stable overall order: deterministic hash (NOT original source order).
    merged=sorted(samples[0]+samples[1],key=lambda r:hashlib.sha256((str(seed)+'order'+r['row_id']).encode()).hexdigest())
    fields=['row_id','source_index','dataset_label','original_text','original_sha256','source_dataset','source_corpus','word_count','char_count','detected_language','english_score','language_method','placeholder_count','placeholder_types','quality_status']+['meajor_'+k for k in columns]
    audit={'source_file':str(Path(input_path).resolve()),'source_sha256':hash_file(input_path),'dataset':'MeAJOR 2026','seed':seed,'per_class':per_class,'language_mode':language_mode,'langdetect_threshold':threshold,'min_words':min_words,'min_chars':min_chars,'multiplier':multiplier,'counts':dict(stats),'available_sources_after_prefilter':{f'{a}|{b}':n for (a,b),n in sorted(source_labels.items())},'sampled_sources':dict(Counter(r['source_corpus'] for r in merged)),'original_labels_preserved':True,'frozen_cohort':True,'caveat':'No manual phishing-only adjudication; dataset labels follow MeAJOR. Language scores are heuristic.'}
    return merged,fields,audit

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--input',default='data/meajor_cleaned_preprocessed.csv')
    p.add_argument('--output',required=True)
    p.add_argument('--per-class',type=int,default=500)
    p.add_argument('--seed',type=int,default=42)
    p.add_argument('--min-words',type=int,default=100)
    p.add_argument('--min-chars',type=int,default=500)
    p.add_argument('--english-threshold',type=float,default=.9)
    p.add_argument('--multiplier',type=int,default=4)
    p.add_argument('--language-mode',choices=['langdetect','supplied'],default='langdetect')
    args=p.parse_args()
    if args.per_class<1 or args.multiplier<1:p.error('per-class and multiplier must be positive')
    if not 0<=args.english_threshold<=1:p.error('English score threshold must be 0..1')
    rows,fields,audit=prepare(args.input,args.per_class,args.seed,args.min_words,args.min_chars,args.english_threshold,args.multiplier,args.language_mode)
    atomic_csv(args.output,rows,fields)
    Path(args.output+'.source.json').write_text(json.dumps(audit,indent=2,ensure_ascii=False),encoding='utf-8')
    print('Prepared',len(rows),'balanced rows in',args.output)
    print('Sampled source breakdown:',audit['sampled_sources'])
    print('Language validation:',args.language_mode)
if __name__=='__main__':main()
