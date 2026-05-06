from __future__ import annotations
import re

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from services import (
    compute_dashboard_context,
    format_dt_short,
    now_local,
    today_str,
)

from config import (
    ADMIN_USER_IDS,
    APP_HOME_SITES,
    SEED_TEST_USERS,
    SITE_ALIASES,
    SITE_EMOJI,
    SLACK_APP_TOKEN,
    SLACK_BOT_TOKEN,
    SUMMARY_CHANNEL_ID,
)
from db import (
    clear_all_current_checkins,
    clear_state,
    get_current_checkin,
    get_state,
    get_user_history,
    init_db,
    record_checkin,
    set_state,
    upsert_user,
)


# ---- General helpers -------------------------------------------------------

def normalize_site(text: str) -> str | None:
    return SITE_ALIASES.get(text.strip().lower()) if text else None


ONSITE_MESSAGE_PATTERN = re.compile(
    r"\bon[\s-]*site\b\s*[:=-]?\s*(?P<site>(?:atl[\s-]*)?\d{2,3}|remote|wfh|home|off|out|pto|vacation)\b",
    re.IGNORECASE,
)


def extract_passive_onsite_site(text: str) -> str | None:
    """Find casual check-ins like 'onsite ATL77' or 'on-site 77' in channel text."""
    if not text:
        return None

    match = ONSITE_MESSAGE_PATTERN.search(text)
    if not match:
        return None

    site_text = re.sub(r"\s+", "", match.group("site"))
    return normalize_site(site_text)


def fetch_user_profile(client, user_id: str):
    resp = client.users_info(user=user_id)
    profile = resp["user"]["profile"]
    display_name = profile.get("display_name") or profile.get("real_name") or "Unknown"
    image_url = profile.get("image_72") or profile.get("image_48") or ""
    return display_name, image_url


def is_admin(user_id: str) -> bool:
    return user_id in ADMIN_USER_IDS

def get_admin_target_context(user_id: str) -> dict:
    current = get_current_checkin(user_id)

    if current and current.get("work_date") == today_str():
        current_text = (
            f"{SITE_EMOJI.get(current['site'], '📍')} Current today: *{current['site']}*"
            f" · Updated {format_dt_short(current.get('updated_at'))}"
        )
    else:
        current_text = "❓ Current today: *Not checked in*"

    return {
        "current_text": current_text,
    }


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

    blocks.extend([
        {"type": "divider"},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": "Open the Onsite Slack Bot App Home for the full team view."}]},
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
    lines.append("Open the Onsite Slack Bot App Home for the full team view.")
    return "\n".join(lines)


def build_slack_dashboard_blocks(context: dict, *, max_people_per_site: int = 12):
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"Team Dashboard - {context['date_str']}", "emoji": True},
        },
        {"type": "divider"},
    ]

    total_people = 0
    for site, people in context["site_sections"]:
        if not people:
            continue

        total_people += len(people)
        visible_people = people[:max_people_per_site]
        names = "\n".join(f"- {person['display_name']}" for person in visible_people)
        if len(people) > max_people_per_site:
            names += f"\n- +{len(people) - max_people_per_site} more"

        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{SITE_EMOJI.get(site, '📍')} *{site}*  |  {len(people)} checked in\n{names}",
                },
            }
        )

    if total_people == 0:
        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": "_No one has checked in yet._"}}
        )

    return blocks


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


# ---- Fake users for testing --------------------------------------------------------------

def seed_test_users():
    import random

    fake_users = [
        ("U_TEST_1", "John Smith"),
        ("U_TEST_2", "Mike Davis"),
        ("U_TEST_3", "Chris Lee"),
        ("U_TEST_4", "Alex Johnson"),
        ("U_TEST_5", "David Brown"),
        ("U_TEST_6", "Kevin White"),
        ("U_TEST_7", "Ryan Clark"),
        ("U_TEST_8", "Matt Hall"),
        ("U_TEST_9", "Jeff Green"),
        ("U_TEST_10", "Jay Bailey"),
        ("U_TEST_11", "Bryan Young"),
        ("U_TEST_12", "Hunter Knox"),
    ]

    #sites = ["ATL77", "ATL88", "OFF"]
    sites = APP_HOME_SITES

    for user_id, name in fake_users:
        upsert_user(user_id, name, "")

        # random check-in today
        site = random.choice(sites)
        record_checkin(
            user_id,
            site,
            today_str(),
            now_local().isoformat(timespec="seconds"),
            source="seed"
        )
    


# ---- App Home --------------------------------------------------------------

def build_app_home(user_id: str):
    checkin = get_current_checkin(user_id)
    if checkin and checkin["work_date"] == today_str():
        status_text = (
            f"{SITE_EMOJI.get(checkin['site'], '📍')} *Current site:* {checkin['site']}"
            f"\n🕐 Updated: {format_dt_short(checkin['updated_at'])}"
)
    else:
        status_text = "❓ *You haven't checked in today.*"

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
        buttons.append(btn)

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": "📍 Onsite Slack Bot", "emoji": True}},
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": status_text}},
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "Post `onsite ATL77` in the channel, use `/onsite <site>`, or tap a button below.",
                }
            ],
        },
        {"type": "actions", "elements": buttons},
    ]

    blocks.extend(
        [
            {"type": "divider"},
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Refresh Team View", "emoji": True},
                        "action_id": "refresh_app_home",
                        "value": "refresh_app_home",
                    }
                ] + (
                    [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Admin Controls", "emoji": True},
                            "action_id": "open_admin_modal",
                            "value": "open_admin_modal",
                        }
                    ] if is_admin(user_id) else []
                ),
            },
            *build_slack_dashboard_blocks(compute_dashboard_context(today_str())),
        ]
    )

    return {
        "type": "home",
        "blocks": blocks,
    }

def publish_home(client, user_id: str):
    client.views_publish(user_id=user_id, view=build_app_home(user_id))


# ---- Slack listeners -------------------------------------------------------

slack_app = App(token=SLACK_BOT_TOKEN, token_verification_enabled=False)


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


@slack_app.action("refresh_app_home")
def handle_refresh_app_home_button(ack, body, client, logger):
    ack()
    try:
        publish_home(client, body["user"]["id"])
    except Exception:
        logger.exception("Failed to refresh App Home")


@slack_app.event("message")
def handle_passive_onsite_message(event, client, logger):
    if event.get("channel") != SUMMARY_CHANNEL_ID:
        return
    if event.get("subtype") or event.get("bot_id") or event.get("user") is None:
        return

    site = extract_passive_onsite_site(event.get("text") or "")
    if not site:
        return

    user_id = event["user"]
    try:
        current = get_current_checkin(user_id)
        if current and current.get("work_date") == today_str() and current.get("site") == site:
            return

        display_name, image_url = fetch_user_profile(client, user_id)
        upsert_user(user_id, display_name, image_url)
        record_checkin(
            user_id,
            site,
            today_str(),
            now_local().isoformat(timespec="seconds"),
            source="passive_message",
        )
        upsert_summary_message(client)
        publish_home(client, user_id)
    except Exception:
        logger.exception("Failed passive onsite check-in")


@slack_app.command("/onsite-refresh")
def handle_refresh(ack, body, client, logger):
    ack({"response_type": "ephemeral", "text": "Refreshing App Home..."})
    publish_home(client, body["user_id"])

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

    site = normalize_site(text) or extract_passive_onsite_site(text)
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
        ack({"response_type": "ephemeral", "text": f"{SITE_EMOJI.get(site, '📍')} Checked in as *{site}*. Open the Onsite Slack Bot App Home for the team view."})
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
        lines.append(f"• {row['work_date']}: *{row['site']}* at {format_dt_short(row['checked_in_at'])}")
    ack({"response_type": "ephemeral", "text": "\n".join(lines)})


@slack_app.command("/onsite-admin")
def handle_admin(ack, body, client, logger):
    user_id = body["user_id"]

    if not is_admin(user_id):
        ack({"response_type": "ephemeral", "text": "❌ You are not an admin."})
        return

    ack()

    client.views_open(
        trigger_id=body["trigger_id"],
        view=build_admin_modal(),
    )
    
@slack_app.action("action_select")
def handle_admin_action_select(ack, body, client, logger):
    ack()
    try:
        selected_action = body["actions"][0]["selected_option"]["value"]
        view = body["view"]

        state_values = view.get("state", {}).get("values", {})
        selected_user = None
        if "user_block" in state_values and "user_select" in state_values["user_block"]:
            selected_user = state_values["user_block"]["user_select"].get("selected_user")

        client.views_update(
            view_id=view["id"],
            hash=view["hash"],
            view=build_admin_modal(
                selected_action=selected_action,
                selected_user=selected_user,
            ),
        )
    except Exception:
        logger.exception("Failed to update admin modal after action change")


@slack_app.action("user_select")
def handle_admin_user_select(ack, body, client, logger):
    ack()
    try:
        selected_user = body["actions"][0]["selected_user"]
        view = body["view"]

        state_values = view.get("state", {}).get("values", {})
        selected_action = None
        if "action_block" in state_values and "action_select" in state_values["action_block"]:
            action_obj = state_values["action_block"]["action_select"]
            if action_obj.get("selected_option"):
                selected_action = action_obj["selected_option"]["value"]

        client.views_update(
            view_id=view["id"],
            hash=view["hash"],
            view=build_admin_modal(
                selected_action=selected_action,
                selected_user=selected_user,
            ),
        )
    except Exception:
        logger.exception("Failed to update admin modal after user change")


def build_admin_modal(
    selected_action: str | None = None,
    selected_user: str | None = None,
):
    blocks = [
        {
            "type": "input",
            "block_id": "user_block",
            "label": {"type": "plain_text", "text": "Select User"},
            "dispatch_action": True,
            "element": {
                "type": "users_select",
                "action_id": "user_select",
                "placeholder": {
                    "type": "plain_text",
                    "text": "Choose a workspace member"
                },
                **({"initial_user": selected_user} if selected_user else {})
            }
        },
        {
            "type": "input",
            "block_id": "action_block",
            "label": {"type": "plain_text", "text": "Action"},
            "dispatch_action": True,
            "element": {
                "type": "static_select",
                "action_id": "action_select",
                "options": [
                    {"text": {"type": "plain_text", "text": "Check In"}, "value": "checkin"},
                    {"text": {"type": "plain_text", "text": "Reset Today"}, "value": "reset_today"},
                ],
                **(
                    {
                        "initial_option": {
                            "text": {
                                "type": "plain_text",
                                "text": {
                                    "checkin": "Check In",
                                    "reset_today": "Reset Today",
                                }[selected_action]
                            },
                            "value": selected_action,
                        }
                    }
                    if selected_action else {}
                )
            }
        },
    ]

    if selected_user:
        target_context = get_admin_target_context(selected_user)
        blocks.extend([
            {"type": "divider"},
            {
                "type": "section",
                "block_id": "target_context_block",
                "text": {
                    "type": "mrkdwn",
                    "text": target_context["current_text"]
                },
            },
        ])

    if selected_action == "checkin":
        blocks.append(
            {
                "type": "input",
                "block_id": "site_block",
                "label": {"type": "plain_text", "text": "Site"},
                "element": {
                    "type": "static_select",
                    "action_id": "site_select",
                    "options": [
                        {"text": {"type": "plain_text", "text": s}, "value": s}
                        for s in APP_HOME_SITES
                    ]
                }
            }
        )
    elif selected_action == "reset_today":
        blocks.append(
            {
                "type": "section",
                "block_id": "reset_warn_block",
                "text": {
                    "type": "mrkdwn",
                    "text": "⚠️ This will clear today's current check-ins and refresh the living summary."
                },
            }
        )

    return {
        "type": "modal",
        "callback_id": "admin_modal_submit",
        "title": {"type": "plain_text", "text": "Admin Controls"},
        "submit": {"type": "plain_text", "text": "Submit"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": blocks,
    }


@slack_app.view("admin_modal_submit")
def handle_admin_submit(ack, body, client, logger):
    ack()

    submitter_id = body["user"]["id"]
    values = body["view"]["state"]["values"]

    if not is_admin(submitter_id):
        client.chat_postMessage(channel=submitter_id, text="❌ You are not an admin.")
        return

    try:
        action = values["action_block"]["action_select"]["selected_option"]["value"]

        target_user = None
        if action != "reset_today":
            target_user = values["user_block"]["user_select"]["selected_user"]
            target_profile = client.users_info(user=target_user)["user"]
            if target_profile.get("is_bot") or target_profile.get("is_app_user") or target_profile.get("name") == "slackbot":
                client.chat_postMessage(
                    channel=submitter_id,
                    text="⚠️ Bot/app users cannot be managed with admin controls."
                )
                return

        if action == "checkin":
            site = values["site_block"]["site_select"]["selected_option"]["value"]
            display_name, image_url = fetch_user_profile(client, target_user)
            upsert_user(target_user, display_name, image_url)
            record_checkin(
                target_user,
                site,
                today_str(),
                now_local().isoformat(timespec="seconds"),
                source="admin_modal",
            )
            msg = f"✅ Updated <@{target_user}> → *{site}*"

        elif action == "reset_today":
            clear_all_current_checkins()
            clear_state("summary_ts")
            upsert_summary_message(client)
            msg = "✅ Reset today's check-ins and refreshed the living summary."

        else:
            msg = "⚠️ Unknown admin action."

        if action != "reset_today":
            upsert_summary_message(client)
            publish_home(client, target_user)

        client.chat_postMessage(channel=submitter_id, text=msg)

    except Exception as exc:
        logger.exception("Admin modal failed")
        client.chat_postMessage(channel=submitter_id, text=f"⚠️ Admin action failed: {exc}")

@slack_app.action("open_admin_modal")
def handle_open_admin_modal(ack, body, client, logger):
    ack()
    user_id = body["user"]["id"]

    if not is_admin(user_id):
        return

    try:
        client.views_open(
            trigger_id=body["trigger_id"],
            view=build_admin_modal(),
        )
    except Exception:
        logger.exception("Failed to open admin modal from App Home")

# ---- Entrypoint ------------------------------------------------------------

def main():
    init_db()

    if SEED_TEST_USERS:
        seed_test_users()

    print("✅ Slack bot connecting via Socket Mode...")
    SocketModeHandler(slack_app, SLACK_APP_TOKEN).start()


if __name__ == "__main__":
    main()
