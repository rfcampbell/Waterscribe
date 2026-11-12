"""Import first in every MCP test. The server has no DB of its own: the live things a test could
touch are the state dir (audit log, passphrase, tokens) and the WaterScribe API, which writes prod.
So force a ws_mcp_test_* temp state dir and an API port nothing listens on, and refuse if the
imported server ended up anywhere else (e.g. imported earlier with the live environment)."""
import os
import sys
import tempfile
from pathlib import Path

LIVE_STATE = Path.home() / '.local/state/waterscribe-mcp'
DEAD_API = 'http://127.0.0.1:1'   # nothing listens: a stray real API call fails instead of writing

STATE = tempfile.mkdtemp(prefix='ws_mcp_test_')
os.environ['WATERSCRIBE_MCP_STATE'] = STATE
os.environ['WATERSCRIBE_API'] = DEAD_API
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def check(server):
    state, api = Path(server.STATE).resolve(), server.API
    if state == LIVE_STATE.resolve() or not state.name.startswith('ws_mcp_test_') or api != DEAD_API:
        raise RuntimeError(f'refusing to run: server uses state {state} and API {api}, '
                           f'not a ws_mcp_test_* dir and {DEAD_API}')
    return server


def import_server():
    import server
    return check(server)
