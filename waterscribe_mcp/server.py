"""
WaterScribe MCP server: insert-only access to readings and events for the claude.ai connector.

Talks to the WaterScribe API on 127.0.0.1:5000 (which owns validation and unit conversion);
every tool call is appended to audit.jsonl. Env:
  WATERSCRIBE_MCP_PUBLIC_URL  public base URL   (default https://robix.tailaf4333.ts.net)
  WATERSCRIBE_MCP_PORT        listen port        (default 8765, always 127.0.0.1)
  WATERSCRIBE_MCP_STATE       state/log dir      (default ~/.local/state/waterscribe-mcp)
  WATERSCRIBE_API             WaterScribe base   (default http://127.0.0.1:5000)
"""
import functools
import json
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel, Field

from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

import oauth

PUBLIC = os.environ.get('WATERSCRIBE_MCP_PUBLIC_URL', 'https://robix.tailaf4333.ts.net').rstrip('/')
PORT = int(os.environ.get('WATERSCRIBE_MCP_PORT', '8765'))
STATE = Path(os.environ.get('WATERSCRIBE_MCP_STATE', Path.home() / '.local/state/waterscribe-mcp'))
API = os.environ.get('WATERSCRIBE_API', 'http://127.0.0.1:5000').rstrip('/')
TZ = ZoneInfo('America/Los_Angeles')    # WaterScribe stores local wall-clock time
RESOURCE = PUBLIC + '/mcp'

os.umask(0o077)    # audit log and token store are private
STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
AUDIT = STATE / 'audit.jsonl'


def audit(kind, data):
    line = {'ts': datetime.now(TZ).isoformat(timespec='seconds'), 'kind': kind, **data}
    with open(AUDIT, 'a') as f:
        f.write(json.dumps(line, default=str) + '\n')


def audited(fn):
    """Log the tool's inputs and its result (or error) to audit.jsonl."""
    @functools.wraps(fn)
    async def wrapper(**kwargs):
        tok = get_access_token()
        entry = {'tool': fn.__name__, 'client_id': tok.client_id if tok else None,
                 'input': {k: (v.model_dump(exclude_none=True) if isinstance(v, BaseModel) else
                               [x.model_dump(exclude_none=True) if isinstance(x, BaseModel) else x for x in v]
                               if isinstance(v, list) else v) for k, v in kwargs.items()}}
        start = time.monotonic()
        try:
            result = await fn(**kwargs)
        except Exception as e:
            audit('tool', {**entry, 'ok': False, 'error': str(e), 'ms': int((time.monotonic() - start) * 1000)})
            raise
        audit('tool', {**entry, 'ok': True, 'result': result, 'ms': int((time.monotonic() - start) * 1000)})
        return result
    return wrapper


# WaterScribe API
async def api(method, path, **kw):
    async with httpx.AsyncClient(base_url=API, timeout=15) as c:
        try:
            r = await c.request(method, '/api' + path, **kw)
        except httpx.HTTPError as e:
            raise ToolError(f'WaterScribe is not reachable ({e.__class__.__name__}); nothing was saved')
    try:
        body = r.json()
    except ValueError:
        raise ToolError(f'WaterScribe returned HTTP {r.status_code} without JSON; nothing was saved')
    if r.status_code >= 400 or (isinstance(body, dict) and body.get('success') is False):
        raise ToolError(f"WaterScribe rejected it: {body.get('error') if isinstance(body, dict) else r.status_code}")
    return body


_catalog = {'at': 0, 'data': None}

async def catalog():
    if time.monotonic() - _catalog['at'] > 300:
        _catalog['data'], _catalog['at'] = await api('GET', '/catalog'), time.monotonic()
    return _catalog['data']


def _norm(s):
    return re.sub(r'[^a-z0-9]', '', (s or '').lower())


async def resolve_tank(tank):
    tanks = await api('GET', '/aquariums')
    want = _norm(str(tank))
    for t in tanks:
        if want in (_norm(t['code']), _norm(t['name']), str(t['id'])):
            return t
    raise ToolError(f'unknown tank {tank!r}. Known tanks: ' +
                    '; '.join(f"{t['code']} ({t['name']})" for t in tanks) + '. Use the code.')


PARAM_ALIASES = {'nh3': 'ammonia', 'nh4': 'ammonia', 'tan': 'ammonia', 'no2': 'nitrite', 'no3': 'nitrate',
                 'conductivity': 'ec', 'carbonatehardness': 'kh', 'generalhardness': 'gh', 'temp': 'temperature',
                 'po4': 'phosphate', 'k': 'potassium', 'fe': 'iron', 'phdegassed': 'ph_degassed'}
EVENT_ALIASES = {'wc': 'water_change', 'waterchange': 'water_change', 'co2': 'co2_bubble_rate',
                 'bubblerate': 'co2_bubble_rate', 'bubblecount': 'co2_bubble_rate', 'fertilizer': 'fertilizer_dose'}


def _lookup(name, items, aliases, what):
    want = _norm(name)
    want = aliases.get(want, want)
    for it in items:
        if want in (_norm(it['key']), _norm(it['label']), it['key']):
            return it
    raise ToolError(f'unknown {what} {name!r}. Known: ' + ', '.join(f"{i['key']} ({i['label']})" for i in items))


def parse_ts(ts):
    """ISO 8601 -> (date, time) in local tank time. Date only -> time unknown. None -> now."""
    if not ts:
        return {}
    s = ts.strip().replace(' ', 'T', 1)
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', s):
        d = datetime.fromisoformat(s)
        if d.date() > datetime.now(TZ).date():
            raise ToolError(f'timestamp {ts!r} is in the future')
        return {'date': s}
    try:
        dt = datetime.fromisoformat(s.replace('Z', '+00:00'))
    except ValueError:
        raise ToolError(f'bad timestamp {ts!r}: use ISO 8601 like 2026-11-11T19:30 (local) or 2026-11-11')
    dt = dt.astimezone(TZ).replace(tzinfo=None) if dt.tzinfo else dt
    if dt > datetime.now(TZ).replace(tzinfo=None) + timedelta(minutes=5):
        raise ToolError(f'timestamp {ts!r} is in the future')
    return {'date': dt.date().isoformat(), 'time': dt.strftime('%H:%M')}


# Tools
class ReadingIn(BaseModel):
    parameter: str = Field(description='Parameter key or name, e.g. "nitrate", "pH", "EC". See list_parameters.')
    value: float = Field(description='The reading. For a range like "10-20", give the midpoint and set value_min/value_max.')
    value_min: float | None = Field(None, description='Low end when the test gives a range (color charts).')
    value_max: float | None = Field(None, description='High end when the test gives a range.')
    unit: str | None = Field(None, description='Unit as measured. Omit to mean the catalog unit. KH/GH in ppm '
                                               'are converted to degrees; any other mismatch is rejected.')
    method: str | None = Field(None, description='Test kit or meter, e.g. "API", "Salifert", "Hanna".')
    quality: str | None = Field(None, description='ok (default), suspect, or bad. Bad readings are hidden on charts.')
    notes: str | None = None
    timestamp: str | None = Field(None, description='When it was measured, ISO 8601 in the tank\'s local time '
                                                    '(America/Los_Angeles) unless an offset is given. '
                                                    'Date only = time unknown. Omit for now.')


INSERT = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
READ = ToolAnnotations(readOnlyHint=True, openWorldHint=False)

mcp = MCPServer(
    name='WaterScribe',
    instructions='Logs aquarium water-test readings and maintenance events to WaterScribe. Insert-only: '
                 'nothing can be edited or deleted from here (mistakes get fixed in the WaterScribe UI). '
                 'Tanks are named by code (list_tanks). Times are the tank\'s local time.',
    auth_server_provider=(provider := oauth.Provider(STATE, RESOURCE, audit)),
    auth=AuthSettings(
        issuer_url=PUBLIC, resource_server_url=RESOURCE, validate_token_resource=True,
        client_registration_options=ClientRegistrationOptions(enabled=True, valid_scopes=[oauth.SCOPE],
                                                              default_scopes=[oauth.SCOPE]),
        revocation_options=RevocationOptions(enabled=True), required_scopes=[oauth.SCOPE]),
)


@mcp.tool(annotations=READ)
@audited
async def list_tanks() -> list[dict]:
    """List the aquariums: code (use this to name a tank), name, type and volume."""
    return [{k: t[k] for k in ('code', 'name', 'type', 'volume_gallons', 'description') if t.get(k) is not None}
            for t in await api('GET', '/aquariums')]


@mcp.tool(annotations=READ)
@audited
async def list_parameters() -> dict:
    """List the parameters readings can be logged for (with the unit stored) and the event types."""
    c = await catalog()
    return {'parameters': c['parameters'], 'event_types': c['event_types'], 'qualities': c['qualities']}


@mcp.tool(annotations=INSERT)
@audited
async def log_readings(tank: str, readings: list[ReadingIn]) -> dict:
    """Log one or more water-test readings for a tank. All are saved or none are.
    Each reading may have its own timestamp; omitted means now."""
    if not readings:
        raise ToolError('readings is empty')
    t, cat = await resolve_tank(tank), await catalog()
    rows = []
    for r in readings:
        p = _lookup(r.parameter, cat['parameters'], PARAM_ALIASES, 'parameter')
        rows.append({**r.model_dump(exclude={'timestamp', 'parameter'}), 'parameter': p['key'], **parse_ts(r.timestamp)})
    res = await api('POST', f"/aquarium/{t['id']}/readings", json={'readings': rows})
    stored = res.get('readings')
    if stored is None or len(stored) != len(rows):
        raise ToolError(f'WaterScribe did not confirm the readings (response: {res}); check the tank in the UI')
    # report what the database holds (converted units included), never the request
    return {'saved': len(stored), 'tank': t['code'], 'readings': [_shown(r, cat) for r in map(_when, stored)]}


@mcp.tool(annotations=INSERT)
@audited
async def log_event(tank: str, event: str, value: float | None = None, unit: str | None = None,
                    notes: str | None = None, timestamp: str | None = None) -> dict:
    """Log a maintenance event (water change %, CO2 bubble rate, dosing, filter clean, plant trim...).
    See list_parameters for event types and which take a value. timestamp: ISO 8601 local, omit for now."""
    t, cat = await resolve_tank(tank), await catalog()
    e = _lookup(event, cat['event_types'], EVENT_ALIASES, 'event type')
    res = await api('POST', f"/aquarium/{t['id']}/events",
                    json={'event_type': e['key'], 'value': value, 'unit': unit, 'notes': notes, **parse_ts(timestamp)})
    return {'saved': True, 'id': res.get('id'), 'tank': t['code'], 'event': e['key'], 'value': value,
            'unit': e['unit'] if value is not None else None}


READING_FIELDS = ('id', 'timestamp', 'parameter', 'value', 'value_min', 'value_max', 'method', 'quality', 'notes')


def _shown(r, cat):
    units = {p['key']: p['unit'] for p in cat['parameters']}
    return {**{k: r[k] for k in READING_FIELDS if r.get(k) not in (None, '')}, 'unit': units.get(r['parameter'])}


def _when(row):
    """Show unknown-time rows as a bare date instead of a made-up noon."""
    if row.get('time_known') is False and row.get('timestamp'):
        row['timestamp'] = row['timestamp'][:10] + ' (time unknown)'
    return row


@mcp.tool(annotations=READ)
@audited
async def get_recent(tank: str, parameter: str | None = None, days: int = 14) -> dict:
    """Recent readings for a tank, newest first, optionally one parameter. Without a parameter,
    the events in the same window are included too."""
    days = max(1, min(int(days), 3650))
    t, cat = await resolve_tank(tank), await catalog()
    params = {'days': days}
    if parameter:
        params['parameter'] = _lookup(parameter, cat['parameters'], PARAM_ALIASES, 'parameter')['key']
    readings = [_shown(r, cat) for r in map(_when, await api('GET', f"/aquarium/{t['id']}/readings", params=params))]
    out = {'tank': t['code'], 'days': days, 'readings': readings}
    if not parameter:
        ev_units = {e['key']: e['unit'] for e in cat['event_types']}
        out['events'] = [{**{k: e[k] for k in ('timestamp', 'event_type', 'value', 'notes') if e.get(k) not in (None, '')},
                          **({'unit': ev_units[e['event_type']]} if e.get('value') is not None else {})}
                         for e in map(_when, await api('GET', f"/aquarium/{t['id']}/events", params={'days': days}))]
    return out


@mcp.custom_route('/login', methods=['GET', 'POST'])
async def login(request):
    return await provider.login(request)


@mcp.custom_route('/healthz', methods=['GET'])
async def healthz(request):
    """Public and unauthenticated: says only whether this server and the WaterScribe API answer.
    CORS-open so the robix services page can show a real status dot."""
    from starlette.responses import JSONResponse
    try:
        await api('GET', '/catalog')     # uncached: a cached answer would stay green after the API died
        api_ok = True
    except ToolError:
        api_ok = False
    return JSONResponse({'ok': api_ok, 'waterscribe_api': api_ok}, status_code=200 if api_ok else 503,
                        headers={'Access-Control-Allow-Origin': '*', 'Cache-Control': 'no-store'})


if __name__ == '__main__':
    host = urlparse(PUBLIC).netloc
    mcp.run('streamable-http', host='127.0.0.1', port=PORT, streamable_http_path='/mcp',
            transport_security=TransportSecuritySettings(
                enable_dns_rebinding_protection=True,
                allowed_hosts=[host, f'127.0.0.1:{PORT}', f'localhost:{PORT}'],
                allowed_origins=[PUBLIC, 'https://claude.ai', 'https://claude.com']))
