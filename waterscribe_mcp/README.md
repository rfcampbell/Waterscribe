# WaterScribe MCP server

Lets Claude (the claude.ai custom connector) log readings and events to WaterScribe and read
recent history. **Insert-only**: there are no edit or delete tools. Fix mistakes in the WaterScribe UI.

| Tool | What it does |
|---|---|
| `list_tanks()` | Codes, names, types, volumes. A tank without a code is left out and named under `without_code` |
| `list_parameters()` | Parameters with stored units, event types, qualities |
| `log_readings(tank, readings[])` | One or more readings, all saved or none. Each reading: `parameter`, `value`, optional `value_min`/`value_max`, `unit`, `method`, `quality`, `notes`, `timestamp` |
| `log_event(tank, event, value?, unit?, notes?, timestamp?)` | Water change, CO2 bubble rate, dosing, maintenance... |
| `get_recent(tank, parameter?, days=14)` | Readings newest first. With no parameter, events are included too |

- Tanks are matched by code (`100P`), name or id. A tank with no code is refused, with a message to set one, and nothing is written. Parameters and events are matched by key, label or common
  alias (`NO3`, `conductivity`, `wc`, `co2`). Unknown names are rejected, and the error lists the valid ones.
- Units and plausible ranges: the stored units are pH, ppm (ammonia, nitrite), ppm NO3, dKH, dGH,
  µS/cm, °F, ppm PO4/K/Fe. KH/GH given in ppm, mg/L or ppm CaCO3 are converted. A bare ppm for
  nitrate or phosphate means as NO3/PO4. Other units and out-of-range values are rejected with an
  error naming the parameter, value and allowed range. The server's instructions tell Claude to ask
  you, not to adjust the value. The full rules are in the main README (*Units and plausible
  ranges*). They live in the WaterScribe API, so the web form, the CSV import and MCP all agree.
- Timestamps are ISO 8601 in tank-local time (America/Los_Angeles), unless an offset is given.
  A date with no time is stored as "time unknown". Omit the timestamp for now. Future times are rejected.
- Results report what the database stored, after conversion, not what was sent.

## How it is wired

```
claude.ai ──https──▶ Tailscale Funnel (robix.tailaf4333.ts.net:443)
                       └─▶ 127.0.0.1:8765  waterscribe-mcp.service  (this; OAuth + tools)
                             └─▶ 127.0.0.1:5000  waterscribe.service  (Flask API)
```

Only the MCP server is funnelled. The WaterScribe UI and nginx stay LAN-only.

**Auth** is OAuth 2.1, done inside this server: dynamic client registration, PKCE, a passphrase
page at `/login`, and 24 h access tokens with 90-day rotating refresh tokens. Registration accepts
only claude.ai's callback (`https://claude.ai/api/mcp/auth_callback` or the claude.com one) and
loopback addresses, which are used for local testing. Codes and tokens are stored as SHA-256 hashes
in `~/.local/state/waterscribe-mcp/oauth.json` (mode 600). The passphrase is stored as an scrypt hash.
Disconnecting the connector in claude.ai revokes its tokens. To cut off every client at once,
stop the service and delete `oauth.json`.

**Passphrase guessing** (`limits.py`): 5 failures from one IP within 15 min lock that IP, and 20
failures from all IPs within 15 min lock everyone. A lockout lasts 15 min, then 30, 60 and so on,
up to 24 h. The level resets after a day without a lockout. While a lockout is in force, the
passphrase is not even checked, so a correct guess fails too. Every failure gets the same page,
with a 401 and at least 1 s of delay, whether it was a wrong passphrase, a lockout or an expired
link. Each failure also uses up that sign-in, so a retry starts again from claude.ai. The real
reason is written only to the audit log (`oauth.login_failed`, `oauth.lockout`). Lockouts survive
restarts in `login_limits.json`.

The client IP comes from `X-Forwarded-For`, and only for connections from loopback, which means
tailscaled. This was verified with tcpdump on the live funnel on 2026-11-11. tailscaled *replaces*
whatever `X-Forwarded-For` the client sent with the real client address, so a forged value is
dropped. It also adds `Tailscale-Funnel-Request: ?1`. It passes **`X-Real-Ip` through from the
client unchanged**, so that header is forgeable and must never be trusted. Nothing here reads it.

Lockouts gate only the passphrase page. Existing bearer tokens and refresh-token grants are never
checked against them, so a lockout can't cut off a connected claude.ai (`tests/test_scope.py`).

```bash
venv/bin/python clear-lockouts             # show lockouts and recent failures
venv/bin/python clear-lockouts --ip 1.2.3.4
venv/bin/python clear-lockouts --all       # global included
```
This takes effect immediately, with no restart, and is written to the audit log
(`oauth.lockouts_cleared`).

Tests: `venv/bin/python -m unittest discover -s tests -v`. Every test imports `tests/testenv.py`
first, which forces a `ws_mcp_test_*` temp state dir and a WaterScribe API address nothing listens
on, and refuses to run if the server loaded the live state dir or the real API anyway.

**Health**: `GET /healthz` is public and unauthenticated, so it says only `{"ok": true}` or
`{"ok": false}` (503). It means this server and the WaterScribe API both answered, checked live
and never cached. Per-component status is on robix nginx, for LAN and tailnet addresses only (403
otherwise): `/status/waterscribe-mcp/server` and `/status/waterscribe-mcp/api`. The services page
tile checks those two, plus the public `/healthz` through the funnel, and shows which one failed.

**Sandboxing**: the unit runs with `ProtectSystem=strict` and `ProtectHome=read-only`. The only
writable path is `~/.local/state/waterscribe-mcp`.

**Audit log**: `~/.local/state/waterscribe-mcp/audit.jsonl` gets one JSON line per tool call
(client, inputs, result or error, duration), plus OAuth events such as registrations, logins,
failed logins, token issues and revocations.

```bash
tail -f ~/.local/state/waterscribe-mcp/audit.jsonl | jq .
```

## Setup (robix)

```bash
cd waterscribe_mcp
python3 -m venv venv && venv/bin/pip install -r requirements.txt
venv/bin/python set-passphrase          # run in a real terminal; prompts twice, stores only a hash
sudo install -m 644 ../deploy/waterscribe-mcp.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now waterscribe-mcp
sudo tailscale funnel --bg 8765         # https://robix.tailaf4333.ts.net -> 127.0.0.1:8765, persists
```

`tailscale funnel --bg` is saved in tailscaled's own state. It is verified to survive a
`systemctl restart tailscaled`.
Check it with `tailscale funnel status`. Remove it with `sudo tailscale funnel --https=443 off`.

Tailscale admin console prerequisites: MagicDNS on, HTTPS certificates on (DNS page), and the
`funnel` node attribute in the tailnet policy:

```json
"nodeAttrs": [{ "target": ["autogroup:member"], "attr": ["funnel"] }]
```

Env overrides (see the unit): `WATERSCRIBE_MCP_PUBLIC_URL`, `WATERSCRIBE_MCP_PORT`,
`WATERSCRIBE_MCP_STATE`, `WATERSCRIBE_API`.

## Adding the connector in claude.ai

Customize → Connectors → **Add custom connector**. Name: `WaterScribe`. URL:
`https://robix.tailaf4333.ts.net/mcp`. Leave the advanced OAuth fields empty, since claude.ai registers
itself. Then **Connect**. A WaterScribe page asks for the passphrase. Enter it, and you are sent back
to claude.ai. Turn the connector on for a chat from the tools menu.

## Swapping to a Cloudflare Tunnel later (if you buy a domain)

1. Add the domain to Cloudflare, install `cloudflared` on robix, and run `cloudflared tunnel login`.
2. Run `cloudflared tunnel create waterscribe-mcp`. Then
   `cloudflared tunnel route dns waterscribe-mcp mcp.<domain>`.
3. In `/etc/cloudflared/config.yml`, set the tunnel and its credentials file, with
   `ingress: [{hostname: mcp.<domain>, service: http://127.0.0.1:8765}, {service: http_status:404}]`.
   Then run `sudo cloudflared service install`.
4. Set `WATERSCRIBE_MCP_PUBLIC_URL=https://mcp.<domain>` in the unit and restart. The OAuth issuer and
   the allowed Host both follow this variable.
5. Delete `oauth.json`. The old tokens are bound to the old URL.
6. Remove the connector in claude.ai and add it again with the new URL.
7. Turn the funnel off: `sudo tailscale funnel --https=443 off`.

Nothing else changes. The server only listens on 127.0.0.1 either way.
