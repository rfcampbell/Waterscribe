"""Lockouts gate only the passphrase page: with /login locked for everyone, an existing bearer
token still reaches /mcp and a refresh-token grant still works. Uses the real server app."""
import base64
import hashlib
import os
import secrets
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parents[1]
STATE = tempfile.mkdtemp()
os.environ.update(WATERSCRIBE_MCP_STATE=STATE, WATERSCRIBE_MCP_PUBLIC_URL='http://127.0.0.1:8765',
                  WATERSCRIBE_MCP_PORT='8765', WATERSCRIBE_API='http://127.0.0.1:1')
sys.path.insert(0, str(HERE))
import oauth
(Path(STATE) / 'passphrase').write_text(oauth.hash_passphrase('right passphrase') + '\n')
import server
from starlette.testclient import TestClient

REDIRECT = 'http://127.0.0.1:9/cb'
MCP_HEADERS = {'Accept': 'application/json, text/event-stream', 'Content-Type': 'application/json'}
INIT = {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
        'params': {'protocolVersion': '2025-06-18', 'capabilities': {}, 'clientInfo': {'name': 't', 'version': '0'}}}


class Scope(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.provider.fail_seconds = 0
        app = server.mcp.streamable_http_app(streamable_http_path='/mcp', transport_security=server.transport_security())
        cls.cm = TestClient(app, base_url='http://127.0.0.1:8765', follow_redirects=False, client=('127.0.0.1', 5))
        cls.c = cls.cm.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.cm.__exit__(None, None, None)

    def setUp(self):
        server.provider.limiter.clear()

    def sign_in(self, passphrase='right passphrase', ip='203.0.113.1'):
        cl = self.c.post('/register', json={'client_name': 't', 'redirect_uris': [REDIRECT],
                                            'grant_types': ['authorization_code', 'refresh_token']}).json()
        ver = secrets.token_urlsafe(48)
        ch = base64.urlsafe_b64encode(hashlib.sha256(ver.encode()).digest()).decode().rstrip('=')
        loc = self.c.get('/authorize', params={'response_type': 'code', 'client_id': cl['client_id'], 'redirect_uri': REDIRECT,
                                              'code_challenge': ch, 'code_challenge_method': 'S256', 'state': 's'}).headers['location']
        req = parse_qs(urlparse(loc).query)['req'][0]
        r = self.c.post('/login', data={'req': req, 'passphrase': passphrase}, headers={'X-Forwarded-For': ip})
        if r.status_code != 302:
            return cl, None, r
        code = parse_qs(urlparse(r.headers['location']).query)['code'][0]
        tok = self.c.post('/token', data={'grant_type': 'authorization_code', 'code': code, 'redirect_uri': REDIRECT,
                                         'client_id': cl['client_id'], 'client_secret': cl['client_secret'],
                                         'code_verifier': ver}).json()
        return cl, tok, r

    def lock_everyone(self):
        for i in range(20):
            self.sign_in('wrong', ip=f'192.0.2.{i}')
        self.assertEqual(server.provider.limiter.locked('198.51.100.1'), 'global')

    def test_tokens_and_refresh_unaffected_by_global_lockout(self):
        cl, tok, _ = self.sign_in()
        self.lock_everyone()
        _, none, r = self.sign_in()                                # login itself refused
        self.assertIsNone(none)
        self.assertEqual(r.status_code, 401)
        r = self.c.post('/mcp', json=INIT, headers={**MCP_HEADERS, 'Authorization': 'Bearer ' + tok['access_token']})
        self.assertEqual(r.status_code, 200, r.text)
        r = self.c.post('/token', data={'grant_type': 'refresh_token', 'refresh_token': tok['refresh_token'],
                                       'client_id': cl['client_id'], 'client_secret': cl['client_secret']})
        self.assertEqual(r.status_code, 200, r.text)
        r = self.c.post('/mcp', json=INIT, headers={**MCP_HEADERS, 'Authorization': 'Bearer ' + r.json()['access_token']})
        self.assertEqual(r.status_code, 200, r.text)

    def test_no_token_still_401_during_lockout(self):
        self.lock_everyone()
        self.assertEqual(self.c.post('/mcp', json=INIT, headers=MCP_HEADERS).status_code, 401)

    def test_clear_lockouts_cli_takes_effect_without_restart(self):
        self.lock_everyone()
        out = subprocess.run([sys.executable, str(HERE / 'clear-lockouts'), '--state', STATE],
                             capture_output=True, text=True).stdout
        self.assertIn('global', out)
        self.assertIn('LOCKED', out)
        out = subprocess.run([sys.executable, str(HERE / 'clear-lockouts'), '--all', '--state', STATE],
                             capture_output=True, text=True).stdout
        self.assertIn('cleared all', out)
        _, tok, _ = self.sign_in()                                 # running server sees it at once
        self.assertIsNotNone(tok)
        self.assertIn('oauth.lockouts_cleared', (Path(STATE) / 'audit.jsonl').read_text())

    def test_clear_one_ip(self):
        for _ in range(5):
            self.sign_in('wrong', ip='203.0.113.50')
        self.assertEqual(server.provider.limiter.locked('203.0.113.50'), 'ip')
        subprocess.run([sys.executable, str(HERE / 'clear-lockouts'), '--ip', '203.0.113.50', '--state', STATE], check=True,
                       capture_output=True)
        self.assertIsNone(server.provider.limiter.locked('203.0.113.50'))


if __name__ == '__main__':
    unittest.main()
