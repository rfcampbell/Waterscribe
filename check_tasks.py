#!/usr/bin/env python3
"""
WaterScribe Scheduled Task Notifier
Checks for due/overdue tasks and sends Slack DMs.
Run via cron: 0 8,12,17 * * * /home/rcampbell/aquarium-tracker/aquarium-tracker/venv/bin/python3 /home/rcampbell/aquarium-tracker/aquarium-tracker/check_tasks.py
"""
import os
import sys
import json
from urllib.request import Request, urlopen
from datetime import datetime, timezone

# Load .env manually
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, _, value = line.partition('=')
                os.environ.setdefault(key.strip(), value.strip())

SLACK_BOT_TOKEN = os.environ.get('SLACK_BOT_TOKEN')
SLACK_NOTIFY_USER = os.environ.get('SLACK_NOTIFY_USER', 'U085FCXMG')
DATABASE_URL = os.environ.get('DATABASE_URL')

if not SLACK_BOT_TOKEN or not DATABASE_URL:
    print("Missing SLACK_BOT_TOKEN or DATABASE_URL in .env", file=sys.stderr)
    sys.exit(1)

import psycopg2

def send_slack_dm(user_id, text):
    payload = json.dumps({"channel": user_id, "text": text}).encode()
    req = Request(
        "https://slack.com/api/chat.postMessage",
        data=payload,
        headers={
            "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
            "Content-Type": "application/json",
        },
    )
    resp = urlopen(req, timeout=10)
    result = json.loads(resp.read())
    if not result.get("ok"):
        print(f"Slack error: {result.get('error')}", file=sys.stderr)
        return False
    return True

def main():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    
    now = datetime.now(timezone.utc)
    today_end = now.replace(hour=23, minute=59, second=59)
    
    cur.execute("""
        SELECT st.id, st.task_name, st.next_due, st.description, st.is_recurring, st.frequency_days, a.name
        FROM scheduled_tasks st
        JOIN aquariums a ON st.aquarium_id = a.id
        WHERE st.active = true AND st.next_due <= %s
        ORDER BY st.next_due ASC
    """, (today_end,))
    
    tasks = cur.fetchall()
    cur.close()
    conn.close()
    
    if not tasks:
        return
    
    lines = ["🐠 *WaterScribe Tasks Due*\n"]
    for task_id, name, next_due, desc, is_recurring, freq, aquarium in tasks:
        # Handle naive datetimes from DB
        if next_due.tzinfo is None:
            from datetime import timezone as tz
            next_due = next_due.replace(tzinfo=tz.utc)
        overdue = next_due < now.replace(hour=0, minute=0, second=0)
        status = "⚠️ OVERDUE" if overdue else "⏰ Due today"
        due_str = next_due.strftime('%b %d') if next_due else '?'
        recurring = f"🔁 Every {freq}d" if is_recurring and freq else "📌 One-time"
        
        lines.append(f"*{name}* — {status} ({due_str})")
        lines.append(f"  🏠 {aquarium} | {recurring}")
        if desc:
            # Truncate long descriptions
            short = desc[:120] + "…" if len(desc) > 120 else desc
            lines.append(f"  📝 {short}")
        lines.append("")
    
    send_slack_dm(SLACK_NOTIFY_USER, "\n".join(lines))

if __name__ == "__main__":
    main()
