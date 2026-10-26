"""Ollama /api/chat and decision /v1/systemone clients, Python standard library.
Never call a cloud service; host URL is restricted to localhost by default.
"""
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass,field
from phishbench.classification import INSTRUCTIONS,CRITERIA

class BackendError(Exception):
    def __init__(self,kind,message,status=""):
        super().__init__(message)
        self.kind,self.status=kind,str(status)

@dataclass
class Prediction:
    label:int
    probabilities:dict=field(default_factory=dict)
    confidence:float|None=None
    meta:dict=field(default_factory=dict)


def parse_label(output):
    if not isinstance(output,str):raise BackendError('invalid_label','Non-string classifier response')
    value=re.sub(r'\s+',' ',output).strip().upper().strip(' .!"\'`')
    if value=='PHISHING':return 1
    if value in ('NON_PHISHING','NON-PHISHING','NON PHISHING','BENIGN'):return 0
    raise BackendError('invalid_label','Unexpected classifier response: '+repr(output[:130]))


def ensure_local_url(url, allow_remote=False):
    parsed=urllib.parse.urlparse(url)
    if parsed.scheme!='http' and not (allow_remote and parsed.scheme=='https'):
        raise ValueError('Ollama URL must be http localhost (or explicitly --allow-remote)')
    if not allow_remote and (parsed.hostname not in ('localhost','127.0.0.1','::1')):
        raise ValueError('This package is local-only; remote Ollama needs explicit --allow-remote')
    return url.rstrip('/')

class Ollama:
    def __init__(self,base='http://127.0.0.1:11434',timeout=240,allow_remote=False,transport=None):
        self.base=ensure_local_url(base,allow_remote)
        self.timeout=timeout
        self.transport=transport
        self.calls=0
        self.last_call={}

    def post(self,endpoint,payload):
        self.last_call={}
        self.calls+=1
        try:
            if self.transport is not None:reply=self.transport(endpoint,payload)
            else:
                req=urllib.request.Request(self.base+endpoint, data=json.dumps(payload).encode('utf-8'),headers={'Content-Type':'application/json'},method='POST')
                with urllib.request.urlopen(req,timeout=self.timeout) as response:
                    reply=json.load(response)
            if not isinstance(reply,dict):raise BackendError('invalid_response','Ollama response not an object')
            if reply.get('error'):raise BackendError('model_error',str(reply['error']))
            self.last_call={'finish_reason':reply.get('done_reason',''), 'prompt_tokens':reply.get('prompt_eval_count',reply.get('usage',{}).get('input_tokens','')), 'completion_tokens':reply.get('eval_count',reply.get('usage',{}).get('output_tokens',''))}
            return reply
        except urllib.error.HTTPError as exc:
            detail=exc.read(1200).decode('utf-8',errors='replace')
            raise BackendError('http_error',detail,exc.code) from exc
        except (urllib.error.URLError,TimeoutError) as exc:
            raise BackendError('connection_error',str(exc)) from exc

    def tags(self):
        if self.transport is not None:
            result=self.transport('/api/tags',{})
            return [x.get('name','') for x in result.get('models',[])]
        with urllib.request.urlopen(self.base+'/api/tags',timeout=min(20,self.timeout)) as response:
            return [m.get('name','') for m in json.load(response).get('models',[])]

    def classify_chat(self,model,text,system_prompt,max_predict=16):
        reply=self.post('/api/chat',{'model':model,'stream':False,'think':False,'messages':[{'role':'system','content':system_prompt},{'role':'user','content':'<EMAIL_DATA>\n'+text+'\n</EMAIL_DATA>'}], 'options':{'temperature':0,'num_predict':max_predict}})
        msg=reply.get('message',{})
        answer=msg.get('content','')
        if not answer or (msg.get('refusal') or re.search(r'(?i)^i cannot (assist|comply)',answer.strip())):
            raise BackendError('model_refusal','Classifier refused / produced empty response')
        return Prediction(parse_label(answer),meta=self.last_call.copy())

    def classify_decision(self,model,text):
        reply=self.post('/v1/systemone',{'model':model,'state':text,'questions':{'email_class':{'type':'choice','instructions':INSTRUCTIONS,'criteria':CRITERIA}}})
        ans=reply.get('answers',{}).get('email_class')
        if not isinstance(ans,dict):raise BackendError('invalid_decision_response','Missing answers.email_class from /v1/systemone')
        label=parse_label(ans.get('choice',''))
        probs=ans.get('probabilities',{})
        if isinstance(probs,list):
            # Some clients return [{option,probability}]; do not assume ordering.
            probs={str(x.get('option',x.get('label',''))):x.get('probability') for x in probs if isinstance(x,dict)}
        if not isinstance(probs,dict):probs={}
        clean={}
        for key,value in probs.items():
            try:clean[str(key)]=float(value)
            except (ValueError,TypeError):pass
        confidence=ans.get('confidence')
        try:confidence=float(confidence) if confidence is not None else None
        except (TypeError,ValueError):confidence=None
        return Prediction(label,clean,confidence,reply)

    def rewrite(self,model,system_prompt,user_prompt,temperature=0.2,max_predict=2048):
        reply=self.post('/api/chat',{'model':model,'stream':False,'think':False,'messages':[{'role':'system','content':system_prompt},{'role':'user','content':user_prompt}], 'options':{'temperature':temperature,'num_predict':max_predict}})
        content=reply.get('message',{}).get('content','')
        if not isinstance(content,str) or not content.strip():raise BackendError('empty_generation','Generator returned no text')
        if reply.get('message',{}).get('refusal'):raise BackendError('model_refusal','Generator refusal')
        return content.strip()
