from __future__ import annotations
import re
import threading
from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from flask import Flask
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from bot import RESET_HOUR
from config import (
    ADMIN_USER_IDS,
    APP_HOME_SITES,
    DASHBOARD_URL,
    FH_WEDNESDAY_ANCHOR,
    SITE_ALIASES,
    SITE_EMOJI,
    SLACK_APP_TOKEN,
    SLACK_BOT_TOKEN,
    SUMMARY_CHANNEL_ID,
    TIMEZONE,
)
from db import (
    clear_state,
    get_all_users,
    get_current_checkin,
    get_daily_movements,
    get_live_statuses,
    get_schedule_for_user,
    get_state,
    get_statuses_for_date,
    get_user_history,
    init_db,
    record_checkin,
    set_schedule,
    set_schedule_override,
    set_state,
    upsert_user,
)
from scheduler import start_scheduler


# ---- General helpers -------------------------------------------------------

def now_local() -> datetime:
    return datetime.now(TIMEZONE)


def today_str() -> str:
    return now_local().date().isoformat()


def parse_work_date(value: str | None) -> date:
    if not value:
        return now_local().date()
    return date.fromisoformat(value)


def normalize_site(text: str) -> str | None:
    return SITE_ALIASES.get(text.strip().lower()) if text else None


def fetch_user_profile(client, user_id: str):
    resp = client.users_info(user=user_id)
    profile = resp["user"]["profile"]
    display_name = profile.get("display_name") or profile.get("real_name") or "Unknown"
    image_url = profile.get("image_72") or profile.get("image_48") or ""
    return display_name, image_url


def is_admin(user_id: str) -> bool:
    return user_id in ADMIN_USER_IDS


def is_front_half_day(work_day: date) -> bool:
    # Sun, Mon, Tue always on front half. Wed alternates.
    if work_day.weekday() in {6, 0, 1}:  # Sun, Mon, Tue with Monday=0? Actually Sun=6.
        return True
    if work_day.weekday() in {3, 4, 5}:  # Thu Fri Sat
        return False
    # Wednesday parity from a known front-half Wednesday anchor.
    anchor = date.fromisoformat(FH_WEDNESDAY_ANCHOR)
    weeks_apart = (work_day - anchor).days // 7
    return weeks_apart % 2 == 0


def is_expected_on_date(schedule: dict | None, work_day: date) -> bool:
    if not schedule or not schedule.get("is_active"):
        return False

    schedule_type = schedule.get("schedule_type")
    if schedule_type == "always_expected":
        return True
    if schedule_type == "never_expected":
        return False
    if schedule_type == "front_half":
        return is_front_half_day(work_day)
    if schedule_type == "back_half":
        return not is_front_half_day(work_day)
    if schedule_type == "custom":
        pattern = (schedule.get("custom_pattern") or "").strip()
        # Simple format: comma separated weekday numbers 0-6 where Monday=0.
        if not pattern:
            return False
        expected_days = {int(x.strip()) for x in pattern.split(",") if x.strip().isdigit()}
        return work_day.weekday() in expected_days
    return False


def build_summary_blocks(context: dict):
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"📍 Onsite Summary — {context['friendly_date']}", "emoji": True},
        },
        {"type": "divider"},
    ]

    total_people = 0
    for site, people in context["site_sections"]:
        if not people:
            continue
        total_people += len(people)
        names = ", ".join(p["display_name"] for p in people)
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"{SITE_EMOJI.get(site, '📍')} *{site}:* {names}"},
            }
        )

    if total_people == 0:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "_No one has checked in yet._"},
            }
        )

    if context["missing_people"]:
        missing_names = ", ".join(person["display_name"] for person in context["missing_people"])
        blocks.extend([
            {"type": "divider"},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"⏳ *Expected today, not checked in:* {missing_names}"}},
        ])

    blocks.extend([
        {"type": "divider"},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": f"<{DASHBOARD_URL}?date={context['work_date']}|Open dashboard>"}]},
    ])
    return blocks


def build_summary_text(context: dict) -> str:
    lines = [f"📍 Onsite Summary — {context['friendly_date']}"]
    added = False
    for site, people in context["site_sections"]:
        if not people:
            continue
        added = True
        names = ", ".join(p["display_name"] for p in people)
        lines.append(f"{SITE_EMOJI.get(site, '📍')} {site}: {names}")
    if not added:
        lines.append("No one has checked in yet.")
    if context["missing_people"]:
        lines.append("Expected today, not checked in: " + ", ".join(p["display_name"] for p in context["missing_people"]))
    lines.append(f"Dashboard: {DASHBOARD_URL}?date={context['work_date']}")
    return "\n".join(lines)


def compute_dashboard_context(work_date_value: str | None = None) -> dict:
    work_day = parse_work_date(work_date_value)
    work_date = work_day.isoformat()
    statuses = get_statuses_for_date(work_date)

    grouped = defaultdict(list)
    checked_in_ids = set()
    for row in statuses:
        grouped[row["site"]].append(row)
        checked_in_ids.add(row["slack_user_id"])

    preferred = ["ATL77", "ATL88", "ATL99", "ATL118", "REMOTE", "OFF"]
    site_sections = []
    for site in preferred:
        site_sections.append((site, sorted(grouped.get(site, []), key=lambda x: x["display_name"].lower())))
    for site in sorted(s for s in grouped if s not in preferred):
        site_sections.append((site, sorted(grouped[site], key=lambda x: x["display_name"].lower())))

    users = get_all_users()
    missing_people = []
    not_scheduled_people = []
    for user in users:
        schedule = {
            "schedule_type": user.get("schedule_type"),
            "custom_pattern": user.get("custom_pattern"),
            "is_active": user.get("is_active", 0),
        }
        expected = is_expected_on_date(schedule, work_day)
        basic_user = {
            "slack_user_id": user["slack_user_id"],
            "display_name": user["display_name"],
            "image_url": user.get("image_url") or "",
        }
        if expected and user["slack_user_id"] not in checked_in_ids:
            missing_people.append(basic_user)
        elif not expected:
            not_scheduled_people.append(basic_user)

    movements = get_daily_movements(work_date)
    previous_day = (work_day - timedelta(days=1)).isoformat()
    next_day = (work_day + timedelta(days=1)).isoformat()

    return {
        "work_date": work_date,
        "friendly_date": work_day.strftime("%A, %B %d, %Y"),
        "date_str": work_day.strftime("%A, %b %d"),
        "is_today": work_day == now_local().date(),
        "site_sections": site_sections,
        "missing_people": sorted(missing_people, key=lambda x: x["display_name"].lower()),
        "not_scheduled_people": sorted(not_scheduled_people, key=lambda x: x["display_name"].lower()),
        "movements": movements,
        "emoji_map": SITE_EMOJI,
        "previous_day": previous_day,
        "next_day": next_day,
    }


def upsert_summary_message(client):
    context = compute_dashboard_context(today_str())
    summary_ts = get_state("summary_ts")
    text = build_summary_text(context)
    blocks = build_summary_blocks(context)

    if summary_ts:
        try:
            client.chat_update(channel=SUMMARY_CHANNEL_ID, ts=summary_ts, text=text, blocks=blocks)
            return
        except Exception:
            pass

    resp = client.chat_postMessage(channel=SUMMARY_CHANNEL_ID, text=text, blocks=blocks)
    set_state("summary_ts", resp["ts"])


# ---- App Home --------------------------------------------------------------

def build_app_home(user_id: str):
    checkin = get_current_checkin(user_id)
    if checkin and checkin["work_date"] == today_str():
        status_text = f"{SITE_EMOJI.get(checkin['site'], '📍')} *Current status:* {checkin['site']}\n🕐 Updated: {checkin['updated_at']}"
    else:
        status_text = "❓ *You haven't checked in today.*"

    schedule = get_schedule_for_user(user_id)
    if schedule and schedule.get("schedule_type"):
        schedule_text = f"*Schedule:* `{schedule['schedule_type']}`"
    else:
        schedule_text = "*Schedule:* not set"

    buttons = []
    for site in APP_HOME_SITES:
        btn = {
            "type": "button",
            "text": {"type": "plain_text", "text": f"{SITE_EMOJI.get(site, '📍')} {site}", "emoji": True},
            "value": site,
            "action_id": f"home_checkin_{site}",
        }
        if checkin and checkin.get("site") == site and checkin.get("work_date") == today_str():
            btn["style"] = "primary"
        if now_local().hour < RESET_HOUR:
            btn["style"] = "default"
        buttons.append(btn)

    return {
        "type": "home",
        "blocks": [
            {"type": "header", "text": {"type": "plain_text", "text": "📍 Onsite Slack Bot", "emoji": True}},
            {"type": "divider"},
            {"type": "section", "text": {"type": "mrkdwn", "text": status_text}},
            {"type": "section", "text": {"type": "mrkdwn", "text": schedule_text}},
            {"type": "divider"},
            {"type": "section", "text": {"type": "mrkdwn", "text": "*Where are you today?*"}},
            {"type": "actions", "elements": buttons},
            {"type": "divider"},
            {"type": "context", "elements": [{"type": "mrkdwn", "text": f"<{DASHBOARD_URL}?date={today_str()}|View team dashboard> · Use `/onsite <site>` anytime."}]},
        ],
    }




def publish_home(client, user_id: str):
    client.views_publish(user_id=user_id, view=build_app_home(user_id))


# ---- Slack listeners -------------------------------------------------------

slack_app = App(token=SLACK_BOT_TOKEN)


@slack_app.event("app_home_opened")
def handle_home_opened(event, client, logger):
    try:
        publish_home(client, event["user"])
    except Exception:
        logger.exception("Failed to publish App Home")


@slack_app.action(re.compile(r"^home_checkin_.+"))
def handle_home_button(ack, body, client, logger):
    ack()
    user_id = body["user"]["id"]
    site = body["actions"][0]["value"]
    try:
        display_name, image_url = fetch_user_profile(client, user_id)
        upsert_user(user_id, display_name, image_url)
        record_checkin(user_id, site, today_str(), now_local().isoformat(timespec="seconds"), source="app_home")
        upsert_summary_message(client)
        publish_home(client, user_id)
    except Exception:
        logger.exception("Failed App Home check-in")


@slack_app.command("/onsite")
def handle_onsite(ack, body, client, logger):
    user_id = body["user_id"]
    text = (body.get("text") or "").strip()

    if not text:
        current = get_current_checkin(user_id)
        if current and current["work_date"] == today_str():
            msg = f"{SITE_EMOJI.get(current['site'], '📍')} You're currently checked in as *{current['site']}* (updated {current['updated_at']})."
        else:
            msg = "❓ You haven't checked in today. Try `/onsite ATL77`, `/onsite remote`, or `/onsite off`."
        ack({"response_type": "ephemeral", "text": msg})
        return

    site = normalize_site(text)
    if not site:
        ack({
            "response_type": "ephemeral",
            "text": "❓ Unrecognized site. Try `/onsite ATL77`, `/onsite ATL88`, `/onsite ATL99`, `/onsite ATL118`, `/onsite remote`, or `/onsite off`."
        })
        return

    try:
        display_name, image_url = fetch_user_profile(client, user_id)
        upsert_user(user_id, display_name, image_url)
        record_checkin(user_id, site, today_str(), now_local().isoformat(timespec="seconds"), source="slash_command")
        upsert_summary_message(client)
        publish_home(client, user_id)
        ack({"response_type": "ephemeral", "text": f"{SITE_EMOJI.get(site, '📍')} Checked in as *{site}*. <{DASHBOARD_URL}?date={today_str()}|View dashboard>."})
    except Exception as exc:
        logger.exception("Error handling /onsite")
        ack({"response_type": "ephemeral", "text": f"⚠️ Something went wrong: {exc}"})


@slack_app.command("/onsite-history")
def handle_history(ack, body, client, logger):
    user_id = body["user_id"]
    text = (body.get("text") or "").strip()
    target_user = user_id

    # optional admin use: /onsite-history U12345
    if text.startswith("U"):
        if not is_admin(user_id):
            ack({"response_type": "ephemeral", "text": "Only configured admins can query another user's history."})
            return
        target_user = text

    history = get_user_history(target_user, limit=10)
    if not history:
        ack({"response_type": "ephemeral", "text": "No history found yet."})
        return

    lines = ["*Recent onsite history*:"]
    for row in history:
        lines.append(f"• {row['work_date']}: *{row['site']}* at {row['checked_in_at']}")
    ack({"response_type": "ephemeral", "text": "\n".join(lines)})


@slack_app.command("/onsite-schedule")
def handle_schedule(ack, body, client, logger):
    user_id = body["user_id"]
    text = (body.get("text") or "").strip().lower()

    if not text:
        current = get_schedule_for_user(user_id)
        if not current:
            ack({"response_type": "ephemeral", "text": "No schedule set. Try `/onsite-schedule front_half` or `/onsite-schedule back_half`."})
            return
        ack({"response_type": "ephemeral", "text": f"Your current schedule is *{current['schedule_type']}*."})
        return

    if text not in {"front_half", "back_half", "always_expected", "never_expected"}:
        ack({"response_type": "ephemeral", "text": "Valid values: `front_half`, `back_half`, `always_expected`, `never_expected`."})
        return

    try:
        display_name, image_url = fetch_user_profile(client, user_id)
        upsert_user(user_id, display_name, image_url)
        set_schedule(user_id, text)
        upsert_summary_message(client)
        publish_home(client, user_id)
        ack({"response_type": "ephemeral", "text": f"✅ Schedule updated to *{text}*."})
    except Exception as exc:
        logger.exception("Error setting schedule")
        ack({"response_type": "ephemeral", "text": f"⚠️ Something went wrong: {exc}"})


# ---- Flask dashboard -------------------------------------------------------

flask_app = Flask(__name__)


def register_dashboard_routes():
    from dashboard import dashboard_bp
    flask_app.register_blueprint(dashboard_bp)


# ---- Entrypoint ------------------------------------------------------------

def main():
    init_db()
    register_dashboard_routes()

    dashboard_thread = threading.Thread(
        target=lambda: flask_app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False),
        daemon=True,
    )
    dashboard_thread.start()
    print("✅ Dashboard running at http://localhost:5000/dashboard")

    start_scheduler(slack_app.client, after_reset_callback=upsert_summary_message)
    print("✅ Daily scheduler running")

    print("✅ Slack bot connecting via Socket Mode...")
    SocketModeHandler(slack_app, SLACK_APP_TOKEN).start()


if __name__ == "__main__":
    main()
