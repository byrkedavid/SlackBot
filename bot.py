import os
import sqlite3
import threading
from datetime import datetime
from collections import defaultdict

from dotenv import load_dotenv
from flask import Flask, render_template_string
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────

SLACK_BOT_TOKEN    = os.environ["SLACK_BOT_TOKEN"]
SLACK_APP_TOKEN    = os.environ["SLACK_APP_TOKEN"]
SUMMARY_CHANNEL_ID = os.environ["SUMMARY_CHANNEL_ID"]
DASHBOARD_URL      = os.environ.get("DASHBOARD_URL", "http://localhost:5000/dashboard")
RESET_HOUR         = 6   # 6:00 AM local time

DB_PATH = "onsite.db"

SITE_ALIASES = {
    "atl77": "ATL77", "77": "ATL77",
    "atl88": "ATL88", "88": "ATL88",
    "atl99": "ATL99", "99": "ATL99",
    "remote": "REMOTE", "wfh": "REMOTE",
    "off": "OFF", "out": "OFF", "pto": "OFF",
}

SITE_EMOJI = {
    "ATL77":  "🏢",
    "ATL88":  "🏢",
    "ATL99":  "🏢",
    "REMOTE": "🏠",
    "OFF":    "🏖️",
}

APP_HOME_SITES = ["ATL77", "ATL88", "ATL99", "REMOTE", "OFF"]

# ── Database ──────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                slack_user_id TEXT PRIMARY KEY,
                display_name  TEXT,
                image_url     TEXT
            );
            CREATE TABLE IF NOT EXISTS checkins (
                slack_user_id TEXT PRIMARY KEY,
                site          TEXT,
                updated_at    TEXT,
                FOREIGN KEY (slack_user_id) REFERENCES users(slack_user_id)
            );
            CREATE TABLE IF NOT EXISTS app_state (
                key   TEXT PRIMARY KEY,
                value TEXT
            );
        """)

def upsert_user(user_id, display_name, image_url):
    with get_db() as conn:
        conn.execute("""
            INSERT INTO users (slack_user_id, display_name, image_url)
            VALUES (?, ?, ?)
            ON CONFLICT(slack_user_id) DO UPDATE SET
                display_name = excluded.display_name,
                image_url    = excluded.image_url
        """, (user_id, display_name, image_url))

def upsert_checkin(user_id, site):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with get_db() as conn:
        conn.execute("""
            INSERT INTO checkins (slack_user_id, site, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(slack_user_id) DO UPDATE SET
                site       = excluded.site,
                updated_at = excluded.updated_at
        """, (user_id, site, now))

def clear_all_checkins():
    with get_db() as conn:
        conn.execute("DELETE FROM checkins")

def get_user_checkin(user_id):
    with get_db() as conn:
        row = conn.execute("""
            SELECT site, updated_at FROM checkins WHERE slack_user_id = ?
        """, (user_id,)).fetchone()
    return dict(row) if row else None

def get_all_statuses():
    with get_db() as conn:
        rows = conn.execute("""
            SELECT u.slack_user_id, u.display_name, u.image_url,
                   c.site, c.updated_at
            FROM checkins c
            JOIN users u ON u.slack_user_id = c.slack_user_id
            ORDER BY u.display_name
        """).fetchall()
    return [dict(r) for r in rows]

def get_state(key):
    with get_db() as conn:
        row = conn.execute("SELECT value FROM app_state WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None

def set_state(key, value):
    with get_db() as conn:
        conn.execute("""
            INSERT INTO app_state (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (key, value))

def clear_state(key):
    with get_db() as conn:
        conn.execute("DELETE FROM app_state WHERE key = ?", (key,))

# ── Helpers ───────────────────────────────────────────────────────────────────

def normalize_site(text: str):
    return SITE_ALIASES.get(text.strip().lower())

def fetch_user_profile(client, user_id):
    resp = client.users_info(user=user_id)
    profile = resp["user"]["profile"]
    display_name = profile.get("display_name") or profile.get("real_name", "Unknown")
    image_url = profile.get("image_72", "")
    return display_name, image_url

def build_summary_text(statuses):
    grouped = defaultdict(list)
    for row in statuses:
        grouped[row["site"]].append(row["display_name"])

    preferred = ["ATL77", "ATL88", "ATL99", "REMOTE", "OFF"]
    lines = [f"*📍 Onsite Summary — {datetime.now().strftime('%A, %b %d')}*"]

    for site in preferred:
        people = sorted(grouped.get(site, []))
        if people:
            emoji = SITE_EMOJI.get(site, "📍")
            lines.append(f"{emoji} *{site}:* " + ", ".join(people))

    for site in sorted(s for s in grouped if s not in preferred):
        lines.append(f"📍 *{site}:* " + ", ".join(sorted(grouped[site])))

    if not any(grouped.get(s) for s in preferred):
        lines.append("_No one has checked in yet._")

    lines.append(f"\n<{DASHBOARD_URL}|View full dashboard>")
    return "\n".join(lines)

def upsert_summary_message(client):
    """Post or update the single living summary message in the channel."""
    statuses = get_all_statuses()
    text = build_summary_text(statuses)
    summary_ts = get_state("summary_ts")

    if summary_ts:
        try:
            client.chat_update(channel=SUMMARY_CHANNEL_ID, ts=summary_ts, text=text)
            return
        except Exception:
            pass  # message was deleted — fall through and post a new one

    resp = client.chat_postMessage(channel=SUMMARY_CHANNEL_ID, text=text)
    set_state("summary_ts", resp["ts"])

# ── App Home ──────────────────────────────────────────────────────────────────

def build_app_home(user_id):
    checkin = get_user_checkin(user_id)

    if checkin:
        emoji = SITE_EMOJI.get(checkin["site"], "📍")
        status_text = f"{emoji} *Current status:* {checkin['site']}\n🕐 Updated: {checkin['updated_at']}"
    else:
        status_text = "❓ *You haven't checked in today.*"

    site_buttons = []
    for site in APP_HOME_SITES:
        emoji = SITE_EMOJI.get(site, "📍")
        btn = {
            "type": "button",
            "text": {"type": "plain_text", "text": f"{emoji} {site}", "emoji": True},
            "value": site,
            "action_id": f"home_checkin_{site}",
        }
        if checkin and checkin["site"] == site:
            btn["style"] = "primary"
        site_buttons.append(btn)

    return [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "📍 Onsite Check-In", "emoji": True},
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": status_text},
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*Where are you today?*"},
        },
        {
            "type": "actions",
            "elements": site_buttons,
        },
        {"type": "divider"},
        {
            "type": "context",
            "elements": [{
                "type": "mrkdwn",
                "text": f"<{DASHBOARD_URL}|View full team dashboard> · Use `/onsite <site>` anytime to update quickly.",
            }],
        },
    ]

def publish_home(client, user_id):
    client.views_publish(
        user_id=user_id,
        view={"type": "home", "blocks": build_app_home(user_id)},
    )

# ── Slack App (Bolt) ──────────────────────────────────────────────────────────

slack_app = App(token=SLACK_BOT_TOKEN)

@slack_app.event("app_home_opened")
def handle_home_opened(event, client, logger):
    try:
        publish_home(client, event["user"])
    except Exception:
        logger.exception("Failed to publish App Home")

@slack_app.action({"action_id": lambda aid: aid.startswith("home_checkin_")})
def handle_home_button(ack, body, client, logger):
    ack()
    user_id = body["user"]["id"]
    site = body["actions"][0]["value"]
    try:
        display_name, image_url = fetch_user_profile(client, user_id)
        upsert_user(user_id, display_name, image_url)
        upsert_checkin(user_id, site)
        upsert_summary_message(client)
        publish_home(client, user_id)
    except Exception:
        logger.exception("Failed to handle home button check-in")

@slack_app.command("/onsite")
def handle_onsite(ack, body, client, logger):
    user_id = body["user_id"]
    text    = body.get("text", "").strip()

    # No argument → show current status
    if not text:
        checkin = get_user_checkin(user_id)
        if checkin:
            emoji = SITE_EMOJI.get(checkin["site"], "📍")
            msg = f"{emoji} You're currently checked in as *{checkin['site']}* (updated {checkin['updated_at']})."
        else:
            msg = "❓ You haven't checked in today. Try `/onsite ATL77`, `/onsite remote`, etc."
        ack({"response_type": "ephemeral", "text": msg})
        return

    site = normalize_site(text)
    if not site:
        ack({
            "response_type": "ephemeral",
            "text": (
                "❓ Unrecognized site. Try:\n"
                "`/onsite ATL77` · `/onsite ATL88` · `/onsite ATL99` · "
                "`/onsite remote` · `/onsite off`"
            ),
        })
        return

    try:
        display_name, image_url = fetch_user_profile(client, user_id)
        upsert_user(user_id, display_name, image_url)
        upsert_checkin(user_id, site)
        upsert_summary_message(client)
        publish_home(client, user_id)

        emoji = SITE_EMOJI.get(site, "📍")
        ack({
            "response_type": "ephemeral",
            "text": f"{emoji} Checked in as *{site}*. <{DASHBOARD_URL}|View dashboard>",
        })
    except Exception as exc:
        logger.exception("Error handling /onsite")
        ack({"response_type": "ephemeral", "text": f"⚠️ Something went wrong: {exc}"})

# ── Daily Reset ───────────────────────────────────────────────────────────────

def run_daily_reset(client):
    clear_all_checkins()
    clear_state("summary_ts")  # force a brand-new message instead of editing the old one

    today = datetime.now().strftime("%A, %b %d")
    prompt = (
        f"*☀️ Good morning! It's {today}.*\n"
        f"Please check in to let the team know where you'll be today.\n\n"
        f"• Use `/onsite ATL77`, `/onsite ATL88`, `/onsite ATL99`, `/onsite remote`, or `/onsite off`\n"
        f"• Or open the *Onsite* app in your Slack sidebar and tap your location\n\n"
        f"_The summary below will update as people check in._"
    )
    client.chat_postMessage(channel=SUMMARY_CHANNEL_ID, text=prompt)
    upsert_summary_message(client)  # post a fresh empty summary right below the prompt

def reset_scheduler(client):
    """Background thread: fires the reset once per day at RESET_HOUR:00."""
    fired_today = False
    while True:
        now = datetime.now()
        if now.hour == RESET_HOUR and now.minute == 0 and not fired_today:
            try:
                run_daily_reset(client)
                print(f"✅ Daily reset fired at {now.strftime('%H:%M')}")
            except Exception as e:
                print(f"⚠️ Reset failed: {e}")
            fired_today = True
        elif now.hour != RESET_HOUR:
            fired_today = False
        threading.Event().wait(30)  # check every 30 seconds

# ── Flask Dashboard ───────────────────────────────────────────────────────────

flask_app = Flask(__name__)

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Onsite Dashboard</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f0f2f5;
      padding: 28px 20px;
      color: #1a1a2e;
    }
    header { margin-bottom: 28px; }
    header h1 { font-size: 1.6rem; font-weight: 700; }
    header p  { color: #666; font-size: 0.9rem; margin-top: 4px; }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      gap: 20px;
    }
    .site-card {
      background: white;
      border-radius: 14px;
      padding: 20px;
      box-shadow: 0 2px 12px rgba(0,0,0,0.07);
    }
    .site-card h2 {
      font-size: 1rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: .05em;
      margin-bottom: 16px;
      padding-bottom: 10px;
      border-bottom: 2px solid #f0f2f5;
    }
    .site-card.ATL77  h2 { color: #1264a3; border-color: #1264a3; }
    .site-card.ATL88  h2 { color: #2eb886; border-color: #2eb886; }
    .site-card.ATL99  h2 { color: #e8912d; border-color: #e8912d; }
    .site-card.REMOTE h2 { color: #6e44ff; border-color: #6e44ff; }
    .site-card.OFF    h2 { color: #aaa;    border-color: #ddd; }
    .person {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 8px 0;
      border-bottom: 1px solid #f5f5f5;
    }
    .person:last-child { border-bottom: none; }
    .person img {
      width: 40px; height: 40px;
      border-radius: 50%;
      object-fit: cover;
    }
    .avatar-placeholder {
      width: 40px; height: 40px;
      border-radius: 50%;
      background: #dce3f0;
      display: flex; align-items: center; justify-content: center;
      font-weight: 700; color: #5a7abf; font-size: 1rem;
      flex-shrink: 0;
    }
    .person-info .name { font-weight: 600; font-size: 0.9rem; }
    .person-info .time { color: #999; font-size: 0.75rem; margin-top: 2px; }
    .empty { color: #bbb; font-size: 0.85rem; font-style: italic; }
  </style>
  <meta http-equiv="refresh" content="60">
</head>
<body>
  <header>
    <h1>📍 Onsite Dashboard</h1>
    <p>{{ date_str }} · auto-refreshes every 60s</p>
  </header>
  <div class="grid">
    {% for site, people in site_sections %}
    <div class="site-card {{ site }}">
      <h2>{{ emoji_map.get(site, '📍') }} {{ site }}</h2>
      {% if people %}
        {% for p in people %}
        <div class="person">
          {% if p.image_url %}
            <img src="{{ p.image_url }}" alt="{{ p.display_name }}">
          {% else %}
            <div class="avatar-placeholder">{{ p.display_name[0] }}</div>
          {% endif %}
          <div class="person-info">
            <div class="name">{{ p.display_name }}</div>
            <div class="time">{{ p.updated_at }}</div>
          </div>
        </div>
        {% endfor %}
      {% else %}
        <p class="empty">No one checked in</p>
      {% endif %}
    </div>
    {% endfor %}
  </div>
</body>
</html>
"""

@flask_app.route("/dashboard")
def dashboard():
    statuses = get_all_statuses()
    grouped = defaultdict(list)
    for row in statuses:
        grouped[row["site"]].append(row)

    preferred = ["ATL77", "ATL88", "ATL99", "REMOTE", "OFF"]
    site_sections = []
    for site in preferred:
        site_sections.append((site, sorted(grouped.get(site, []), key=lambda x: x["display_name"])))
    for site in sorted(s for s in grouped if s not in preferred):
        site_sections.append((site, sorted(grouped[site], key=lambda x: x["display_name"])))

    return render_template_string(
        DASHBOARD_HTML,
        site_sections=site_sections,
        date_str=datetime.now().strftime("%A, %B %d"),
        emoji_map=SITE_EMOJI,
    )

# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()

    # Flask dashboard in a background thread
    flask_thread = threading.Thread(
        target=lambda: flask_app.run(port=5000, debug=False, use_reloader=False),
        daemon=True,
    )
    flask_thread.start()
    print("✅ Dashboard running at http://localhost:5000/dashboard")

    # Daily reset scheduler in a background thread
    reset_thread = threading.Thread(
        target=lambda: reset_scheduler(slack_app.client),
        daemon=True,
    )
    reset_thread.start()
    print(f"✅ Daily reset scheduled for {RESET_HOUR}:00 AM")

    print("✅ Slack bot connecting via Socket Mode...")
    SocketModeHandler(slack_app, SLACK_APP_TOKEN).start()