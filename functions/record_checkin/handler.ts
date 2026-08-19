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
    const resp = await client.apps.datastore.query({ datastore, limit: 100, ...(cursor ? { cursor } : {}) });
    if (!resp.ok) throw new Error(resp.error || `Failed to query ${datastore}`);
    items.push(...(resp.items || []));
    cursor = resp.next_cursor || undefined;
  } while (cursor);
  return items;
}

async function upsertSummary(client: any, channelId: string) {
  const today = localDate();
  const [checkins, users] = await Promise.all([
    queryAll(client, CurrentCheckins.name),
    queryAll(client, Users.name),
  ]);
  const todays = checkins.filter((row) => row.work_date === today);
  const grouped = new Map<string, any[]>();
  for (const site of SITES) grouped.set(site, []);
  for (const row of todays) {
    if (!grouped.has(row.site)) grouped.set(row.site, []);
    grouped.get(row.site)!.push(row);
  }
  for (const rows of grouped.values()) rows.sort((a, b) => String(a.display_name).localeCompare(String(b.display_name)));

  const checked = new Set(todays.map((row) => row.user_id));
  const unset = users.filter((u) => !checked.has(u.user_id)).sort((a, b) => String(a.display_name).localeCompare(String(b.display_name)));
  const blocks: any[] = [
    { type: "header", text: { type: "plain_text", text: `📍 Onsite — ${friendlyDate()}`, emoji: true } },
    { type: "divider" },
  ];

  let total = 0;
  for (const [site, rows] of grouped.entries()) {
    if (!rows.length) continue;
    total += rows.length;
    blocks.push({
      type: "section",
      text: { type: "mrkdwn", text: `${SITE_EMOJI[site] || "📍"} *${site}  |  ${rows.length} checked in*\n${rows.map((r) => `• <@${r.user_id}>`).join("\n")}` },
    });
  }
  if (!total) blocks.push({ type: "section", text: { type: "mrkdwn", text: "_No one has checked in yet._" } });
  if (unset.length) {
    blocks.push(
      { type: "divider" },
      { type: "section", text: { type: "mrkdwn", text: `❓ *No location set today  |  ${unset.length}*\n${unset.map((u) => `• <@${u.user_id}>`).join("\n")}` } },
    );
  }
  blocks.push(
    { type: "divider" },
    { type: "context", elements: [{ type: "mrkdwn", text: `${total} checked in · ${users.length} tracked users · updates automatically` }] },
  );

  const text = `Onsite team view for ${friendlyDate()}: ${total} checked in.`;
  const stateKey = `summary:${channelId}`;
  const state = await client.apps.datastore.get({ datastore: AppState.name, id: stateKey });
  let ts = state.ok && state.item?.value ? state.item.value : undefined;
  if (ts) {
    const update = await client.chat.update({ channel: channelId, ts, text, blocks });
    if (!update.ok) ts = undefined;
  }
  if (!ts) {
    const post = await client.chat.postMessage({ channel: channelId, text, blocks });
    if (!post.ok || !post.ts) throw new Error(post.error || "Could not post onsite summary");
    ts = post.ts;
    const save = await client.apps.datastore.put({ datastore: AppState.name, item: { key: stateKey, value: ts } });
    if (!save.ok) throw new Error(save.error || "Could not save summary timestamp");
  }
  return ts as string;
}

export default SlackFunction(RecordCheckinFunction, async ({ inputs, client }) => {
  if (!SITES.includes(inputs.site as typeof SITES[number])) return { error: `Invalid site: ${inputs.site}` };
  const profileResp = await client.users.info({ user: inputs.user_id });
  if (!profileResp.ok || !profileResp.user) return { error: profileResp.error || "Could not load Slack user" };
  const profile = profileResp.user.profile || {};
  const displayName = profile.display_name || profile.real_name || profileResp.user.real_name || inputs.user_id;
  const imageUrl = profile.image_72 || profile.image_48 || "";
  const now = new Date().toISOString();
  const workDate = localDate();

  const saves = await Promise.all([
    client.apps.datastore.put({ datastore: Users.name, item: { user_id: inputs.user_id, display_name: displayName, image_url: imageUrl, updated_at: now } }),
    client.apps.datastore.put({ datastore: CurrentCheckins.name, item: { user_id: inputs.user_id, display_name: displayName, work_date: workDate, site: inputs.site, updated_at: now } }),
    client.apps.datastore.put({ datastore: CheckinHistory.name, item: { id: crypto.randomUUID(), user_id: inputs.user_id, display_name: displayName, work_date: workDate, site: inputs.site, checked_in_at: now } }),
  ]);
  const failed = saves.find((r) => !r.ok);
  if (failed) return { error: failed.error || "Could not save check-in" };
  try {
    const summaryTs = await upsertSummary(client, inputs.channel_id);
    return { outputs: { summary_ts: summaryTs } };
  } catch (error) {
    return { error: error instanceof Error ? error.message : String(error) };
  }
});
