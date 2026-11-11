# 🐠 WaterScribe

**Aquarium tracker for fishkeepers who care about their water.**

![WaterScribe](icon.png)

Track water parameters, schedule maintenance, manage fish inventory, and monitor your aquarium's health — all from a clean, mobile-friendly interface.

## Features

- **Water Parameters** — Each reading is its own record: value, optional min–max range (for colour-chart kits), method/kit, quality (`ok` / `suspect` / `bad`) and a note. Several readings taken together are entered in one form. Parameters: pH, ammonia, nitrite, nitrate, KH, GH, EC, degassed pH, temperature, TDS, phosphate, potassium, iron — add or reorder in `app/catalog.py`. Rows on the entry grid collapse; collapsed state is remembered per browser
- **Charts** — One chart per parameter group over 7/30/90 days or all time. Water changes are drawn as dashed lines, CO2 bubble rate as a step chart; suspect readings are marked, bad ones are left off
- **Scheduled Tasks** — Recurring and one-time maintenance reminders
- **Fish Inventory** — Track species with held/planned counts, auto-fetched Wikipedia thumbnails and species info
- **Events** — Water changes (%), CO2 bubble rate (bubbles/30s), fertilizer dose (ml/day), one-off doses, drop checker refills, equipment changes and routine maintenance; completed scheduled tasks are logged here too
- **Multi-Aquarium** — Track multiple tanks; the Manage Aquariums page (`/aquariums`) lists every tank with edit and delete
- **CSV Export / Import** — Readings and events export as CSV from the Charts tab; `import_csv.py` reads the same format (see below)
- **PWA** — Install as a standalone app on iOS/Android from the browser
- **Slack Notifications** — Optional DMs for due/overdue tasks and new task alerts

## Screenshots

The UI features a dark ocean theme with animated bubbles, gradient accents, and a responsive layout that works great on phones.

## Tech Stack

- **Backend:** Python 3 / Flask / SQLAlchemy / PostgreSQL
- **Frontend:** Vanilla HTML/CSS/JS / Chart.js
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
venv/bin/python import_csv.py readings.csv --dry-run   # validate, report, write nothing
venv/bin/python import_csv.py readings.csv
venv/bin/python import_csv.py events.csv --aquarium 100p
```

Readings columns: `date,time,tank,parameter,value,value_min,value_max,unit,method,quality,notes`.
Events columns: `date,time,tank,event,value,unit,notes`. The kind is detected from the header,
and `tank` selects the aquarium by name unless `--aquarium` is given. Blank `time` means the time
is unknown (stored at 12:00, shown as date only). Units are checked against `app/catalog.py`.
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

## License

MIT
