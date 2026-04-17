from __future__ import annotations

import threading
from datetime import datetime
from time import sleep

from config import RESET_HOUR, RESET_MINUTE, SUMMARY_CHANNEL_ID, TIMEZONE
from db import clear_all_current_checkins, clear_state


def run_daily_reset(client):
    now = datetime.now(TIMEZONE)
    today = now.strftime("%A, %b %d")

    clear_all_current_checkins()
    clear_state("summary_ts")

    prompt = (
        f"*☀️ Good morning! It's {today}.*\n"
        "Please check in so the team can see where everyone is early.\n\n"
        "• Use `/onsite ATL77`, `/onsite ATL88`, `/onsite ATL99`, `/onsite ATL118`, `/onsite remote`, or `/onsite off`\n"
        "• Or open the *Onsite Slack Bot* app in your Slack sidebar and tap your location\n\n"
        "_The living summary below will update as people check in._"
    )
    client.chat_postMessage(channel=SUMMARY_CHANNEL_ID, text=prompt)


def scheduler_loop(client, after_reset_callback=None):
    fired_marker: str | None = None
    while True:
        now = datetime.now(TIMEZONE)
        marker = now.strftime("%Y-%m-%d")
        if now.hour == RESET_HOUR and now.minute == RESET_MINUTE and fired_marker != marker:
            run_daily_reset(client)
            if after_reset_callback:
                after_reset_callback(client)
            fired_marker = marker
        sleep(20)


def start_scheduler(client, after_reset_callback=None) -> threading.Thread:
    thread = threading.Thread(
        target=lambda: scheduler_loop(client, after_reset_callback=after_reset_callback),
        daemon=True,
    )
    thread.start()
    return thread
