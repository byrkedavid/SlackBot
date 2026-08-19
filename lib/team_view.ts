import AppState from "../datastores/app_state.ts";
import CurrentCheckins from "../datastores/current_checkins.ts";
import { friendlyDate, localDate, SITE_EMOJI, SITES } from "./constants.ts";

export async function queryAll(client: any, datastore: string) {
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

function buildTeamView(checkins: any[]) {
  const today = localDate();
  const todays = checkins.filter((row) => row.work_date === today);
  const grouped = new Map<string, any[]>();
  for (const site of SITES) grouped.set(site, []);
  for (const row of todays) {
    if (!grouped.has(row.site)) grouped.set(row.site, []);
    grouped.get(row.site)!.push(row);
  }
  for (const rows of grouped.values()) rows.sort((a, b) => String(a.display_name).localeCompare(String(b.display_name)));

  let total = 0;
  const blocks: any[] = [
    { type: "header", text: { type: "plain_text", text: `📍 Onsite — ${friendlyDate()}`, emoji: true } },
    { type: "divider" },
  ];
  const markdown: string[] = [`# 📍 Onsite — ${friendlyDate()}`, ""];

  for (const [site, rows] of grouped.entries()) {
    if (!rows.length) continue;
    total += rows.length;
    blocks.push({
      type: "section",
      text: { type: "mrkdwn", text: `${SITE_EMOJI[site] || "📍"} *${site}  |  ${rows.length} checked in*\n${rows.map((r) => `• <@${r.user_id}>`).join("\n")}` },
    });
    markdown.push(`## ${SITE_EMOJI[site] || "📍"} ${site} · ${rows.length} checked in`);
    markdown.push(...rows.map((r) => `- <@${r.user_id}>`), "");
  }

  if (!total) {
    blocks.push({ type: "section", text: { type: "mrkdwn", text: "_No one has checked in yet today._" } });
    markdown.push("_No one has checked in yet today._", "");
  }

  blocks.push(
    { type: "divider" },
    { type: "context", elements: [{ type: "mrkdwn", text: `${total} checked in today · resets automatically at midnight ET` }] },
  );
  markdown.push("---", `${total} checked in today · resets automatically at midnight ET`);

  return {
    total,
    text: `Onsite team view for ${friendlyDate()}: ${total} checked in.`,
    blocks,
    markdown: markdown.join("\n"),
  };
}

export async function upsertTeamViews(client: any, channelId: string) {
  const checkins = await queryAll(client, CurrentCheckins.name);
  const view = buildTeamView(checkins);

  // Keep one living channel message as a lightweight fallback.
  const summaryKey = `summary:${channelId}`;
  const summaryState = await client.apps.datastore.get({ datastore: AppState.name, id: summaryKey });
  let summaryTs = summaryState.ok && summaryState.item?.value ? summaryState.item.value : undefined;
  if (summaryTs) {
    const update = await client.chat.update({ channel: channelId, ts: summaryTs, text: view.text, blocks: view.blocks });
    if (!update.ok) summaryTs = undefined;
  }
  if (!summaryTs) {
    const post = await client.chat.postMessage({ channel: channelId, text: view.text, blocks: view.blocks });
    if (!post.ok || !post.ts) throw new Error(post.error || "Could not post onsite summary");
    summaryTs = post.ts;
    const save = await client.apps.datastore.put({ datastore: AppState.name, item: { key: summaryKey, value: summaryTs } });
    if (!save.ok) throw new Error(save.error || "Could not save summary timestamp");
  }

  // Create a dedicated Onsite Canvas tab the first time this channel is used,
  // then replace its entire content on every check-in/reset.
  const canvasKey = `canvas:${channelId}`;
  const canvasState = await client.apps.datastore.get({ datastore: AppState.name, id: canvasKey });
  let canvasId = canvasState.ok && canvasState.item?.value ? canvasState.item.value : undefined;

  if (canvasId) {
    const edit = await client.canvases.edit({
      canvas_id: canvasId,
      changes: [{
        operation: "replace",
        document_content: { type: "markdown", markdown: view.markdown },
      }],
    });
    if (!edit.ok) canvasId = undefined;
  }

  if (!canvasId) {
    const create = await client.canvases.create({
      title: "Onsite",
      channel_id: channelId,
      document_content: { type: "markdown", markdown: view.markdown },
    });
    if (!create.ok || !create.canvas_id) throw new Error(create.error || "Could not create Onsite canvas tab");
    canvasId = create.canvas_id;
    const save = await client.apps.datastore.put({ datastore: AppState.name, item: { key: canvasKey, value: canvasId } });
    if (!save.ok) throw new Error(save.error || "Could not save canvas ID");
  }

  return { summaryTs: summaryTs as string, canvasId: canvasId as string };
}
