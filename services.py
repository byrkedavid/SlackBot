from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta

from config import SITE_EMOJI, TIMEZONE
from db import (
    get_all_users,
    get_daily_movements,
    get_schedule_override,
    get_statuses_for_date,
)


def now_local() -> datetime:
    return datetime.now(TIMEZONE)


def today_str() -> str:
    return now_local().date().isoformat()


def parse_work_date(value: str | None) -> date:
    if not value:
        return now_local().date()
    try:
        return date.fromisoformat(value)
    except ValueError:
        return now_local().date()


def format_dt_short(value: str | None) -> str:
    if not value:
        return "-"
    try:
        dt = datetime.fromisoformat(value)
        return dt.strftime("%b %d, %I:%M %p").replace(" 0", " ").lstrip("0")
    except Exception:
        return value


def schedule_label(schedule_type: str | None) -> str:
    mapping = {
        "front_half": "Front Half",
        "back_half": "Back Half",
        "always_expected": "Always Expected",
        "never_expected": "Never Expected",
        "custom": "Custom",
    }
    return mapping.get(schedule_type or "", "Not set")


def schedule_badge_class(schedule_type: str | None) -> str:
    return {
        "front_half": "badge-front",
        "back_half": "badge-back",
        "always_expected": "badge-always",
        "never_expected": "badge-never",
        "custom": "badge-custom",
    }.get(schedule_type or "", "badge-none")


def source_label(source: str | None) -> str:
    return {
        "slash_command": "slash command",
        "app_home": "App Home",
        "admin_modal": "admin",
    }.get(source or "", source or "unknown")


def is_expected_on_date(schedule: dict | None, work_day: date) -> bool:
    if not schedule or not schedule.get("is_active"):
        return False

    schedule_type = schedule.get("schedule_type")
    if schedule_type == "always_expected":
        return True
    if schedule_type == "never_expected":
        return False
    if schedule_type == "front_half":
        return work_day.weekday() in {6, 0, 1, 2}  # Sun-Wed
    if schedule_type == "back_half":
        return work_day.weekday() in {2, 3, 4, 5}  # Wed-Sat
    if schedule_type == "custom":
        pattern = (schedule.get("custom_pattern") or "").strip()
        # Simple format: comma separated weekday numbers 0-6 where Monday=0.
        if not pattern:
            return False
        expected_days = {int(x.strip()) for x in pattern.split(",") if x.strip().isdigit()}
        return work_day.weekday() in expected_days
    return False


def is_bot_or_app_user(user: dict) -> bool:
    name = (user.get("display_name") or "").lower()
    user_id = user.get("slack_user_id") or ""

    return (
        user_id.startswith("B")
        or "bot" in name
        or "slackbot" in name
        or "onsite bot" in name
    )


def compute_dashboard_context(
    work_date_value: str | None = None,
    site_filter: list[str] | None = None,
    show_all_sites: bool = False,
) -> dict:
    work_day = parse_work_date(work_date_value)
    work_date = work_day.isoformat()
    statuses = get_statuses_for_date(work_date)

    users = get_all_users()
    users = [u for u in users if not is_bot_or_app_user(u)]
    users_by_id = {u["slack_user_id"]: u for u in users}

    grouped = defaultdict(list)
    checked_in_ids = set()

    for row in statuses:
        row = dict(row)
        if row["slack_user_id"] not in users_by_id:
            continue
        user_info = users_by_id.get(row["slack_user_id"], {})

        schedule_type = user_info.get("schedule_type")
        row["schedule_type"] = schedule_type
        row["schedule_label"] = schedule_label(schedule_type)
        row["schedule_badge_class"] = schedule_badge_class(schedule_type)
        row["display_updated_at"] = format_dt_short(row.get("updated_at"))
        row["source_label"] = source_label(row.get("source"))

        grouped[row["site"]].append(row)
        checked_in_ids.add(row["slack_user_id"])

    preferred = ["ATL77", "ATL88", "ATL99", "ATL118", "REMOTE", "OFF"]
    site_sections = []
    for site in preferred:
        site_sections.append((site, sorted(grouped.get(site, []), key=lambda x: x["display_name"].lower())))
    for site in sorted(s for s in grouped if s not in preferred):
        site_sections.append((site, sorted(grouped[site], key=lambda x: x["display_name"].lower())))

    all_sites = [site for site, _people in site_sections]

    if not show_all_sites:
        site_sections = [
            (site, people)
            for site, people in site_sections
            if people
        ]

    if site_filter:
        site_sections = [
            (site, people)
            for site, people in site_sections
            if site in site_filter
        ]

    missing_people = []
    not_scheduled_people = []
    for user in users:
        schedule = {
            "schedule_type": user.get("schedule_type"),
            "custom_pattern": user.get("custom_pattern"),
            "is_active": user.get("is_active", 0),
        }
        override = get_schedule_override(user["slack_user_id"], work_date)

        if override == "expected":
            expected = True
        elif override == "not_expected":
            expected = False
        else:
            expected = is_expected_on_date(schedule, work_day)

        basic_user = {
            "slack_user_id": user["slack_user_id"],
            "display_name": user["display_name"],
            "image_url": user.get("image_url") or "",
            "schedule_type": user.get("schedule_type"),
            "schedule_label": schedule_label(user.get("schedule_type")),
            "schedule_badge_class": schedule_badge_class(user.get("schedule_type")),
        }
        if expected and user["slack_user_id"] not in checked_in_ids:
            missing_people.append(basic_user)
        elif not expected:
            not_scheduled_people.append(basic_user)

    movements = get_daily_movements(work_date)
    for person in movements:
        for event in person["events"]:
            event["display_checked_in_at"] = format_dt_short(event.get("checked_in_at"))
            event["source_label"] = source_label(event.get("source"))

    previous_day = (work_day - timedelta(days=1)).isoformat()
    next_day = (work_day + timedelta(days=1)).isoformat()

    return {
        "work_date": work_date,
        "friendly_date": work_day.strftime("%A, %B %d, %Y"),
        "date_str": work_day.strftime("%A, %B %d"),
        "is_today": work_day == now_local().date(),
        "site_sections": site_sections,
        "missing_people": sorted(missing_people, key=lambda x: x["display_name"].lower()),
        "not_scheduled_people": sorted(not_scheduled_people, key=lambda x: x["display_name"].lower()),
        "movements": movements,
        "emoji_map": SITE_EMOJI,
        "previous_day": previous_day,
        "next_day": next_day,
        "all_users": users,
        "all_sites": all_sites,
        "selected_sites": site_filter or [],
        "show_all_sites": show_all_sites,
    }
