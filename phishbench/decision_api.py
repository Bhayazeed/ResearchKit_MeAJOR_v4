"""Direct structured decision requests; no chat-model fallback."""
import http.client
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        # Never forward a bearer credential to a redirected login/other host.
        return None


def authenticated_endpoint(url,key_env,require_systemone=True):
    parsed=urllib.parse.urlsplit(url)
    local=parsed.hostname in ('localhost','127.0.0.1','::1')
    if not parsed.hostname or not (parsed.scheme=='https' or (local and parsed.scheme=='http')):
        raise ValueError('Use the full HTTPS systemone URL (HTTP allowed only on localhost)')
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Endpoint URL must not contain credentials, query parameters or fragments')
    if require_systemone and not parsed.path.rstrip('/').endswith('/systemone'):
        raise ValueError('Supply the direct systemone endpoint, not /api/chat/completions or a tool ID')
    key=os.environ.get(key_env,'').strip()
    if not key or key=='API_KEY' or key.startswith('PASTE_'):
        raise ValueError('Set the API key in environment variable '+key_env)
    return url,{'Content-Type':'application/json','Authorization':'Bearer '+key}


def post_json(url,payload,headers,timeout=180,attempts=3):
    if attempts<1 or timeout<=0:
        raise ValueError('Request attempts and timeout must be positive')
    opener=urllib.request.build_opener(NoRedirect())
    request=urllib.request.Request(url,data=json.dumps(payload).encode('utf-8'),headers=headers,method='POST')
    failure='request failed'
    for attempt in range(1,attempts+1):
        try:
            with opener.open(request,timeout=timeout) as response:
                result=json.load(response)
            if not isinstance(result,dict):
                raise ValueError('Decision endpoint returned a non-object JSON response')
            return result
        except urllib.error.HTTPError as exc:
            code=exc.code;exc.close()
            if code in (401,403):
                raise RuntimeError(f'Decision HTTP {code}: check API key and access to this endpoint; no decision recorded') from None
            if code not in (408,429,500,502,503,504):
                raise RuntimeError(f'Decision HTTP {code}: verify the direct systemone route and payload; no decision recorded') from None
            failure=f'HTTP {code}'
        except (urllib.error.URLError,ConnectionError,TimeoutError,http.client.RemoteDisconnected,http.client.IncompleteRead) as exc:
            failure=type(exc).__name__
        except (json.JSONDecodeError,UnicodeDecodeError):
            raise RuntimeError('Decision endpoint did not return valid JSON; no decision recorded') from None
        if attempt<attempts:
            delay=min(30,2**(attempt-1))
            print(f'Decision request {attempt}/{attempts} failed ({failure}); retrying in {delay}s...',file=sys.stderr,flush=True)
            time.sleep(delay)
    raise RuntimeError(f'Decision request failed after {attempts} attempts ({failure}); checkpoint preserved')


def choice_answer(result,question,criteria):
    answers=result.get('answers')
    answer=answers.get(question) if isinstance(answers,dict) else None
    if not isinstance(answer,dict) or answer.get('choice') not in criteria:
        raise ValueError('Missing/invalid structured answers.'+question+'; chat text is not a Decider result')
    choice=answer['choice']
    probabilities=answer.get('probabilities',{})
    if isinstance(probabilities,list):
        probabilities={x.get('option',x.get('label')):x.get('probability') for x in probabilities if isinstance(x,dict)}
    probability=probabilities.get(choice) if isinstance(probabilities,dict) else None
    confidence=answer.get('confidence')
    for value in (probability,confidence):
        if value not in (None,''):
            if isinstance(value,bool) or not math.isfinite(float(value)) or not 0<=float(value)<=1:
                raise ValueError('Invalid decision probability/confidence')
    return choice,probability,confidence
