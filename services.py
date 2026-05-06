from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime

from config import APP_HOME_SITES, SITE_EMOJI, TIMEZONE
from db import (
    get_all_users,
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


def source_label(source: str | None) -> str:
    return {
        "slash_command": "slash command",
        "app_home": "App Home",
        "admin_modal": "admin",
        "passive_message": "channel message",
    }.get(source or "", source or "unknown")


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
) -> dict:
    work_day = parse_work_date(work_date_value)
    work_date = work_day.isoformat()
    statuses = get_statuses_for_date(work_date)

    users = get_all_users()
    users = [u for u in users if not is_bot_or_app_user(u)]
    users_by_id = {u["slack_user_id"]: u for u in users}

    grouped = defaultdict(list)
    for row in statuses:
        row = dict(row)
        if row["slack_user_id"] not in users_by_id:
            continue

        row["display_updated_at"] = format_dt_short(row.get("updated_at"))
        row["source_label"] = source_label(row.get("source"))

        grouped[row["site"]].append(row)

    preferred = APP_HOME_SITES
    site_sections = []
    for site in preferred:
        site_sections.append((site, sorted(grouped.get(site, []), key=lambda x: x["display_name"].lower())))
    for site in sorted(s for s in grouped if s not in preferred):
        site_sections.append((site, sorted(grouped[site], key=lambda x: x["display_name"].lower())))

    site_sections = [
        (site, people)
        for site, people in site_sections
        if people
    ]

    return {
        "work_date": work_date,
        "friendly_date": work_day.strftime("%A, %B %d, %Y"),
        "date_str": work_day.strftime("%A, %B %d"),
        "is_today": work_day == now_local().date(),
        "site_sections": site_sections,
        "emoji_map": SITE_EMOJI,
        "all_users": users,
    }
