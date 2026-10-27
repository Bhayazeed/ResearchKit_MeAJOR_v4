#!/usr/bin/env python3
import argparse,glob,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from phishbench.workflow import CURATED_DATASET
from phishbench.data import read_csv,read_dataset,atomic_csv

def metrics(dataset,baseline):
    ds={r['row_id']:r for r in dataset}
    if len(ds)!=len(dataset) or len(baseline)!=len(dataset) or set(ds)!={r['row_id'] for r in baseline}:raise ValueError('Baseline rows do not match source dataset')
    tp=tn=fp=fn=missing=invalid_label=0
    for b in baseline:
        row=ds[b['row_id']]
        if row['original_sha256']!=b['original_sha256']:raise ValueError('Original email hash drift')
        if row['dataset_label'] not in ('0','1'):invalid_label+=1;continue
        if b['baseline_status']!='ok':missing+=1;continue
        target=int(row['dataset_label']);pred=int(b['baseline_prediction'])
        if (target,pred)==(1,1):tp+=1
        elif (target,pred)==(0,0):tn+=1
        elif (target,pred)==(0,1):fp+=1
        else:fn+=1
    n=tp+tn+fp+fn
    percent=lambda x,y:round(x/y,6) if y else None
    positives=sum(r['dataset_label']=='1' for r in dataset)
    negatives=sum(r['dataset_label']=='0' for r in dataset)
    scope='both_classes' if positives and negatives else ('positive_only' if positives else 'negative_only' if negatives else 'no_valid_labels')
    return {'n_total':len(dataset),'n_classified':n,'n_missing':missing,'n_invalid_label':invalid_label,'n_positive':positives,'n_negative':negatives,'metric_scope':scope,'classification_coverage':percent(n,positives+negatives),'detection_rate_all_positives':percent(tp,positives),'tp':tp,'tn':tn,'fp':fp,'fn':fn,'accuracy':percent(tp+tn,n),'precision_phishing':percent(tp,tp+fp),'recall_phishing':percent(tp,tp+fn),'f1_phishing':percent(2*tp,2*tp+fp+fn),'tp_pool':tp,'metric_note':'Metrics are conditional on classified rows. Single-class precision/F1/accuracy do not estimate full detector performance; detection_rate_all_positives includes missing predictions in its denominator.'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--dataset',default=CURATED_DATASET);p.add_argument('--dir',required=True);p.add_argument('--output',required=True);p.add_argument('--label',choices=['0','1','all'],default='1',help='Gold label to include (default: 1)');args=p.parse_args()
    ds=read_dataset(args.dataset,label=args.label);output=[]
    for path in glob.glob(str(Path(args.dir)/'*_baseline.csv')):
        v=Path(path).name.replace('_baseline.csv','');row={'victim_id':v};row.update(metrics(ds,read_csv(path)));output.append(row)
    if not output:raise SystemExit('No baseline files')
    atomic_csv(args.output,output,list(output[0]));print('Saved',args.output)
if __name__=='__main__':main()
