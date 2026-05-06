import os
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()

SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_APP_TOKEN = os.environ["SLACK_APP_TOKEN"]
SUMMARY_CHANNEL_ID = os.environ["SUMMARY_CHANNEL_ID"]

DB_PATH = os.environ.get("DB_PATH", "onsite.db")
TIMEZONE = ZoneInfo(os.environ.get("TIMEZONE", "America/New_York"))

SEED_TEST_USERS = os.environ.get("SEED_TEST_USERS", "").lower() in {"1", "true", "yes"}

SITE_ALIASES = {
    "atl55": "ATL55", "55": "ATL55",
    "atl66": "ATL66", "66": "ATL66",
    "atl77": "ATL77", "77": "ATL77",
    "atl88": "ATL88", "88": "ATL88",
    "atl99": "ATL99", "99": "ATL99",
    "atl118": "ATL118", "118": "ATL118",
    "remote": "REMOTE", "wfh": "REMOTE", "home": "REMOTE",
    "off": "OFF", "out": "OFF", "pto": "OFF", "vacation": "OFF",
}

SITE_EMOJI = {
    "ATL55": "🏢",
    "ATL66": "🏢",
    "ATL77": "🏢",
    "ATL88": "🏢",
    "ATL99": "🏢",
    "ATL118": "🏢",
    "REMOTE": "🏠",
    "OFF": "🏖️",
}

APP_HOME_SITES = ["ATL55", "ATL66", "ATL77", "ATL88", "ATL99", "ATL118", "REMOTE", "OFF"]

# Check .env for admin user IDs
ADMIN_USER_IDS = {
    user_id.strip()
    for user_id in os.environ.get("ADMIN_USER_IDS", "").split(",")
    if user_id.strip()
}
