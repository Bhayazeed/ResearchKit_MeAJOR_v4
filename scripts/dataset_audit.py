#!/usr/bin/env python3
"""Check MeAJOR row/label/source/placeholder distribution without model calls."""
import argparse,csv,json,re,sys
from collections import Counter
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from phishbench.data import atomic_json

def main():
 p=argparse.ArgumentParser();p.add_argument('--input',default='data/meajor_cleaned_preprocessed.csv');p.add_argument('--output',default='outputs/meajor_dataset_audit.json');args=p.parse_args()
 stats=Counter();sources=Counter();examples=Counter();pat=re.compile(r'\[[A-Z][A-Z_]*\]')
 try:csv.field_size_limit(sys.maxsize)
 except OverflowError:csv.field_size_limit(2**31-1)
 with open(args.input,encoding='utf-8-sig',errors='replace',newline='') as f:
  rd=csv.DictReader(f)
  for r in rd:
   stats['total']+=1;value=(r.get('label') or '').strip()
   if value not in ('0','0.0','1','1.0'):stats['invalid_label']+=1;continue
   lab=str(int(float(value)));stats['label_'+lab]+=1
   sources[(r.get('source') or '<empty>',lab)]+=1
   text=(r.get('subject') or '')+'\n'+(r.get('body') or '')
   if pat.search(text):stats['placeholder_rows']+=1
   if len((r.get('body') or ''))>=500:stats['body_500_chars']+=1
   if (r.get('language') or '').lower()=='en':stats['source_language_en']+=1
 payload={'counts':dict(stats),'sources_by_label':{a+'|'+b:c for (a,b),c in sources.items()},'note':'The csv release observed, not the number of claimed original corpora'}
 atomic_json(args.output,payload);print(json.dumps(payload,indent=2))
if __name__=='__main__':main()
