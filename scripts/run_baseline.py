#!/usr/bin/env python3
"""Defensive baseline classification for frozen MeAJOR cohorts; no generation."""
import argparse,csv,hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from phishbench.data import read_dataset,atomic_csv,atomic_json,append_checkpoint,hash_file,load_row_checkpoint
from phishbench.ollama_backend import Ollama,BackendError
from phishbench.classification import CHAT_PROMPT,INSTRUCTIONS,CRITERIA
from phishbench.workflow import CURATED_DATASET,BASELINE_DIR,validate_curated_rows

PROMPT=CHAT_PROMPT

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--input',default=CURATED_DATASET)
    p.add_argument('--require-curated',action='store_true',help='Validate English and body length screening before victim classification')
    p.add_argument('--label',choices=['0','1','all'],default='1',help='Gold label to include (default: 1; no sampling)')
    p.add_argument('--config',default='config/models.json')
    p.add_argument('--output-dir',default=BASELINE_DIR)
    p.add_argument('--victims',nargs='*')
    p.add_argument('--base-url')
    p.add_argument('--decision-base-url',default='http://127.0.0.1:11435')
    p.add_argument('--checkpoint-every',type=int,default=25)
    p.add_argument('--dry-run',action='store_true')
    args=p.parse_args()
    if not Path(args.input).is_file():p.error('Input does not exist: '+args.input+'; run RUN_CURATE_PPLX.bat to create the new curated dataset first.')
    print('Loading input:',args.input,flush=True)
    config=json.loads(Path(args.config).read_text());rows=read_dataset(args.input,label=args.label)
    if not rows:raise ValueError('No input rows match label filter: '+args.label)
    if args.require_curated or args.input==CURATED_DATASET:validate_curated_rows(rows)
    print('Selected label',args.label,':',len(rows),'rows',flush=True)
    victims=[v for v in config['victims'] if v['id'] in args.victims] if args.victims else [v for v in config['victims'] if v.get('enabled',True)]
    if not victims:raise ValueError('No matching victims')
    outdir=Path(args.output_dir);outdir.mkdir(parents=True,exist_ok=True)
    dataset_hash=hash_file(args.input)
    plan=[{'victim_id':v['id'],'tag':v['tag'],'kind':v['kind'],'rows':len(rows),'label_filter':args.label,'status':'planned'} for v in victims]
    atomic_csv(outdir/'run_plan.csv',plan,list(plan[0]))
    if args.dry_run:
        print('Dry run:',len(rows),'rows for',','.join(v['id'] for v in victims));return
    fields=['row_id','dataset_label','original_sha256','source_corpus','baseline_prediction','baseline_status','baseline_error','decision_confidence','decision_probability_phishing','victim_id','victim_model','victim_kind']
    for victim in victims:
        path=outdir/(victim['id']+'_baseline.csv');journal=Path(str(path)+'.checkpoint.jsonl');manifest=Path(str(path)+'.run.json')
        signature={'dataset_hash':dataset_hash,'model':victim,'baseline_prompt_hash':hashlib.sha256(PROMPT.encode()).hexdigest(),'decision_endpoint':args.decision_base_url,'chat_endpoint':args.base_url or config['ollama_base_url']}
        signature['classification_task_hash']=hashlib.sha256(json.dumps([INSTRUCTIONS,CRITERIA],sort_keys=True).encode()).hexdigest()
        if args.label!='all':signature['label_filter']=args.label
        if manifest.exists():
            if json.loads(manifest.read_text())!=signature:raise ValueError('Baseline changed; use a new output directory: '+str(path))
        elif journal.exists():raise ValueError('Missing manifest for checkpoint '+str(journal))
        else:atomic_json(manifest,signature)
        cached=load_row_checkpoint(journal, ('baseline_status','baseline_prediction','dataset_label'))
        client=Ollama(args.decision_base_url if victim['kind']=='decision' else args.base_url or config['ollama_base_url'])
        print('Victim:',victim['id'],'cached',len(cached),'of',len(rows),flush=True)
        result=[]
        for idx,row in enumerate(rows,1):
            rid=row['row_id'];item=cached.get(rid)
            if item is None:
                item={'row_id':rid,'dataset_label':row['dataset_label'],'original_sha256':row['original_sha256'],'source_corpus':row.get('source_corpus',''),'baseline_prediction':'','baseline_status':'','baseline_error':'','decision_confidence':'','decision_probability_phishing':'','victim_id':victim['id'],'victim_model':victim['tag'],'victim_kind':victim['kind']}
                try:
                    pred=client.classify_decision(victim['tag'],row['original_text']) if victim['kind']=='decision' else client.classify_chat(victim['tag'],row['original_text'],PROMPT)
                    item['baseline_prediction']=str(pred.label);item['baseline_status']='ok'
                    item['decision_confidence']=pred.confidence if pred.confidence is not None else ''
                    item['decision_probability_phishing']=pred.probabilities.get('PHISHING','')
                except BackendError as exc:
                    if exc.kind in ('connection_error','http_error'):
                        print('Transient backend failure: no checkpoint will be committed for this row; rerun after fixing connection.',file=sys.stderr)
                        raise
                    item['baseline_status']=exc.kind;item['baseline_error']=str(exc)[:200]
                except (KeyboardInterrupt,SystemExit):raise
                except Exception as exc:
                    print('Unrecoverable API error:',repr(exc),'resume this command',file=sys.stderr)
                    raise
                append_checkpoint(journal,item);cached[rid]=item
            if item['original_sha256']!=row['original_sha256']:raise ValueError('Checkpoint sha mismatch')
            result.append(item)
            if idx%max(1,args.checkpoint_every)==0:atomic_csv(path,result,fields);print(victim['id'],idx,'/',len(rows),flush=True)
        atomic_csv(path,result,fields)
        tp=sum(r['dataset_label']=='1' and r['baseline_prediction']=='1' for r in result)
        print('Finished',victim['id'],'correct-class-1 pool',tp,'of',len(rows))
if __name__=='__main__':main()
