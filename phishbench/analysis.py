"""Common analysis: binomial ASR, stage-wise, paired McNemar and screening."""
import math
import random
from collections import Counter,defaultdict

def as_float(num,den):return round(100*num/den,4) if den else None

def bootstrap_interval(successes, n, draws=1000, seed=42):
    """Percentile bootstrap for binary ITA outcomes; no normality assumption."""
    if n<=0:return ('','')
    r=random.Random(seed)
    arr=[1]*successes+[0]*(n-successes)
    outcomes=sorted(sum(r.choices(arr,k=n))/n*100 for _ in range(draws))
    return (round(outcomes[int(.025*(draws-1))],4),round(outcomes[int(.975*(draws-1))],4))


def summarize(records):
    by=defaultdict(list)
    for r in records:by[(r['victim_id'],r['method'])].append(r)
    out=[]
    for (victim,method),all_rows in sorted(by.items()):
        pool=[r for r in all_rows if r['tp_pool_member']=='1']
        n=len(pool);success=sum(r['attack_success']=='1' for r in pool)
        valid=sum(r.get('validated_attack_success','')=='1' for r in pool)
        reviewed=sum(r.get('human_review_status')=='completed' for r in pool)
        successful_reviewed=sum(r.get('human_review_status')=='completed' and r.get('attack_success')=='1' for r in pool)
        scored=sum(r.get('candidate_scored')=='1' for r in pool)
        s1=sum(r.get('stage1_label_flip')=='1' for r in pool)
        s2=sum(r.get('stage2_additional_flip')=='1' for r in pool)
        failures=Counter(r.get('error_kind','') for r in pool if r.get('error_kind'))
        lo,hi=bootstrap_interval(success,n)
        out.append({'asr_bootstrap_95_low':lo,'asr_bootstrap_95_high':hi,'victim_id':victim,'method':method,'all_rows':len(all_rows),'tp_pool':n,'success_raw':success,'asr_ita_percent':as_float(success,n),'robust_accuracy_percent':as_float(n-success,n),'asr_scored_percent':as_float(success,scored),'stage1_success':s1,'stage1_asr_percent':as_float(s1,n),'stage2_additional':s2,'stage2_cumulative_asr_percent':as_float(s1+s2,n),'candidate_scored':scored,'human_reviewed':reviewed,'raw_success_reviewed':successful_reviewed,'all_raw_flips_reviewed':str(successful_reviewed==success),'validated_success':valid,'validated_asr_percent':as_float(valid,n) if successful_reviewed==success and n else '', 'error_count':sum(failures.values()),'error_breakdown':str(dict(failures))})
    return out

def mcnemar_exact(b,c):
    n=b+c
    if n==0:return 1.0
    k=min(b,c)
    vals=[math.exp(math.lgamma(n+1)-math.lgamma(i+1)-math.lgamma(n-i+1)-n*math.log(2)) for i in range(k+1)]
    return min(1.0,2*math.fsum(vals))

def pair(a,b):
    if not a or not b:raise ValueError('Empty input')
    ma={x['row_id']:x for x in a};mb={x['row_id']:x for x in b}
    if len(ma)!=len(a) or len(mb)!=len(b) or set(ma)!=set(mb):raise ValueError('Unmatched row IDs')
    if len({x['victim_id'] for x in a+b})!=1:raise ValueError('Must compare same victim')
    counts=Counter()
    for key in ma:
        x,y=ma[key],mb[key]
        if any(x.get(field)!=y.get(field) for field in ('dataset_label','original_sha256','baseline_prediction','tp_pool_member')):
            raise ValueError('Paired provenance/baseline mismatch at '+key)
        if x['tp_pool_member']!='1':continue
        counts[(x['attack_success']=='1',y['attack_success']=='1')]+=1
    b_only=counts[(True,False)];c_only=counts[(False,True)]
    return {'victim_id':a[0]['victim_id'],'tp_paired_n':sum(counts.values()),'both_success':counts[(True,True)],'gan_only_success':b_only,'llm_only_success':c_only,'neither_success':counts[(False,False)],'mcnemar_exact_p':mcnemar_exact(b_only,c_only),'caution':'raw label flips; unequal attacker query budgets and human validity require separate comparison'}
