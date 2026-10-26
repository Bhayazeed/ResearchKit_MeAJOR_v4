"""Automated diagnostics are NOT proof of semantic preservation."""
import re
from collections import Counter

WORDS=re.compile(r"\b[\w]+\b",re.UNICODE)
NUM=re.compile(r'(?<!\w)\d+(?:[.,]\d+)*(?!\w)')
URL=re.compile(r'(?:https?://|www\.)[^\s<>]+',re.I)
EMAIL=re.compile(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}')
ANON=re.compile(r'\[[A-Z][A-Z_]+\]')

def tokens(text):return [x.lower() for x in WORDS.findall(text)]

def retention(original,modified,pattern):
    lhs=Counter(pattern.findall(original)); rhs=Counter(pattern.findall(modified))
    if not lhs:return 1.0
    return sum(min(count,rhs.get(k,0)) for k,count in lhs.items())/sum(lhs.values())

def screen(original,modified):
    a=tokens(original);b=tokens(modified)
    lr=len(b)/len(a) if a else 0.0
    jac=len(set(a)&set(b))/len(set(a)|set(b)) if a or b else 1.0
    vals={'length_ratio':round(lr,6),'word_ratio':round(lr,6),'jaccard':round(jac,6),'numeric_retention':retention(original,modified,NUM),'url_retention':retention(original,modified,URL),'email_retention':retention(original,modified,EMAIL),'anchor_retention':retention(original,modified,ANON)}
    flags=[]
    if not modified.strip():flags.append('empty_output')
    if lr<0.5:flags.append('short_or_collapsed')
    if lr>2.0:flags.append('expanded')
    for key in ('numeric_retention','url_retention','email_retention','anchor_retention'):
        if vals[key]<1:flags.append('lost_'+key)
    vals['flags']=flags;vals['status']='warning' if flags else 'pass'
    return vals
