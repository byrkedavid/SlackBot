import os
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()

SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_APP_TOKEN = os.environ["SLACK_APP_TOKEN"]
SUMMARY_CHANNEL_ID = os.environ["SUMMARY_CHANNEL_ID"]

# Public URL users can click from Slack. Replace in production.
DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "http://localhost:5000/dashboard")
DB_PATH = os.environ.get("DB_PATH", "onsite.db")
TIMEZONE = ZoneInfo(os.environ.get("TIMEZONE", "America/New_York"))

# Morning prompt / reset time in local timezone.
RESET_HOUR = int(os.environ.get("RESET_HOUR", "6"))
RESET_MINUTE = int(os.environ.get("RESET_MINUTE", "0"))

# Anchor date used to determine alternating Wednesdays for front-half/back-half.
# Pick a Wednesday you know was a front-half Wednesday.
FH_WEDNESDAY_ANCHOR = os.environ.get("FH_WEDNESDAY_ANCHOR", "2026-01-07")

SITE_ALIASES = {
    "atl77": "ATL77", "77": "ATL77",
    "atl88": "ATL88", "88": "ATL88",
    "atl99": "ATL99", "99": "ATL99",
    "atl118": "ATL118", "118": "ATL118",
    "remote": "REMOTE", "wfh": "REMOTE", "home": "REMOTE",
    "off": "OFF", "out": "OFF", "pto": "OFF", "vacation": "OFF",
}

SITE_EMOJI = {
    "ATL77": "🏢",
    "ATL88": "🏢",
    "ATL99": "🏢",
    "ATL118": "🏢",
    "REMOTE": "🏠",
    "OFF": "🏖️",
}

APP_HOME_SITES = ["ATL77", "ATL88", "ATL99", "ATL118", "REMOTE", "OFF"]

# Check .env for admin user IDs
ADMIN_USER_IDS = {
    user_id.strip()
    for user_id in os.environ.get("ADMIN_USER_IDS", "").split(",")
    if user_id.strip()
}
