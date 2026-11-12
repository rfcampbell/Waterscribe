# 🐠 WaterScribe

**Aquarium tracker for fishkeepers who care about their water.**

![WaterScribe](icon.png)

Track water parameters, schedule maintenance, manage fish inventory, and monitor your aquarium's health — all from a clean, mobile-friendly interface.

## Features

- **At a glance** — The Parameters page opens on tiles in a fixed order, by group (EC, nitrate, phosphate, potassium, iron | KH, GH, ammonia, nitrite, TDS, temperature | pH, CO2 pH drop, degassed pH, CO2 bubble rate; `TILE_GROUPS` in `app/catalog.py`). They sit in one continuous grid (`repeat(auto-fill, minmax(210px, 1fr))`, two columns on a phone) that fills the width and wraps; the group shows as a 3px top-edge accent (green nutrients, blue hardness+safety, lavender CO2; `TILE_GROUP_NAMES`), not as a row break. One tile per parameter the tank has data for: latest value (bad readings never count; a suspect latest gets ⚠), method, age, a 30-day sparkline and the tank's target band. A tile fades with an amber age once its reading is older than the parameter's staleness limit (`STALE_DAYS`: EC 2 d, nitrate 7 d, KH/GH 14 d...). Value and sparkline are seafoam in band, coral out of band. Logic in `app/overview.py`
- **CO2 pH drop** — For tanks with a daily CO2 window set (Manage Aquariums): the most recent ok (not suspect, not bad) degassed pH from the last 14 days minus the most recent ok in-tank pH taken inside the window in the last 2 days. The degassed sample must be taken after the tank's latest water change of 20% or more (`WC_RESETS_DEGASSED_PCT`; a change with no % counts too), since a big change moves KH. The tile shows both readings; when the rule can't be met it says why (no in-window pH, or new degassed sample needed after water change) in stale styling instead of showing a number, and chart history omits points that fail it. No window, no tile
- **Main chart** — Below the tiles; clicking a tile charts that parameter and scrolls to it. 7/30/90 d/all buttons, plus an overview strip whose window can be dragged and resized. Target band shaded, min–max ranges as error bars, water changes (with %) and other events as vertical markers, suspect points hollow, bad points hidden unless *show bad readings* is ticked. The y scale fits the ok readings in the window plus the target band, with 10% padding. Suspect readings, and bad ones when shown, never stretch it: any outside it are pinned to the top or bottom edge with a ▲/▼ marker (sand for suspect, grey for bad) and keep their real value in the tooltip. Only a window with no ok reading at all scales to what is shown. Hover (desktop) or touch-drag (phone) scrubs: the crosshair snaps to the nearest reading or event, with date, value or range, method, quality, note and the nearest preceding event. `app/static/js/mainchart.js`, data from `GET /api/aquarium/<id>/series?key=` (not used by the MCP server)
- **Water Parameters** — Each reading is its own record: value, optional min–max range (for colour-chart kits), method/kit, quality (`ok` / `suspect` / `bad`) and a note. Several readings taken together are entered at once: **+ Add new entry** (next to the tank name) opens a drawer — side sheet on desktop, full screen on a phone — prefilled with the current time and, per parameter, the method last used on *this* tank (method suggestions are shared across tanks). Closing it keeps anything typed, and the button shows how many readings are unsaved; saving reloads the page so tiles, chart and log update. A draft belongs to the tank it was typed on: it is never stored, the form carries its tank id and refuses to save to any other, and switching pills, Manage, the logo or a task reload asks before discarding it (back, close and typed URLs get the browser's leave-page prompt — except on iOS Safari, which has none, so a swipe-back there discards silently). The form has `autocomplete="off"` so the browser's back-button form restore can't bring a discarded draft back. Parameters: pH, ammonia, nitrite, nitrate, KH, GH, EC, degassed pH, temperature, TDS, phosphate, potassium, iron — add or reorder in `app/catalog.py`. Rows on the entry grid collapse; collapsed state is remembered per browser
- **Log** — Under the Parameters tab, like a lab notebook: one table per day (newest day first, rows in time order). Days start collapsed. Each day header is a toggle showing date · readings · events · the day's last value per parameter in tile order (e.g. `EC 317 · NO3 20`), plus ⚠ and the number of suspect or bad readings. Expand all / Collapse all sit above the log. Which days are open is remembered per tank for the browser session only. The log sits on an opaque dark card with blue-gray rows and a subtle greenbar. Parameter names are soft seafoam, values white mono, and units, method and notes muted grey. Every text colour meets WCAG AA (≥ 4.5:1), and `tests/ui_log_check.py` measures it. Bad readings are greyed and struck through rather than faded, so they stay legible. Columns: time, parameter, value (decimals aligned), range, unit, method, quality (SUSPECT / BAD; bad rows dimmed), note, ⋯ (Edit, Delete with an inline confirm). Readings taken within 10 minutes of a session's first reading form a session (`SESSION_WINDOW` in `app/overview.py`); its time shows once, with a stronger divider, and a note shared by every reading shows once. Unknown-time readings form their own session at the top of the day. Events are full-width rows in the same timeline. Parameter chips filter the rows and hide days left empty; collapsed summaries count only what passes the filter. On a phone the columns collapse to time, parameter, value + unit, quality, with method and note on a second line. Data from `GET /api/aquarium/<id>/log` (not used by the MCP server)
- **Charts** tab — One chart per parameter group over 7/30/90 days or all time. Water changes are drawn as dashed lines, CO2 bubble rate as a step chart; suspect readings are marked, bad ones are left off
- **Scheduled Tasks** — Recurring and one-time maintenance reminders. **Hidden by default**: see [Schedule feature flag](#schedule-feature-flag)
- **Fish Inventory** — Track species with held/planned counts, auto-fetched Wikipedia thumbnails and species info
- **Events** — Water changes (%), CO2 bubble rate (bubbles/30s), fertilizer dose (ml/day), one-off doses, ammonia doses (ppm), livestock added, filter seeding, cycle complete, drop checker refills, equipment changes and routine maintenance; completed scheduled tasks are logged here too
- **Multi-Aquarium** — Track multiple tanks; the Manage Aquariums page (`/aquariums`) lists every tank with edit and delete. Every tank has a short unique code (`100P`, `HQT`), which is required (the database enforces it); CSV import and the MCP server name tanks by it. The dashboard switches tanks with code pills, in each tank's **Order** (editable on Manage; new tanks go last), and remembers the last one picked; the **+** pill opens Manage's add form The old per-tank URL `/aquarium/<id>` redirects (302) to `/?aquarium_id=<id>`; an unknown id is a 404.
- **Target ranges** — Per tank and parameter (plus CO2 pH drop), either end optional, edited under *Target ranges* on Manage Aquariums. Values outside the parameter's plausible range are rejected
- **CSV Export / Import** — Readings and events export as CSV from the Charts tab; `import_csv.py` reads the same format (see below)
- **PWA** — Install as a standalone app on iOS/Android from the browser
- **Claude connector** — `waterscribe_mcp/` is an insert-only MCP server, so Claude can log readings and events and read recent history (see [waterscribe_mcp/README.md](waterscribe_mcp/README.md))
- **Slack Notifications** — Optional DMs for due/overdue tasks and new task alerts

## Screenshots

The UI features a dark ocean theme with animated bubbles, gradient accents, and a responsive layout that works great on phones.

## Tech Stack

- **Backend:** Python 3 / Flask / SQLAlchemy / PostgreSQL
- **Frontend:** Vanilla HTML/CSS/JS / Chart.js (pinned to 4.6.1 in `base.html`)
- **Deployment:** Gunicorn + Nginx + systemd
- **PWA:** Service worker + Web App Manifest

## Quick Start

### Prerequisites

- Python 3.10+
- PostgreSQL

### Setup

```bash
# Clone
git clone https://github.com/rfcampbell/Waterscribe.git
cd Waterscribe

# Virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your database credentials and secret key

# Database setup
createdb waterscribe
flask db upgrade

# Run
flask run
```

### Production Deployment

```bash
# Install gunicorn
pip install gunicorn

# Run with gunicorn
gunicorn --workers 3 --bind 127.0.0.1:5000 wsgi:app
```

See `nginx-waterscribe.conf` and `waterscribe.service` (the configs deployed on robix) and `DEPLOYMENT.md`.

### Importing CSV

```bash
venv/bin/python import_csv.py readings.csv --dry-run   # validate, report, write nothing (read-only transaction)
venv/bin/python import_csv.py readings.csv
venv/bin/python import_csv.py events.csv --aquarium 100p
```

A dry run is safe against prod: it runs in a `READ ONLY` transaction, so Postgres refuses any write.

Readings columns: `date,time,tank,parameter,value,value_min,value_max,unit,method,quality,notes`.
Events columns: `date,time,tank,event,value,unit,notes`. The kind is detected from the header,
and `tank` selects the aquarium by name unless `--aquarium` is given. Blank `time` means the time
is unknown (stored at 12:00, shown as date only). Units and values are checked as described
under *Units and plausible ranges* below.
Any invalid row aborts the whole file; rows already stored are skipped, so re-running is safe.
Times are local wall-clock time, not UTC.

### Backups

`deploy/backup-db` runs nightly at 03:45 (`deploy/waterscribe-backup.timer`, installed in
`/etc/systemd/system/`). It writes `~/waterscribe-backups/waterscribe-nightly-*.dump`, keeps 30 days,
and verifies each dump by restoring it into a scratch DB and comparing every table's row count and
the schema version with live. A dump that fails verification is renamed `*.unverified`; the unit
fails and `OnFailure=robix-alert@` notifies Home Assistant. Backups are on robix's own disk only.

```bash
systemctl list-timers waterscribe-backup.timer          # next/last run
journalctl -u waterscribe-backup -n 5                   # last result
pg_restore --clean --if-exists --no-owner -d "$DATABASE_URL" ~/waterscribe-backups/<dump>   # restore
```

### Units and plausible ranges

One set of rules, in `app/catalog.py` and `app/records.py`, applies to the web form, CSV import,
the API and the MCP server:

- **Conversions:** KH/GH given as `ppm`, `mg/L`, `ppm CaCO3` or `mg/L CaCO3` are divided by
  17.848 to give dKH/dGH. The original value is kept in the note.
- **Same unit, different spelling:** a blank unit means the catalog unit. Case, spaces, `µ`/`u`, a
  leading `°` and `ppm as X` are ignored. `mg/L` counts as `ppm`. A bare `ppm` for nitrate,
  phosphate, potassium or iron is taken as NO3, PO4, K or Fe. `percent` counts as `%`.
- **Rejected:** any other unit, for example `ppm NO3-N`, `ppm P`, `mS/cm`, `°C`, `meq/L`.
- **Plausible ranges** (checked after conversion, on the value and on its min and max): pH 3–10,
  ammonia/nitrite 0–10, nitrate 0–200, KH 0–30, GH 0–40, EC 0–2000, TDS 0–1500, temperature
  50–100 °F, phosphate 0–20, potassium 0–100, iron 0–5. A value outside its range is rejected with
  an error naming the parameter, value and range. Editing a range in `RANGES` is how to allow
  something unusual.

Tests: `venv/bin/python -m unittest discover -s tests -v`. Tests that need a database set
`WATERSCRIBE_TEST_DATABASE_URL` to a restored copy named `ws_*`, and refuse to run on anything else
(prod's `DATABASE_URL` is only in `.env`; nothing loads it into a shell unless you source it).

Browser checks use Playwright from a separate dev venv — never the app's `venv/`, which is what gunicorn runs:

```bash
python3 -m venv .venv-dev
.venv-dev/bin/pip install -r requirements-dev.txt   # Playwright, pinned
.venv-dev/bin/playwright install chromium           # Playwright picks and finds its own browser build
.venv-dev/bin/python tests/ui_drawer_check.py http://127.0.0.1:5055 --tank 4 --other 5 [--shots DIR]
.venv-dev/bin/python tests/ui_log_check.py http://127.0.0.1:5055 --tank 4 [--shots DIR]
.venv-dev/bin/python tests/ui_tiles_chart_check.py http://127.0.0.1:5055 --tank 4 [--shots DIR]
```

`ui_tiles_chart_check.py` checks the tile grid at 1920, 1280 and iPhone widths: one grid in `TILE_GROUPS` order, full rows, 210px minimum or 2 columns, each tile's group accent and its 3:1 contrast against the tile. For the chart it answers one `/series` request with the real data plus injected outliers (suspect high and low, bad high) and a wide target. It then checks the scale, the edge pinning, the marker pixels and the tooltips, with *show bad readings* off and on. It is read-only.


`ui_log_check.py` covers the log: days start collapsed, summaries match their rows and follow the filter, session memory, Expand/Collapse all, the entry form existing only in the drawer, page order, and measured AA contrast of every visible log text. It is read-only. `ui_drawer_check.py` drives the entry drawer at desktop and iPhone sizes: prefill, closing keeps the draft,
every way off the page warns, a draft can't save to or show up in another tank, and back doesn't restore a
discarded one. It writes nothing: readings POSTs are intercepted and answered with a fake success, and any other
non-GET request is blocked and fails the run — so it is safe to run against prod after a deploy. Not picked up by `unittest discover`.

### API used by the MCP server

`GET /api/aquariums` returns the tanks with their codes. `GET /api/catalog` returns parameters, units and event types. `POST /api/aquarium/<id>/readings` accepts a `unit` on each reading, plus an optional `date`/`time` per reading, and echoes the stored rows. `POST .../events` accepts a `unit`. Units are checked and converted as in the CSV import.

### Slack Notifications (Optional)

Add `SLACK_BOT_TOKEN` and `SLACK_NOTIFY_USER` to your `.env` to enable:
- DM notifications when scheduled tasks are created
- Periodic due/overdue task alerts via `check_tasks.py` (run via cron; only while `FEATURE_SCHEDULE` is on)

```bash
# Example crontab entry (8am, 12pm, 5pm)
0 8,12,17 * * * /path/to/venv/bin/python3 /path/to/check_tasks.py
```

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | Yes | Flask session secret |
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `FLASK_ENV` | No | `development` or `production` |
| `SESSION_COOKIE_SECURE` | No | Set `true` for HTTPS |
| `SLACK_BOT_TOKEN` | No | Slack bot token for notifications |
| `SLACK_NOTIFY_USER` | No | Slack user ID for DM notifications |
| `FEATURE_SCHEDULE` | No | `true` shows the Schedule feature; default off (see below) |

### Schedule feature flag

`FEATURE_SCHEDULE` in `.env` is the one switch for Scheduled Tasks. It defaults to off. Off hides every UI entry point: the Schedule tab and its panel, the "N tasks · next: …" part of the header line, and the task count on Manage Aquariums. The Manage delete confirmation still names a tank's tasks if it has any, because deleting the tank deletes them.

`check_tasks.py` reads the same flag. Off, it logs one line (`FEATURE_SCHEDULE is off; not checking scheduled tasks`, under `waterscribe-notify` in the journal) and exits 0 without touching the database or Slack. The cron entry stays. It reads `.env` on every run, so it needs no restart.

Nothing else changes. The `scheduled_tasks` table and its data, the `ScheduledTask` model, the `/api/aquarium/<id>/scheduled` and `/stats` API routes, the DM sent when a task is created through the API, and the tests are all untouched, and the API stays reachable directly.

To restore the feature, set `FEATURE_SCHEDULE=true` in `.env` and restart the app (`sudo systemctl restart waterscribe`). The service reads `.env` only at start, so a `kill -HUP` is not enough. With the flag on, the pages render byte-for-byte as they did before the flag existed. `tests/test_feature_schedule.py` checks both states.

## Future work

- **Per-tank plausible ranges.** `RANGES` in `app/catalog.py` is global. A medaka pond added as a
  tank would need its own temperature range, since it drops well below 50 °F in winter. That means
  per-tank overrides, checked in `check_range`.

## License

MIT
