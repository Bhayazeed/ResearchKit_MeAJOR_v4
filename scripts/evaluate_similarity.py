#!/usr/bin/env python3
"""Optional SBERT/BLEU/ROUGE/Jaccard/retention on reviewed offline candidates."""
import argparse,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from phishbench.workflow import CURATED_DATASET
from phishbench.data import read_csv,read_dataset,atomic_csv
from phishbench.quality import screen,tokens

def main():
 p=argparse.ArgumentParser();p.add_argument('--dataset',default=CURATED_DATASET);p.add_argument('--candidates',required=True);p.add_argument('--output',required=True);p.add_argument('--sbert',action='store_true');p.add_argument('--label',choices=['0','1','all'],default='1',help='Gold label to include (default: 1)');args=p.parse_args()
 from sacrebleu.metrics import BLEU
 from rouge_score.rouge_scorer import RougeScorer
 bleu=BLEU(effective_order=True);rouge=RougeScorer(['rougeL'],use_stemmer=True)
 encoder=None
 if args.sbert:
  from sentence_transformers import SentenceTransformer
  encoder=SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
 index={r['row_id']:r for r in read_dataset(args.dataset,label=args.label)};metrics=[]
 for row in read_csv(args.candidates):
  if row['row_id'] not in index or row.get('review_status')!='approved':continue
  a=index[row['row_id']]['original_text'];b=row.get('candidate_text','')
  if not b.strip():continue
  scr=screen(a,b)
  va=set(t for t in tokens(a) if len(t)>3);vb=set(tokens(b))
  result={'row_id':row['row_id'],'method':row['method'],'BLEU_0_100':round(bleu.sentence_score(b,[a]).score,4),'ROUGE_L_0_1':round(rouge.score(a,b)['rougeL'].fmeasure,6),'Jaccard_0_1':scr['jaccard'],'content_retention_0_1':round(len(va&vb)/len(va),6) if va else 1.0,'placeholder_retention_0_1':scr['anchor_retention'],'length_ratio':scr['length_ratio'],'SBERT_cosine_0_1':''}
  if encoder is not None:
   x=encoder.encode([a,b],normalize_embeddings=True);result['SBERT_cosine_0_1']=round(float(x[0]@x[1]),6)
  metrics.append(result)
 if not metrics:raise ValueError('No approved candidates')
 atomic_csv(args.output,metrics,list(metrics[0]));print('Saved',len(metrics),'metrics to',args.output)
if __name__=='__main__':main()
