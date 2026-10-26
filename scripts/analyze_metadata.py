#!/usr/bin/env python3
"""Metadata subgroup baseline report; records support and TP/TN/FP/FN."""
import argparse,sys
from pathlib import Path
from collections import Counter,defaultdict
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from phishbench.data import read_csv,read_dataset,atomic_csv

def main():
 p=argparse.ArgumentParser();p.add_argument('--dataset',required=True);p.add_argument('--baseline',required=True);p.add_argument('--output',required=True);p.add_argument('--label',choices=['0','1','all'],default='1',help='Gold label to include (default: 1)');args=p.parse_args()
 dataset=read_dataset(args.dataset,label=args.label);base={r['row_id']:r for r in read_csv(args.baseline)};cnt=defaultdict(Counter)
 if len(base)!=len(dataset):raise ValueError('Baseline cohort mismatch')
 for r in dataset:
  label=r['dataset_label'];prediction=base[r['row_id']]
  if prediction['original_sha256']!=r['original_sha256']:raise ValueError('Hash drift')
  value=prediction['baseline_prediction'] if prediction['baseline_status']=='ok' else None
  words=int(r.get('word_count') or 0)
  groups={'source':r['source_corpus'],'placeholder': 'yes' if int(r.get('placeholder_count') or 0)>0 else 'no', 'length': '<100 words' if words<100 else ('100-199 words' if words<200 else '200+ words')}
  for name,key in groups.items():
   group=cnt[(name,key)];group['n']+=1;group['phish_class_n' if label=='1' else ('benign_class_n' if label=='0' else 'invalid_label_n')]+=1
   if value is None or label not in ('0','1'):group['unscored']+=1
   else:group[{('1','1'):'tp',('1','0'):'fn',('0','0'):'tn',('0','1'):'fp'}[(label,value)]]+=1
 fields=['victim','group_type','group_value','n','phish_class_n','benign_class_n','tp','tn','fp','fn','unscored','invalid_label_n','accuracy','recall_phish','fpr']
 result=[]
 for (name,key),c in sorted(cnt.items()):
  scored=sum(c[k] for k in ('tp','tn','fp','fn'))
  result.append({'victim':next(iter(base.values()))['victim_id'],'group_type':name,'group_value':key,**{f:c[f] for f in fields[3:12]},'accuracy':round((c['tp']+c['tn'])/scored,4) if scored else '', 'recall_phish':round(c['tp']/(c['tp']+c['fn']),4) if c['tp']+c['fn'] else '', 'fpr':round(c['fp']/(c['fp']+c['tn']),4) if c['fp']+c['tn'] else ''})
 atomic_csv(args.output,result,fields);print('Saved metadata subgroup baseline report',args.output)
if __name__=='__main__':main()
