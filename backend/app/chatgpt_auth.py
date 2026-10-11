"""Official loopback PKCE sign-in; credentials never leave backend storage."""
import base64
import hashlib
import json
import logging
import os
from pathlib import Path
import secrets
import ssl
import tempfile
import threading
import time
from urllib.parse import urlencode, urlparse
from urllib.request import Request,urlopen
from urllib.error import HTTPError, URLError
import uuid

import jwt
import certifi
from .config import database_path

ISSUER='https://auth.openai.com'
RESOURCE='https://api.openai.com/v1'
CALLBACK='http://127.0.0.1:8000/auth/callback'
SCOPES='openid offline_access resource.invoke chatgpt.tokens.use.direct'
_LOCK=threading.RLock()
_PENDING={}


def _tls_context():
    # Framework Python on macOS may have no default CA file installed.
    return ssl.create_default_context(cafile=certifi.where())


class SignInError(ValueError):
    """Only fixed, non-secret diagnostics may be shown in the browser."""
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def failure_message(error):
    if isinstance(error, SignInError):
        return str(error)
    if isinstance(error, (jwt.PyJWTError, jwt.PyJWKClientError)):
        return 'OpenAI identity verification failed. Start a new sign-in; existing account credentials were preserved.'
    if isinstance(error, HTTPError):
        return f'OpenAI sign-in could not finish (HTTP {error.code}). Start a new sign-in; if it repeats, check account eligibility.'
    if isinstance(error, ssl.SSLCertVerificationError) or (isinstance(error, URLError) and isinstance(error.reason, ssl.SSLCertVerificationError)):
        return 'The backend could not verify OpenAI’s TLS certificate. Check the backend certificate bundle; existing account credentials were preserved.'
    if isinstance(error, (URLError, OSError, TimeoutError)):
        return 'The backend could not reach OpenAI to finish sign-in. Check the connection and start again.'
    return 'The sign-in response could not be validated. Start again; existing account credentials were preserved.'


class _CallbackLogFilter(logging.Filter):
    def filter(self,record):
        if isinstance(record.args,tuple) and len(record.args)>=3 and isinstance(record.args[2],str) and record.args[2].startswith('/auth/callback'):
            args=list(record.args);args[2]='/auth/callback';record.args=tuple(args)
        return True


logging.getLogger('uvicorn.access').addFilter(_CallbackLogFilter())


def _file(path=None):
    return Path(path or database_path()).parent/'credentials'/'chatgpt.json'


def _read(path=None):
    target=_file(path)
    if not target.exists():
        return {'accounts':{},'active':None,'host_id':'urn:uuid:'+str(uuid.uuid4())}
    data=json.loads(target.read_text())
    changed=False
    for account in data['accounts'].values():
        if 'email' in account:
            del account['email'];changed=True
        if 'id_token' in account.get('tokens',{}):
            del account['tokens']['id_token'];changed=True
    if changed:_save(data,path)
    return data


def _save(data,path=None):
    target=_file(path);target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd,tmp=tempfile.mkstemp(dir=target.parent)
    try:
        with os.fdopen(fd,'w') as stream:
            json.dump(data,stream);stream.flush();os.fsync(stream.fileno())
        os.replace(tmp,target)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def _json(url,form=None,token=None):
    headers={'Accept':'application/json'}
    if token:headers['Authorization']='Bearer '+token
    body=urlencode(form).encode() if form is not None else None
    if body is not None:headers['Content-Type']='application/x-www-form-urlencoded'
    with urlopen(Request(url,data=body,headers=headers),timeout=30,context=_tls_context()) as response:
        raw=response.read()
        return json.loads(raw) if raw else {}


def _discovery():
    data=_json(ISSUER+'/.well-known/openid-configuration')
    if data.get('issuer')!=ISSUER:raise ValueError('Unexpected OpenAI identity issuer')
    for field in ['jwks_uri','revocation_endpoint']:
        if field in data and (urlparse(data[field]).scheme!='https' or urlparse(data[field]).netloc!='auth.openai.com'):
            raise ValueError('Unexpected OpenAI identity endpoint')
    return data


def start(path=None,account=None):
    with _LOCK:
        data=_read(path)
        selected=data['accounts'].get(account) if account else None
        if account and not selected:raise ValueError('Unknown saved ChatGPT account')
        _save(data,path)
        verifier=secrets.token_urlsafe(48);state=secrets.token_urlsafe(32);nonce=secrets.token_urlsafe(32)
        pending={'verifier':verifier,'nonce':nonce,'created':time.time(),'path':path,'client_id':selected['client_id'] if selected else None,'subject':selected['subject'] if selected else None}
        # Browser handoffs may create several tabs; keep each fresh attempt valid.
        for old_state in list(_PENDING):
            if time.time()-_PENDING[old_state]['created']>600:
                del _PENDING[old_state]
        while len(_PENDING)>=8:
            del _PENDING[min(_PENDING,key=lambda key:_PENDING[key]['created'])]
        _PENDING[state]=pending
        args={'client_id':pending['client_id'] or 'dynamic_agent_client','ext_agent_host_id':data['host_id'],
              'response_type':'code','redirect_uri':CALLBACK,'scope':SCOPES,'resource':RESOURCE,
              'state':state,'nonce':nonce,'code_challenge_method':'S256',
              'code_challenge':base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')}
        if not selected:args['agent_name_hint']='Garmin Health & Training'
        # Account picker is intentional; tokens are never returned in URLs.
        return {'authorization_url':ISSUER+'/api/accounts/authorize?'+urlencode(args)}


def finish(params):
    with _LOCK:
        state=params.get('state','');pending=_PENDING.pop(state,None)
        if not pending or time.time()-pending['created']>600:raise SignInError('expired_state','This sign-in link expired, was already used, or belongs to an earlier backend session. Return to Settings and generate a fresh link for Chrome.')
        if params.get('error'):raise SignInError('authorization_denied','OpenAI did not authorize this connection. Start again and review the requested ChatGPT plan permission.')
        client=params.get('client_id') or pending['client_id']
        if not client or client=='dynamic_agent_client' or (pending['client_id'] and client!=pending['client_id']):raise SignInError('client_id_mismatch','OpenAI did not return the expected app registration. Generate a new sign-in link in Settings.')
        if not params.get('code'):raise SignInError('missing_code','OpenAI did not return an authorization code. Start sign-in again from Settings.')
        tokens=_json(ISSUER+'/api/accounts/oauth/token',{'grant_type':'authorization_code','client_id':client,'code':params['code'],
            'code_verifier':pending['verifier'],'redirect_uri':CALLBACK,'resource':RESOURCE})
        config=_discovery();key=jwt.PyJWKClient(config['jwks_uri'],ssl_context=_tls_context()).get_signing_key_from_jwt(tokens['id_token'])
        claims=jwt.decode(tokens['id_token'],key.key,algorithms=['RS256'],audience=client,issuer=ISSUER,options={'require':['exp','iss','aud','sub','nonce']})
        if not secrets.compare_digest(str(claims['nonce']),pending['nonce']):raise ValueError('ChatGPT identity nonce did not match')
        if pending['subject'] and claims['sub']!=pending['subject']:raise ValueError('ChatGPT account changed during reauthorization')
        if tokens.get('token_type','').lower()!='bearer' or not tokens.get('access_token'):raise ValueError('Missing ChatGPT access credential')
        data=_read(pending['path'])
        # Identity token is verified transiently, never retained as personal context.
        tokens.pop('id_token',None)
        data['accounts'][client]={'client_id':client,'subject':claims['sub'],
            'tokens':tokens,'scopes':tokens.get('scope','').split(),'expires_at':time.time()+int(tokens['expires_in'])}
        data['active']=client;_save(data,pending['path'])
        return status(pending['path'])


def status(path=None):
    with _LOCK:
        data=_read(path);account=data['accounts'].get(data['active'])
        permitted=bool(account and account.get('tokens',{}).get('access_token') and 'chatgpt.tokens.use.direct' in account.get('scopes',[]))
        return {'connected':permitted,'active':data['active'],
            'accounts':[{'id':key,'label':'ChatGPT account '+str(index)+' · '+key[-8:],'signed_in':bool(a.get('tokens'))} for index,(key,a) in enumerate(data['accounts'].items(),1)],
            'detail':'ChatGPT account connected; model access and plan limits apply.' if permitted else 'Continue with ChatGPT and allow plan usage.'}


def access_token(path=None):
    with _LOCK:
        data=_read(path);account=data['accounts'].get(data['active'])
        if not account or not account.get('tokens') or 'chatgpt.tokens.use.direct' not in account.get('scopes',[]):raise RuntimeError('Connect your ChatGPT account in Settings and allow plan usage.')
        if account['expires_at']<=time.time()+60:
            tokens=_json(ISSUER+'/api/accounts/oauth/token',{'grant_type':'refresh_token','client_id':account['client_id'],
                'refresh_token':account['tokens']['refresh_token'],'resource':RESOURCE})
            if not tokens.get('access_token') or not tokens.get('refresh_token'):raise RuntimeError('ChatGPT renewal failed; reconnect in Settings.')
            tokens.pop('id_token',None)
            account['tokens']={**account['tokens'],**tokens}
            account['scopes']=tokens.get('scope',' '.join(account['scopes'])).split()
            account['expires_at']=time.time()+int(tokens['expires_in']);_save(data,path)
        if 'chatgpt.tokens.use.direct' not in account['scopes']:raise RuntimeError('ChatGPT plan usage is not authorized; reconnect in Settings.')
        return account['tokens']['access_token']


def models(path=None):
    payload=_json(RESOURCE+'/models',token=access_token(path))
    return [{'id':m['slug'],'name':m['display_name']} for m in payload.get('models',[]) if m.get('visibility')=='list']


def sign_out(path=None):
    with _LOCK:
        data=_read(path);account=data['accounts'].get(data['active']);confirmed=True
        if account and account.get('tokens'):
            try:
                endpoint=_discovery()['revocation_endpoint']
                _json(endpoint,{'token':account['tokens']['refresh_token'],'token_type_hint':'refresh_token','client_id':account['client_id']})
            except Exception:confirmed=False
            account['tokens']={};account['scopes']=[];_save(data,path)
        return {'remote_revocation_confirmed':confirmed,**status(path)}
