# 🐠 WaterScribe

**Aquarium tracker for fishkeepers who care about their water.**

![WaterScribe](icon.png)

Track water parameters, schedule maintenance, manage fish inventory, and monitor your aquarium's health — all from a clean, mobile-friendly interface.

## Features

- **At a glance** — The Parameters page opens on one tile per parameter the tank has data for: latest value (bad readings never count; a suspect latest gets ⚠), method, age, a 30-day sparkline and the tank's target band. A tile fades with an amber age once its reading is older than the parameter's staleness limit (`STALE_DAYS` in `app/catalog.py`: EC 2 d, nitrate 7 d, KH/GH 14 d...). The value turns seafoam in band, coral out of band. Tanks with a degassed pH that pairs with a same-day in-tank pH (nearest in time) in the last 90 days get a derived **CO2 pH drop** tile showing the two readings used. Logic in `app/overview.py`
- **Water Parameters** — Each reading is its own record: value, optional min–max range (for colour-chart kits), method/kit, quality (`ok` / `suspect` / `bad`) and a note. Several readings taken together are entered in one form. Parameters: pH, ammonia, nitrite, nitrate, KH, GH, EC, degassed pH, temperature, TDS, phosphate, potassium, iron — add or reorder in `app/catalog.py`. Rows on the entry grid collapse; collapsed state is remembered per browser
- **Charts** — One chart per parameter group over 7/30/90 days or all time. Water changes are drawn as dashed lines, CO2 bubble rate as a step chart; suspect readings are marked, bad ones are left off
- **Scheduled Tasks** — Recurring and one-time maintenance reminders
- **Fish Inventory** — Track species with held/planned counts, auto-fetched Wikipedia thumbnails and species info
- **Events** — Water changes (%), CO2 bubble rate (bubbles/30s), fertilizer dose (ml/day), one-off doses, ammonia doses (ppm), livestock added, filter seeding, cycle complete, drop checker refills, equipment changes and routine maintenance; completed scheduled tasks are logged here too
- **Multi-Aquarium** — Track multiple tanks; the Manage Aquariums page (`/aquariums`) lists every tank with edit and delete. Every tank has a short unique code (`100P`, `HQT`), which is required (the database enforces it); CSV import and the MCP server name tanks by it. The dashboard switches tanks with code pills, in each tank's **Order** (editable on Manage; new tanks go last), and remembers the last one picked; the **+** pill opens Manage's add form
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

### API used by the MCP server

`GET /api/aquariums` returns the tanks with their codes. `GET /api/catalog` returns parameters, units and event types. `POST /api/aquarium/<id>/readings` accepts a `unit` on each reading, plus an optional `date`/`time` per reading, and echoes the stored rows. `POST .../events` accepts a `unit`. Units are checked and converted as in the CSV import.

### Slack Notifications (Optional)

Add `SLACK_BOT_TOKEN` and `SLACK_NOTIFY_USER` to your `.env` to enable:
- DM notifications when scheduled tasks are created
- Periodic due/overdue task alerts via `check_tasks.py` (run via cron)

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

## Future work

- **Dead route:** `GET /aquarium/<id>` (`aquarium_detail`) renders `dashboard/aquarium.html`, which
  doesn't exist, so gunicorn drops the connection. Nothing links to it; the dashboard uses
  `/?aquarium_id=`. Delete the route, or make it redirect.

- **Per-tank plausible ranges.** `RANGES` in `app/catalog.py` is global. A medaka pond added as a
  tank would need its own temperature range, since it drops well below 50 °F in winter. That means
  per-tank overrides, checked in `check_range`.

## License

MIT
