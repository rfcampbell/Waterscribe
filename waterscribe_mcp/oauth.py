"""
Single-user OAuth 2.1 authorization server for the claude.ai connector.

claude.ai registers itself (DCR), sends Rob to /authorize, he types the passphrase on /login,
and claude.ai gets tokens. Only token hashes are stored. State lives in one JSON file.
"""
import hashlib
import hmac
import json
import os
import secrets
import time
from html import escape
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from starlette.requests import Request
from starlette.responses import HTMLResponse as _HTML, RedirectResponse

from mcp.server.auth.provider import (AccessToken, AuthorizationCode, AuthorizationParams, AuthorizeError,
                                      RefreshToken, RegistrationError, TokenError, construct_redirect_uri)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

SCOPE = 'waterscribe'
SUBJECT = 'rob'
ACCESS_TTL = 24 * 3600
REFRESH_TTL = 90 * 24 * 3600
CODE_TTL = 300
PENDING_TTL = 600
MAX_CLIENTS = 50
# Redirect URIs a client may register: claude.ai's callback, plus loopback for local testing.
ALLOWED_REDIRECTS = {'https://claude.ai/api/mcp/auth_callback', 'https://claude.com/api/mcp/auth_callback'}
LOGIN_FAIL_LIMIT = 10          # failed passphrases per LOGIN_FAIL_WINDOW before /login locks
LOGIN_FAIL_WINDOW = 3600


def HTMLResponse(body, status=200):
    # login page: never framed or cached. No CSP form-action: browsers apply it to the redirect to claude.ai
    return _HTML(body, status, headers={'X-Frame-Options': 'DENY', 'Cache-Control': 'no-store',
                                        'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'"})


def _h(token):
    return hashlib.sha256(token.encode()).hexdigest()


def hash_passphrase(p, salt=None):
    salt = salt or secrets.token_bytes(16)
    return 'scrypt$' + salt.hex() + '$' + hashlib.scrypt(p.encode(), salt=salt, n=2**15, r=8, p=1,
                                                         maxmem=64 * 2**20).hex()


def check_passphrase(p, stored):
    try:
        _, salt, _ = stored.split('$')
    except (AttributeError, ValueError):
        return False
    return hmac.compare_digest(hash_passphrase(p, bytes.fromhex(salt)), stored)


def redirect_allowed(uri):
    u = urlparse(str(uri))
    if u.scheme == 'http' and u.hostname in ('localhost', '127.0.0.1'):
        return True
    return f'{u.scheme}://{u.netloc}{u.path}' in ALLOWED_REDIRECTS and not u.query


class Provider:
    def __init__(self, state_dir, resource_url, audit):
        self.path = Path(state_dir) / 'oauth.json'
        self.passphrase_path = Path(state_dir) / 'passphrase'
        self.resource = resource_url
        self.audit = audit
        self.pending = {}          # login request id -> (client_id, params, expires) ; memory only
        self.fails = []            # timestamps of failed logins
        self.s = json.loads(self.path.read_text()) if self.path.exists() else {}
        for k in ('clients', 'codes', 'access', 'refresh'):
            self.s.setdefault(k, {})

    def _save(self):
        now = time.time()
        for k in ('codes', 'access', 'refresh'):
            self.s[k] = {h: v for h, v in self.s[k].items() if (v.get('expires_at') or now + 1) > now}
        tmp = self.path.with_suffix('.tmp')
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump(self.s, f, indent=1)
        os.replace(tmp, self.path)

    # clients
    async def get_client(self, client_id):
        c = self.s['clients'].get(client_id)
        return OAuthClientInformationFull.model_validate(c) if c else None

    async def register_client(self, client_info):
        bad = [str(u) for u in client_info.redirect_uris or [] if not redirect_allowed(u)]
        if bad or not client_info.redirect_uris:
            self.audit('oauth.register_rejected', {'redirect_uris': [str(u) for u in client_info.redirect_uris or []]})
            raise RegistrationError('invalid_redirect_uri', f'redirect URI not allowed: {", ".join(bad) or "none"}')
        if len(self.s['clients']) >= MAX_CLIENTS:
            # drop the oldest registration rather than refuse; claude.ai re-registers freely
            oldest = min(self.s['clients'], key=lambda k: self.s['clients'][k].get('client_id_issued_at') or 0)
            del self.s['clients'][oldest]
        self.s['clients'][client_info.client_id] = client_info.model_dump(mode='json', exclude_none=True)
        self._save()
        self.audit('oauth.register', {'client_id': client_info.client_id, 'client_name': client_info.client_name,
                                      'redirect_uris': [str(u) for u in client_info.redirect_uris]})

    # authorize -> /login
    async def authorize(self, client, params: AuthorizationParams):
        if not self.passphrase_path.exists():
            raise AuthorizeError('server_error', 'no passphrase set on the server (run set-passphrase)')
        now = time.time()
        self.pending = {k: v for k, v in self.pending.items() if v[2] > now}
        req = secrets.token_urlsafe(24)
        self.pending[req] = (client.client_id, params, now + PENDING_TTL)
        return f'{self.resource.rsplit("/mcp", 1)[0]}/login?req={req}'

    async def login(self, request: Request):
        req = request.query_params.get('req', '')
        if request.method == 'POST':
            form = parse_qs((await request.body()).decode(errors='replace'))
            req = (form.get('req') or [''])[0]
        entry = self.pending.get(req)
        if not entry or entry[2] < time.time():
            return HTMLResponse(_page('This sign-in link has expired. Start again from claude.ai.'), 400)
        client_id, params, _ = entry
        client = self.s['clients'].get(client_id, {})
        if request.method == 'GET':
            return HTMLResponse(_page(None, req, client.get('client_name') or client_id))

        now = time.time()
        self.fails = [t for t in self.fails if t > now - LOGIN_FAIL_WINDOW]
        if len(self.fails) >= LOGIN_FAIL_LIMIT:
            self.audit('oauth.login_locked', {'client_id': client_id})
            return HTMLResponse(_page('Too many wrong passphrases. Try again in an hour.'), 429)
        passphrase = (form.get('passphrase') or [''])[0]
        if not check_passphrase(passphrase, self.passphrase_path.read_text().strip()):
            self.fails.append(now)
            self.audit('oauth.login_failed', {'client_id': client_id, 'ip': request.headers.get('x-forwarded-for')})
            return HTMLResponse(_page('Wrong passphrase.', req, client.get('client_name') or client_id), 401)

        del self.pending[req]
        code = secrets.token_urlsafe(32)
        self.s['codes'][_h(code)] = AuthorizationCode(
            code=_h(code), scopes=params.scopes or [SCOPE], expires_at=now + CODE_TTL, client_id=client_id,
            code_challenge=params.code_challenge, redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=self.resource, subject=SUBJECT).model_dump(mode='json')
        self._save()
        self.audit('oauth.login', {'client_id': client_id})
        return RedirectResponse(construct_redirect_uri(str(params.redirect_uri), code=code, state=params.state), 302)

    # codes and tokens
    async def load_authorization_code(self, client, authorization_code):
        c = self.s['codes'].get(_h(authorization_code))
        if c and c['client_id'] == client.client_id:
            return AuthorizationCode.model_validate(c)

    def _issue(self, client_id, scopes):
        now = int(time.time())
        access, refresh = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        common = dict(client_id=client_id, scopes=scopes, resource=self.resource, subject=SUBJECT)
        self.s['access'][_h(access)] = {**common, 'expires_at': now + ACCESS_TTL, 'refresh': _h(refresh)}
        self.s['refresh'][_h(refresh)] = {**common, 'expires_at': now + REFRESH_TTL}
        self._save()
        return OAuthToken(access_token=access, token_type='Bearer', expires_in=ACCESS_TTL,
                          refresh_token=refresh, scope=' '.join(scopes))

    async def exchange_authorization_code(self, client, authorization_code):
        if not self.s['codes'].pop(authorization_code.code, None):   # .code holds the hash
            raise TokenError('invalid_grant', 'authorization code already used')
        self.audit('oauth.token', {'client_id': client.client_id, 'grant': 'authorization_code'})
        return self._issue(client.client_id, authorization_code.scopes)

    async def load_refresh_token(self, client, refresh_token):
        r = self.s['refresh'].get(_h(refresh_token))
        if r and r['client_id'] == client.client_id:
            return RefreshToken(token=_h(refresh_token), **{k: v for k, v in r.items() if k != 'token'})

    async def exchange_refresh_token(self, client, refresh_token, scopes):
        if not self.s['refresh'].pop(refresh_token.token, None):      # rotate: old refresh token dies
            raise TokenError('invalid_grant', 'refresh token already used')
        self.s['access'] = {h: a for h, a in self.s['access'].items() if a.get('refresh') != refresh_token.token}
        self.audit('oauth.token', {'client_id': client.client_id, 'grant': 'refresh_token'})
        return self._issue(client.client_id, scopes or refresh_token.scopes)

    async def load_access_token(self, token):
        a = self.s['access'].get(_h(token))
        if a and a['expires_at'] > time.time():
            return AccessToken(token=_h(token), **{k: v for k, v in a.items() if k != 'refresh'})

    async def revoke_token(self, token):
        h = token.token
        refresh = self.s['access'].get(h, {}).get('refresh') or h
        self.s['refresh'].pop(refresh, None)
        self.s['access'] = {k: a for k, a in self.s['access'].items() if k != h and a.get('refresh') != refresh}
        self._save()
        self.audit('oauth.revoke', {'client_id': token.client_id})

    async def exchange_identity_assertion(self, client, params):
        raise TokenError('unsupported_grant_type', 'not supported')


def _page(message, req=None, client=None):
    form = '' if not req else f'''
<p>{escape(client or "A client")} wants to log readings and events to WaterScribe.</p>
<form method="post" action="login">
  <input type="hidden" name="req" value="{escape(req)}">
  <input type="password" name="passphrase" placeholder="Passphrase" autofocus required>
  <button type="submit">Allow</button>
</form>'''
    msg = f'<p class="msg">{escape(message)}</p>' if message else ''
    return f'''<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>WaterScribe sign-in</title>
<style>body{{font-family:system-ui,sans-serif;background:#0f172a;color:#e2e8f0;display:flex;justify-content:center;
padding:4rem 1rem}}main{{max-width:22rem;width:100%}}input,button{{font:inherit;padding:.6rem;width:100%;
box-sizing:border-box;margin-top:.6rem;border-radius:6px;border:1px solid #334155}}input{{background:#1e293b;
color:inherit}}button{{background:#0ea5e9;color:#fff;border:0;cursor:pointer}}.msg{{color:#fca5a5}}</style>
</head><body><main><h1>WaterScribe</h1>{msg}{form}</main></body></html>'''
