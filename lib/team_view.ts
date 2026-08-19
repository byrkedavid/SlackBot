import AppState from "../datastores/app_state.ts";
import CurrentCheckins from "../datastores/current_checkins.ts";
import Users from "../datastores/users.ts";
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

function buildTeamView(checkins: any[], users: any[]) {
  const today = localDate();
  const todays = checkins.filter((row) => row.work_date === today);
  const grouped = new Map<string, any[]>();
  for (const site of SITES) grouped.set(site, []);
  for (const row of todays) {
    if (!grouped.has(row.site)) grouped.set(row.site, []);
    grouped.get(row.site)!.push(row);
  }
  for (const rows of grouped.values()) {
    rows.sort((a, b) => String(a.display_name).localeCompare(String(b.display_name)));
  }

  const checked = new Set(todays.map((row) => row.user_id));
  const unset = users
    .filter((u) => !checked.has(u.user_id))
    .sort((a, b) => String(a.display_name).localeCompare(String(b.display_name)));

  const markdown: string[] = [
    `# 📍 Onsite — ${friendlyDate()}`,
    "",
    `${todays.length} checked in · ${users.length} tracked users`,
    "",
    "---",
    "",
  ];

  let total = 0;
  for (const [site, rows] of grouped.entries()) {
    if (!rows.length) continue;
    total += rows.length;
    markdown.push(`## ${SITE_EMOJI[site] || "📍"} ${site} · ${rows.length}`);
    markdown.push(...rows.map((r) => `- ![](@${r.user_id})`), "");
  }

  if (!total) {
    markdown.push("_No one has checked in yet today._", "");
  }

  if (unset.length) {
    markdown.push(`## ❓ No location set today · ${unset.length}`);
    markdown.push(...unset.map((u) => `- ![](@${u.user_id})`), "");
  }

  markdown.push("---", "_Updates automatically · daily locations reset at midnight ET._");
  return markdown.join("\n");
}

export async function upsertTeamCanvas(client: any, channelId: string) {
  const [checkins, users] = await Promise.all([
    queryAll(client, CurrentCheckins.name),
    queryAll(client, Users.name),
  ]);
  const markdown = buildTeamView(checkins, users);

  const canvasKey = `canvas:${channelId}`;
  const canvasState = await client.apps.datastore.get({ datastore: AppState.name, id: canvasKey });
  let canvasId = canvasState.ok && canvasState.item?.value ? canvasState.item.value : undefined;

  if (canvasId) {
    const edit = await client.canvases.edit({
      canvas_id: canvasId,
      changes: [{
        operation: "replace",
        document_content: { type: "markdown", markdown },
      }],
    });
    if (!edit.ok) canvasId = undefined;
  }

  if (!canvasId) {
    const create = await client.canvases.create({
      title: "Onsite",
      channel_id: channelId,
      document_content: { type: "markdown", markdown },
    });
    if (!create.ok || !create.canvas_id) {
      throw new Error(create.error || "Could not create Onsite canvas tab");
    }
    canvasId = create.canvas_id;
    const save = await client.apps.datastore.put({
      datastore: AppState.name,
      item: { key: canvasKey, value: canvasId },
    });
    if (!save.ok) throw new Error(save.error || "Could not save canvas ID");
  }

  return canvasId as string;
}
