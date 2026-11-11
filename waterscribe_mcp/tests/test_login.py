"""Brute-force protection on /login. Run: cd waterscribe_mcp && venv/bin/python -m unittest discover -s tests -v"""
import asyncio
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pydantic import AnyUrl
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

import limits
import oauth
from mcp.server.auth.provider import AuthorizationParams
from mcp.shared.auth import OAuthClientInformationFull

PASS = 'correct horse battery'


class Clock:
    def __init__(self):
        self.t = 1_800_000_000.0
    def __call__(self):
        return self.t


class LoginTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.state = Path(self.dir.name)
        (self.state / 'passphrase').write_text(oauth.hash_passphrase(PASS) + '\n')
        self.events, self.clock = [], Clock()
        self.make_provider()

    def tearDown(self):
        self.dir.cleanup()

    def make_provider(self):
        self.p = oauth.Provider(self.state, 'http://test/mcp', lambda k, d: self.events.append((k, d)), clock=self.clock)
        self.p.fail_seconds = 0
        app = Starlette(routes=[Route('/login', self.p.login, methods=['GET', 'POST'])])
        # connections arrive from tailscaled on loopback, like the real funnel
        self.http = TestClient(app, base_url='http://test', follow_redirects=False, client=('127.0.0.1', 40000))
        self.app = app
        self.client = OAuthClientInformationFull(client_id='c1', client_secret='s', client_name='Claude',
                                                 redirect_uris=[AnyUrl('https://claude.ai/api/mcp/auth_callback')])
        asyncio.run(self.p.register_client(self.client))

    def new_req(self):
        params = AuthorizationParams(state='st', scopes=['waterscribe'], code_challenge='x' * 43,
                                     redirect_uri=AnyUrl('https://claude.ai/api/mcp/auth_callback'),
                                     redirect_uri_provided_explicitly=True)
        url = asyncio.run(self.p.authorize(self.client, params))
        return url.split('req=')[1]

    def attempt(self, passphrase, ip='203.0.113.5', req=None):
        req = self.new_req() if req is None else req
        return self.http.post('/login', data={'req': req, 'passphrase': passphrase},
                              headers={'X-Forwarded-For': ip})

    def assertFailed(self, r):
        self.assertEqual(r.status_code, 401)
        self.assertIn(oauth.FAILED, r.text)
        self.assertNotIn('<form', r.text)

    def test_correct_passphrase_redirects_with_code(self):
        r = self.attempt(PASS)
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers['location'].startswith('https://claude.ai/api/mcp/auth_callback?code='))
        self.assertIn('state=st', r.headers['location'])

    def test_ip_locks_after_5_failures_even_for_correct_passphrase(self):
        for _ in range(5):
            self.assertFailed(self.attempt('wrong'))
        self.assertFailed(self.attempt(PASS))                     # locked: right passphrase refused
        self.assertEqual(self.events[-1][1]['reason'], 'locked_ip')
        self.assertEqual(self.attempt(PASS, ip='198.51.100.9').status_code, 302)   # other IPs fine

    def test_lockout_expires_and_backs_off(self):
        for _ in range(5):
            self.attempt('wrong')
        self.clock.t += 15 * 60 - 1
        self.assertFailed(self.attempt(PASS))
        self.clock.t += 2                                         # first lockout: 15 min
        for _ in range(5):
            self.attempt('wrong')
        lock = [d for k, d in self.events if k == 'oauth.lockout'][-1]
        self.assertEqual((lock['seconds'], lock['level']), (1800, 2))   # second: 30 min
        self.clock.t += 1801
        self.assertEqual(self.attempt(PASS).status_code, 302)

    def test_backoff_caps_at_24h_and_resets_after_quiet_day(self):
        for _ in range(10):
            for _ in range(5):
                self.attempt('wrong')
            self.clock.t += limits.MAX_LOCK + 1 - 1   # just inside LEVEL_RESET, past any lock
        secs = [d['seconds'] for k, d in self.events if k == 'oauth.lockout' and d['scope'] == 'ip']
        self.assertEqual(max(secs), limits.MAX_LOCK)
        self.clock.t += limits.LEVEL_RESET + 10
        for _ in range(5):
            self.attempt('wrong')
        last = [d for k, d in self.events if k == 'oauth.lockout' and d['scope'] == 'ip'][-1]
        self.assertEqual((last['seconds'], last['level']), (900, 1))

    def test_global_limit_across_ips(self):
        for i in range(20):
            self.assertFailed(self.attempt('wrong', ip=f'192.0.2.{i}'))
        self.assertTrue(any(k == 'oauth.lockout' and d['scope'] == 'global' for k, d in self.events))
        self.assertFailed(self.attempt(PASS, ip='198.51.100.77'))   # fresh IP, still refused
        self.assertEqual(self.events[-1][1]['reason'], 'locked_global')

    def test_every_failure_is_identical(self):
        r1 = self.attempt('wrong')
        r2 = self.attempt(PASS, req='no-such-request')
        r3 = self.http.get('/login?req=no-such-request')
        for _ in range(5):
            self.attempt('wrong', ip='203.0.113.99')
        r4 = self.attempt(PASS, ip='203.0.113.99')
        req = self.new_req()
        (self.state / 'passphrase').unlink()                      # passphrase removed mid-flow
        r5 = self.attempt(PASS, ip='203.0.113.200', req=req)
        bodies = {(r.status_code, r.text) for r in (r1, r2, r3, r4, r5)}
        self.assertEqual(len(bodies), 1, bodies)

    def test_request_is_single_use(self):
        req = self.new_req()
        self.assertFailed(self.attempt('wrong', req=req))
        self.assertFailed(self.attempt(PASS, req=req))           # same req again: gone
        self.assertEqual(self.events[-1][1]['reason'], 'bad_request')

    def test_failures_are_audited_without_passphrase(self):
        self.attempt('hunter2-guess')
        kind, d = self.events[-1]
        self.assertEqual((kind, d['reason'], d['ip'], d['ip_fails']), ('oauth.login_failed', 'wrong_passphrase', '203.0.113.5', 1))
        self.assertNotIn('hunter2', repr(self.events))

    def test_lockout_survives_restart(self):
        for _ in range(5):
            self.attempt('wrong')
        self.make_provider()                                      # new process, same state dir
        self.assertFailed(self.attempt(PASS))
        self.assertEqual(self.events[-1][1]['reason'], 'locked_ip')

    def test_success_clears_ip_failures(self):
        for _ in range(4):
            self.attempt('wrong')
        self.assertEqual(self.attempt(PASS).status_code, 302)
        for _ in range(4):
            self.attempt('wrong')
        self.assertEqual(self.attempt(PASS).status_code, 302)    # 4+4 never reached 5

    def test_spoofed_forwarded_for_is_ignored(self):
        for i in range(5):                                        # attacker rotates a fake left-hand entry
            self.attempt('wrong', ip=f'10.0.0.{i}, 203.0.113.5')
        self.assertFailed(self.attempt(PASS, ip='10.9.9.9, 203.0.113.5'))
        self.assertEqual(self.events[-1][1]['ip'], '203.0.113.5')

    def test_forwarded_for_ignored_from_non_loopback_peer(self):
        direct = TestClient(self.app, base_url='http://test', follow_redirects=False, client=('192.168.221.50', 1234))
        direct.post('/login', data={'req': self.new_req(), 'passphrase': 'wrong'}, headers={'X-Forwarded-For': '1.2.3.4'})
        self.assertEqual(self.events[-1][1]['ip'], '192.168.221.50')

    def test_failure_delay_applies_to_every_failure(self):
        self.p.fail_seconds = 0.3
        for args in (('wrong',), (PASS, '203.0.113.5', 'bogus')):
            t = time.monotonic()
            self.attempt(*args)
            self.assertGreaterEqual(time.monotonic() - t, 0.3)


if __name__ == '__main__':
    unittest.main()
