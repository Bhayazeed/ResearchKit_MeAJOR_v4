#!/usr/bin/env python3
"""Read-only evaluation of pre-existing, manually approved offline candidates.

No generator/attack implementation or model-based search loop. Candidates are
paired by row_id and method, and all statistics use fixed cohort denominator.
"""
import argparse,csv,hashlib,math,sys
from collections import Counter
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from phishbench.data import read_csv,read_dataset,atomic_csv
from phishbench.analysis import mcnemar_exact
from phishbench.quality import screen,tokens

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--dataset',required=True)
    p.add_argument('--baseline',required=True,help='Victim baseline CSV')
    p.add_argument('--candidates',required=True,help='Manually reviewed offline records: row_id,method,candidate_text,review_status,final_prediction')
    p.add_argument('--output-dir',default='outputs/eval')
    p.add_argument('--label',choices=['0','1','all'],default='1',help='Gold label to include (default: 1)');args=p.parse_args()
    cohort=read_dataset(args.dataset,label=args.label);baselines=read_csv(args.baseline);candidates=read_csv(args.candidates)
    indexed={r['row_id']:r for r in cohort};baseline={r['row_id']:r for r in baselines}
    if len(indexed)!=len(cohort) or len(baseline)!=len(baselines) or set(indexed)!=set(baseline):raise ValueError('Mismatched baseline and dataset IDs')
    for rid,row in indexed.items():
        if baseline[rid]['original_sha256']!=row['original_sha256']:raise ValueError('Baseline source hash mismatch')
    rows=[];seen=set();tps={rid for rid,r in indexed.items() if r['dataset_label']=='1' and baseline[rid]['baseline_status']=='ok' and baseline[rid]['baseline_prediction']=='1'}
    for cand in candidates:
        rid=cand['row_id'];method=cand['method']
        if rid not in indexed:raise ValueError('Unknown candidate ID')
        if (rid,method) in seen:raise ValueError('Duplicate candidate ID & method')
        seen.add((rid,method))
        if cand.get('review_status')!='approved':continue
        if rid not in tps:continue
        if cand.get('final_prediction') not in ('0','1'):continue
        if not cand.get('candidate_text','').strip():continue
        metrics=screen(indexed[rid]['original_text'],cand['candidate_text'])
        anchor=set(t for t in tokens(indexed[rid]['original_text']) if len(t)>3)
        retained=round(len(anchor&set(tokens(cand['candidate_text'])))/len(anchor),6) if anchor else 1.0
        result={'row_id':rid,'method':method,'victim_id':baseline[rid]['victim_id'],'source_corpus':indexed[rid].get('source_corpus',''),'has_placeholder':str(int(bool(indexed[rid].get('placeholder_count','0')!='0'))),'dataset_label':indexed[rid]['dataset_label'],'baseline_prediction':'1','final_prediction':cand['final_prediction'],'raw_label_flip':str(int(cand['final_prediction']=='0')),'review_status':'approved','similarity_jaccard':metrics['jaccard'],'content_retention':retained,'placeholder_retention':metrics['anchor_retention'],'url_retention':metrics['url_retention'],'numeric_retention':metrics['numeric_retention'],'length_ratio':metrics['length_ratio'],'screen_status':metrics['status']}
        rows.append(result)
    out=Path(args.output_dir);out.mkdir(parents=True,exist_ok=True)
    fields=['row_id','method','victim_id','source_corpus','has_placeholder','dataset_label','baseline_prediction','final_prediction','raw_label_flip','review_status','similarity_jaccard','content_retention','placeholder_retention','url_retention','numeric_retention','length_ratio','screen_status']
    atomic_csv(out/'candidate_metrics.csv',rows,fields)
    methods=sorted({x['method'] for x in candidates});summaries=[]
    for method in methods:
        selected=[r for r in rows if r['method']==method];flips=sum(r['raw_label_flip']=='1' for r in selected)
        summaries.append({'victim_id':baselines[0]['victim_id'],'method':method,'baseline_true_positive_pool':len(tps),'reviewed_scored_candidates':len(selected),'raw_flips':flips,'raw_flips_per_TP':round(flips/len(tps),6) if tps else '', 'reviewed_flip_rate':round(flips/len(selected),6) if selected else '', 'validated_ASR':'requires explicit human confirmation of retained phishing intent'})
    if summaries:atomic_csv(out/'summary.csv',summaries,list(summaries[0]))
    if len(methods)==2:
        a,b=methods
        lookup={(r['row_id'],r['method']):r for r in rows}
        paired=sorted({rid for rid,m in lookup if (rid,a) in lookup and (rid,b) in lookup})
        a_only=sum(lookup[rid,a]['raw_label_flip']=='1' and lookup[rid,b]['raw_label_flip']=='0' for rid in paired)
        b_only=sum(lookup[rid,a]['raw_label_flip']=='0' and lookup[rid,b]['raw_label_flip']=='1' for rid in paired)
        m={'method_a':a,'method_b':b,'paired_n':len(paired),'a_only':a_only,'b_only':b_only,'mcnemar_exact_p':mcnemar_exact(a_only,b_only),'note':'Only reviewed/scored pairs; result is not validated attack success'}
        atomic_csv(out/'paired_mcnemar.csv',[m],list(m))
    print('Approved candidate metrics:',len(rows),'TP denominator:',len(tps),'results at',out)
if __name__=='__main__':main()
