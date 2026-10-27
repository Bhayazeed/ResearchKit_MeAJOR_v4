#!/usr/bin/env python3
"""Optional: take only rows accepted by every selected quality method.
No relabeling; can keep same class counts for fair downstream experiments.
"""
import argparse,sys,json
from pathlib import Path
from collections import Counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from phishbench.data import read_csv,read_dataset,atomic_csv,atomic_json,hash_file

def main():
 p=argparse.ArgumentParser()
 p.add_argument('--input',required=True)
 p.add_argument('--audit',nargs='+',required=True,help='quality_audit.csv from each provider')
 p.add_argument('--output',required=True)
 p.add_argument('--label',choices=['0','1','all'],default='1')
 p.add_argument('--per-class',type=int,help='Optional sample size per selected class; omit to retain all accepted rows')
 args=p.parse_args()
 if args.per_class is not None and args.per_class<1:p.error('--per-class must be positive')
 rows=read_dataset(args.input,label=args.label);source={x['row_id']:x for x in rows};eligible=set(source)
 if not rows:raise ValueError('No rows match label filter: '+args.label)
 if len(source)!=len(rows):raise ValueError('Duplicate source row IDs')
 primary_audit=None
 for path in args.audit:
  cur=read_csv(path)
  if len(cur)!=len(source) or set(x['row_id'] for x in cur)!=set(source):raise ValueError('All audits must use the SAME selected input cohort with unique IDs')
  for row in cur:
   if any(row.get(key)!=source[row['row_id']].get(key) for key in ('original_sha256','dataset_label')):raise ValueError('Audit provenance mismatch at '+row['row_id'])
   if row.get('quality_accepted') not in ('0','1'):raise ValueError('Invalid quality acceptance at '+row['row_id'])
  accepted={x['row_id'] for x in cur if x['quality_accepted']=='1'}
  eligible.intersection_update(accepted)
  if primary_audit is None:primary_audit={x['row_id']:x for x in cur}
 output=[];counts=Counter()
 for r in rows:
  label=r['dataset_label']
  if r['row_id'] in eligible and (args.per_class is None or (label in ('0','1') and counts[label]<args.per_class)):
   # Preserve annotations from the first (primary) audit while retaining source text/labels.
   annotation_keys=set(primary_audit[r['row_id']])-set(r)
   annotation_keys.update({'quality_status','detected_language','english_score','language_method','word_count'} & set(primary_audit[r['row_id']]))
   annotated=dict(r)
   annotated.update({key:value for key,value in primary_audit[r['row_id']].items() if key in annotation_keys})
   output.append(annotated);counts[label]+=1
 selected_classes=('0','1') if args.label=='all' else (args.label,)
 if args.per_class is not None and any(counts[label]<args.per_class for label in selected_classes):raise ValueError('Not enough common accepted rows: '+repr(dict(counts))+'; do not pad with unapproved data')
 if not output:raise ValueError('No common accepted rows')
 atomic_csv(args.output,output,list(output[0]));atomic_json(args.output+'.source.json',{'frozen_input_sha256':hash_file(args.input),'quality_audits':[{ 'path':p,'sha256':hash_file(p)} for p in args.audit],'primary_annotation_audit':args.audit[0],'label_filter':args.label,'per_class':args.per_class,'n_by_label':dict(counts),'labels_preserved':True})
 print('Common quality cohort:',len(output),'labels',dict(counts))
if __name__=='__main__':main()
