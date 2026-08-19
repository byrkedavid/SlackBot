import { SlackFunction } from "deno-slack-sdk/mod.ts";
import { RecordCheckinFunction } from "./definition.ts";
import CurrentCheckins from "../../datastores/current_checkins.ts";
import CheckinHistory from "../../datastores/checkin_history.ts";
import Users from "../../datastores/users.ts";
import AppState from "../../datastores/app_state.ts";
import { friendlyDate, localDate, SITE_EMOJI, SITES } from "../../lib/constants.ts";

async function queryAll(client: any, datastore: string) {
  const items: any[] = [];
  let cursor: string | undefined;
  do {
    const resp = await client.apps.datastore.query({
      datastore,
      limit: 100,
      ...(cursor ? { cursor } : {}),
    });
    if (!resp.ok) throw new Error(resp.error || `Failed to query ${datastore}`);
    items.push(...(resp.items || []));
    cursor = resp.response_metadata?.next_cursor || undefined;
  } while (cursor);
  return items;
}

async function buildAndUpsertSummary(client: any, channelId: string) {
  const today = localDate();
  const [checkins, users] = await Promise.all([
    queryAll(client, CurrentCheckins.name),
    queryAll(client, Users.name),
  ]);

  const todays = checkins.filter((row) => row.work_date === today);
  const bySite = new Map<string, any[]>();
  for (const site of SITES) bySite.set(site, []);
  for (const row of todays) {
    if (!bySite.has(row.site)) bySite.set(row.site, []);
    bySite.get(row.site)!.push(row);
  }
  for (const rows of bySite.values()) {
    rows.sort((a, b) => String(a.display_name).localeCompare(String(b.display_name)));
  }

  const checkedIds = new Set(todays.map((row) => row.user_id));
  const notCheckedIn = users
    .filter((u) => !checkedIds.has(u.user_id))
    .sort((a, b) => String(a.display_name).localeCompare(String(b.display_name)));

  const blocks: any[] = [
    {
      type: "header",
      text: { type: "plain_text", text: `📍 Onsite — ${friendlyDate()}`, emoji: true },
    },
    { type: "divider" },
  ];

  let total = 0;
  for (const [site, rows] of bySite.entries()) {
    if (!rows.length) continue;
    total += rows.length;
    blocks.push({
      type: "section",
      text: {
        type: "mrkdwn",
        text: `${SITE_EMOJI[site] || "📍"} *${site} — ${rows.length}*\n${rows.map((r) => `<@${r.user_id}>`).join(", ")}`,
      },
    });
  }

  if (total === 0) {
    blocks.push({
      type: "section",
      text: { type: "mrkdwn", text: "_No one has checked in yet._" },
    });
  }

  if (notCheckedIn.length) {
    blocks.push(
      { type: "divider" },
      {
        type: "section",
        text: {
          type: "mrkdwn",
          text: `⏳ *Tracked users not checked in — ${notCheckedIn.length}*\n${notCheckedIn.map((u) => `<@${u.user_id}>`).join(", ")}`,
        },
      },
    );
  }

  blocks.push(
    { type: "divider" },
    {
      type: "context",
      elements: [{ type: "mrkdwn", text: `${total} checked in · ${users.length} tracked users · updates automatically` }],
    },
  );

  const text = `Onsite summary for ${friendlyDate()}: ${total} checked in.`;
  const stateKey = `summary:${channelId}`;
  const stateResp = await client.apps.datastore.get({ datastore: AppState.name, id: stateKey });
  let summaryTs = stateResp.ok && stateResp.item?.value ? stateResp.item.value : undefined;

  if (summaryTs) {
    const update = await client.chat.update({ channel: channelId, ts: summaryTs, text, blocks });
    if (!update.ok) summaryTs = undefined;
  }

  if (!summaryTs) {
    const post = await client.chat.postMessage({ channel: channelId, text, blocks });
    if (!post.ok || !post.ts) throw new Error(post.error || "Could not post onsite summary");
    summaryTs = post.ts;
    const save = await client.apps.datastore.put({
      datastore: AppState.name,
      item: { key: stateKey, value: summaryTs },
    });
    if (!save.ok) throw new Error(save.error || "Could not save summary timestamp");
  }

  return summaryTs;
}

export default SlackFunction(
  RecordCheckinFunction,
  async ({ inputs, client }) => {
    if (!SITES.includes(inputs.site as typeof SITES[number])) {
      return { error: `Invalid site: ${inputs.site}` };
    }

    const profileResp = await client.users.info({ user: inputs.user_id });
    if (!profileResp.ok || !profileResp.user) {
      return { error: profileResp.error || "Could not load Slack user" };
    }

    const profile = profileResp.user.profile || {};
    const displayName = profile.display_name || profile.real_name || profileResp.user.real_name || inputs.user_id;
    const imageUrl = profile.image_72 || profile.image_48 || "";
    const now = new Date().toISOString();
    const workDate = localDate();

    const userSave = await client.apps.datastore.put({
      datastore: Users.name,
      item: {
        user_id: inputs.user_id,
        display_name: displayName,
        image_url: imageUrl,
        schedule_type: "",
        updated_at: now,
      },
    });
    if (!userSave.ok) return { error: userSave.error || "Could not save user" };

    const currentSave = await client.apps.datastore.put({
      datastore: CurrentCheckins.name,
      item: {
        user_id: inputs.user_id,
        display_name: displayName,
        work_date: workDate,
        site: inputs.site,
        updated_at: now,
      },
    });
    if (!currentSave.ok) return { error: currentSave.error || "Could not save check-in" };

    const historySave = await client.apps.datastore.put({
      datastore: CheckinHistory.name,
      item: {
        id: crypto.randomUUID(),
        user_id: inputs.user_id,
        display_name: displayName,
        work_date: workDate,
        site: inputs.site,
        checked_in_at: now,
      },
    });
    if (!historySave.ok) return { error: historySave.error || "Could not save check-in history" };

    try {
      const summaryTs = await buildAndUpsertSummary(client, inputs.channel_id);
      return { outputs: { summary_ts: summaryTs } };
    } catch (error) {
      return { error: error instanceof Error ? error.message : String(error) };
    }
  },
);
