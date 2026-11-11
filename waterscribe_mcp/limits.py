"""
Failed-login limiter for the public /login page: per client IP and across all IPs.

LIMIT failures within WINDOW seconds locks that key (an IP, or 'global') for BASE_LOCK seconds,
doubling with each further lockout up to MAX_LOCK. The backoff level resets once a key has gone
LEVEL_RESET seconds without a lockout. State is saved to disk so a restart does not clear it.
The file is re-read whenever it changes, so `clear-lockouts` takes effect without a restart.
Only the /login passphrase check uses this; bearer tokens and token grants never consult it.
"""
import json
import os
import time
from pathlib import Path

PER_IP = (5, 900)          # (failures, window seconds)
GLOBAL = (20, 900)
BASE_LOCK = 900            # first lockout 15 min, then 30, 60, ... up to MAX_LOCK
MAX_LOCK = 24 * 3600
LEVEL_RESET = 24 * 3600


class LoginLimiter:
    def __init__(self, path, clock=time.time, per_ip=PER_IP, global_=GLOBAL):
        self.path, self.clock = Path(path), clock
        self.limits = {'ip': per_ip, 'global': global_}
        self._stamp = None
        self._sync()

    def _file_stamp(self):
        try:
            st = self.path.stat()
            return (st.st_mtime_ns, st.st_size, st.st_ino)
        except OSError:
            return None

    def _sync(self):
        """Reload if the file changed under us (clear-lockouts, or deleted by hand)."""
        stamp = self._file_stamp()
        if stamp is not None and stamp == self._stamp:
            return
        try:
            self.s = json.loads(self.path.read_text())
        except (OSError, ValueError):
            self.s = {}
        self.s.setdefault('ip', {})
        self.s.setdefault('global', {})
        self._stamp = stamp

    def _entry(self, kind, key):
        bucket = self.s[kind] if kind == 'ip' else self.s
        return bucket.setdefault(key, {'fails': [], 'locked_until': 0, 'level': 0, 'last_lock': 0})

    def locked(self, ip):
        """'ip' or 'global' if a lockout is in force for this request, else None."""
        self._sync()
        now = self.clock()
        if self.s['global'].get('locked_until', 0) > now:
            return 'global'
        if self.s['ip'].get(ip, {}).get('locked_until', 0) > now:
            return 'ip'
        return None

    def fail(self, ip):
        """Record a failure. Returns a list of lockouts it triggered: [(scope, seconds, level)]."""
        self._sync()
        now, started = self.clock(), []
        for kind, e in (('ip', self._entry('ip', ip)), ('global', self.s['global'])):
            e.setdefault('fails', []); e.setdefault('level', 0); e.setdefault('last_lock', 0)
            limit, window = self.limits[kind]
            e['fails'] = [t for t in e['fails'] if t > now - window] + [now]
            if len(e['fails']) >= limit and e.get('locked_until', 0) <= now:
                if now - e['last_lock'] > LEVEL_RESET:
                    e['level'] = 0
                e['level'] += 1
                secs = min(BASE_LOCK * 2 ** (e['level'] - 1), MAX_LOCK)
                e.update(locked_until=now + secs, last_lock=now, fails=[])
                started.append((kind, secs, e['level']))
        self._save()
        return started

    def counts(self, ip):
        self._sync()
        return {'ip_fails': len(self.s['ip'].get(ip, {}).get('fails', [])),
                'global_fails': len(self.s['global'].get('fails', []))}

    def success(self, ip):
        """A correct passphrase clears that IP's failures and backoff (not the global ones)."""
        self._sync()
        if self.s['ip'].pop(ip, None) is not None:
            self._save()

    def _save(self):
        now = self.clock()
        # forget IPs with nothing pending and no backoff that still matters
        self.s['ip'] = {ip: e for ip, e in self.s['ip'].items()
                        if e['fails'] or e['locked_until'] > now or now - e['last_lock'] < LEVEL_RESET}
        tmp = self.path.with_suffix('.tmp')
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump(self.s, f)
        os.replace(tmp, self.path)
        self._stamp = self._file_stamp()

    def status(self):
        """Active lockouts and recent failures, for the clear-lockouts CLI."""
        self._sync()
        now = self.clock()
        rows = [('global', self.s['global'])] + sorted(self.s['ip'].items())
        return [{'scope': k, 'locked_for_s': max(0, int(e.get('locked_until', 0) - now)),
                 'level': e.get('level', 0), 'recent_fails': len(e.get('fails', []))}
                for k, e in rows if e]

    def clear(self, ip=None):
        """Drop lockouts, failures and backoff: for one IP, or everything (including global)."""
        self._sync()
        if ip:
            found = self.s['ip'].pop(ip, None) is not None
        else:
            found = bool(self.s['ip'] or self.s['global'])
            self.s = {'ip': {}, 'global': {}}
        self._save()
        return found


def client_ip(request):
    """The connection comes from tailscaled on 127.0.0.1, which appends the real client to
    X-Forwarded-For. Take the rightmost entry: anything left of it was sent by the client."""
    peer = request.client.host if request.client else ''
    if peer in ('127.0.0.1', '::1'):
        xff = request.headers.get('x-forwarded-for', '')
        if xff.strip():
            return xff.split(',')[-1].strip()
    return peer or 'unknown'
