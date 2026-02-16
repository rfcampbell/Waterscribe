"""
Slack notification helper for WaterScribe
Sends DMs when scheduled tasks are created or updated.
"""
import os
import json
import logging
from urllib.request import Request, urlopen
from urllib.error import URLError

logger = logging.getLogger(__name__)

SLACK_BOT_TOKEN = os.environ.get('SLACK_BOT_TOKEN')
SLACK_NOTIFY_USER = os.environ.get('SLACK_NOTIFY_USER', 'U085FCXMG')

def _post_slack(channel, text):
    """Post a message to Slack via the Web API."""
    if not SLACK_BOT_TOKEN:
        logger.warning("SLACK_BOT_TOKEN not set, skipping notification")
        return False
    
    try:
        payload = json.dumps({"channel": channel, "text": text}).encode()
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
            logger.error("Slack API error: %s", result.get("error"))
            return False
        return True
    except (URLError, Exception) as e:
        logger.error("Failed to send Slack notification: %s", e)
        return False


def notify_task_created(task, aquarium_name):
    """Send a Slack DM when a new scheduled task is created."""
    due = task.next_due.strftime('%b %d, %Y') if task.next_due else 'No date set'
    recurring = "🔁 Recurring" if task.is_recurring else "📌 One-time"
    
    text = (
        f"🐠 *New WaterScribe Task*\n"
        f"*{task.task_name}* ({recurring})\n"
        f"🏠 Aquarium: {aquarium_name}\n"
        f"📅 Due: {due}\n"
    )
    if task.description:
        text += f"📝 {task.description}\n"
    
    return _post_slack(SLACK_NOTIFY_USER, text)


def notify_task_due(task, aquarium_name, overdue=False):
    """Send a Slack DM for a due or overdue task."""
    due = task.next_due.strftime('%b %d, %Y') if task.next_due else 'Unknown'
    status = "⚠️ *OVERDUE*" if overdue else "⏰ *Due Today*"
    
    text = (
        f"🐠 {status}\n"
        f"*{task.task_name}*\n"
        f"🏠 Aquarium: {aquarium_name}\n"
        f"📅 Due: {due}\n"
    )
    if task.description:
        text += f"📝 {task.description}\n"
    
    return _post_slack(SLACK_NOTIFY_USER, text)
