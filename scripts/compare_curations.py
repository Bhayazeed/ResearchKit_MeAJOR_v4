#!/usr/bin/env python3
"""Paired quality-decision agreement on a shared MeAJOR sample."""
import argparse,sys,csv
from collections import Counter
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from phishbench.data import read_csv,atomic_csv
from phishbench.analysis import mcnemar_exact

def main():
 p=argparse.ArgumentParser();p.add_argument('--a',required=True);p.add_argument('--b',required=True);p.add_argument('--output',required=True);args=p.parse_args()
 a=read_csv(args.a);b=read_csv(args.b);ma={r['row_id']:r for r in a};mb={r['row_id']:r for r in b}
 if len(ma)!=len(a) or len(mb)!=len(b) or set(ma)!=set(mb):raise ValueError('Unpaired cohorts')
 if not a:raise ValueError('Empty quality audits')
 for rid in ma:
  if any(ma[rid].get(key)!=mb[rid].get(key) for key in ('original_sha256','dataset_label')):raise ValueError('Quality audit provenance mismatch at '+rid)
  if any(row.get('quality_accepted') not in ('0','1') for row in (ma[rid],mb[rid])):raise ValueError('Invalid quality acceptance at '+rid)
 counts=Counter((ma[rid]['quality_accepted'],mb[rid]['quality_accepted']) for rid in ma)
 row={'a':a[0].get('quality_model'),'b':b[0].get('quality_model'),'n':len(ma),'both_accepted':counts[('1','1')],'a_only':counts[('1','0')],'b_only':counts[('0','1')],'both_rejected':counts[('0','0')],'mcnemar_p':mcnemar_exact(counts[('1','0')],counts[('0','1')])}
 atomic_csv(args.output,[row],list(row));print(row)
if __name__=='__main__':main()
