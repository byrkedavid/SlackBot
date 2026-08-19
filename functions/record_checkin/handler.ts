import { SlackFunction } from "deno-slack-sdk/mod.ts";
import { TriggerContextData, TriggerTypes } from "deno-slack-api/mod.ts";
import { RecordCheckinFunction } from "./definition.ts";
import CurrentCheckins from "../../datastores/current_checkins.ts";
import CheckinHistory from "../../datastores/checkin_history.ts";
import Users from "../../datastores/users.ts";
import AppState from "../../datastores/app_state.ts";
import { isPocSlackUsername, localDate, SITES } from "../../lib/constants.ts";
import { upsertTeamCanvas } from "../../lib/team_view.ts";

function nextEasternTimeIso(hour: number) {
  const now = new Date();
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/New_York",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    hourCycle: "h23",
  }).formatToParts(now);
  const values = Object.fromEntries(parts.map((p) => [p.type, p.value]));

  const localHour = Number(values.hour);
  const base = new Date(`${values.year}-${values.month}-${values.day}T12:00:00Z`);
  if (localHour >= hour) base.setUTCDate(base.getUTCDate() + 1);

  const targetParts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/New_York",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(base);
  const target = Object.fromEntries(targetParts.map((p) => [p.type, p.value]));

  const offsetParts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    timeZoneName: "longOffset",
  }).formatToParts(base);
  const zoneName = offsetParts.find((p) => p.type === "timeZoneName")?.value || "GMT-04:00";
  const offset = zoneName.replace("GMT", "");
  return `${target.year}-${target.month}-${target.day}T${String(hour).padStart(2, "0")}:00:00${offset}`;
}

async function getState(client: any, key: string) {
  const resp = await client.apps.datastore.get({ datastore: AppState.name, id: key });
  return resp.ok && resp.item?.value ? resp.item.value as string : undefined;
}

async function saveState(client: any, key: string, value: string) {
  const resp = await client.apps.datastore.put({
    datastore: AppState.name,
    item: { key, value },
  });
  if (!resp.ok) throw new Error(resp.error || `Could not save ${key}`);
}

async function deleteState(client: any, key: string) {
  await client.apps.datastore.delete({ datastore: AppState.name, id: key });
}

async function triggerStillExists(client: any, triggerId?: string) {
  if (!triggerId) return false;
  const resp = await client.workflows.triggers.permissions.list({ trigger_id: triggerId });
  if (resp.ok) return true;
  if (resp.error === "trigger_not_found") return false;
  throw new Error(resp.error || `Could not verify trigger ${triggerId}`);
}

async function ensureCheckinShortcut(client: any, channelId: string) {
  const urlKey = `checkin_shortcut_url:${channelId}`;
  const idKey = `checkin_shortcut_id:${channelId}`;
  const existingUrl = await getState(client, urlKey);
  const existingId = await getState(client, idKey);

  if (existingUrl && await triggerStillExists(client, existingId)) return existingUrl;
  if (existingUrl) await deleteState(client, urlKey);
  if (existingId) await deleteState(client, idKey);

  const created = await client.workflows.triggers.create({
    type: TriggerTypes.Shortcut,
    name: `Update onsite location ${channelId}`,
    description: "Update your onsite location from the daily Builder Thread.",
    workflow: "#/workflows/onsite_check_in",
    shortcut: { button_text: "Update Onsite Location" },
    inputs: {
      interactivity: { value: TriggerContextData.Shortcut.interactivity },
      user_id: { value: TriggerContextData.Shortcut.user_id },
      channel_id: { customizable: true },
    },
  });

  const shortcutUrl = created.trigger?.shortcut_url;
  const triggerId = created.trigger?.id;
  if (!created.ok || !shortcutUrl || !triggerId) {
    throw new Error(created.error || "Could not create channel check-in shortcut");
  }

  await saveState(client, urlKey, shortcutUrl);
  await saveState(client, idKey, triggerId);
  return shortcutUrl;
}

async function ensureDailyPromptTrigger(client: any, channelId: string) {
  const key = `daily_prompt_trigger:${channelId}`;
  const existingId = await getState(client, key);
  if (await triggerStillExists(client, existingId)) return;
  if (existingId) await deleteState(client, key);

  const created = await client.workflows.triggers.create({
    type: TriggerTypes.Scheduled,
    name: `Daily Builder Thread ${channelId}`,
    description: "Post the onsite Builder Thread every morning at 6 AM Eastern.",
    workflow: "#/workflows/onsite_daily_prompt",
    inputs: { channel_id: { value: channelId } },
    schedule: {
      start_time: nextEasternTimeIso(6),
      timezone: "America/New_York",
      frequency: { type: "daily", repeats_every: 1 },
    },
  });

  const triggerId = created.trigger?.id;
  if (!created.ok || !triggerId) {
    throw new Error(created.error || "Could not create daily Builder Thread trigger");
  }
  await saveState(client, key, triggerId);
}

async function ensureMidnightResetTrigger(client: any, channelId: string) {
  const key = `reset_trigger:${channelId}`;
  const existingId = await getState(client, key);
  if (await triggerStillExists(client, existingId)) return;
  if (existingId) await deleteState(client, key);

  const created = await client.workflows.triggers.create({
    type: TriggerTypes.Scheduled,
    name: `Onsite midnight reset ${channelId}`,
    description: "Clear current onsite locations at midnight Eastern Time.",
    workflow: "#/workflows/onsite_midnight_reset",
    inputs: { channel_id: { value: channelId } },
    schedule: {
      start_time: nextEasternTimeIso(0),
      timezone: "America/New_York",
      frequency: { type: "daily", repeats_every: 1 },
    },
  });

  const triggerId = created.trigger?.id;
  if (!created.ok || !triggerId) {
    throw new Error(created.error || "Could not create midnight reset trigger");
  }
  await saveState(client, key, triggerId);
}

export default SlackFunction(RecordCheckinFunction, async ({ inputs, client }) => {
  if (!SITES.includes(inputs.site as typeof SITES[number])) {
    return { error: `Invalid site: ${inputs.site}` };
  }

  const profileResp = await client.users.info({ user: inputs.user_id });
  if (!profileResp.ok || !profileResp.user) {
    return { error: profileResp.error || "Could not load Slack user" };
  }

  const profile = profileResp.user.profile || {};
  const displayName = profile.display_name || profile.real_name || profileResp.user.real_name || inputs.user_id;
  const slackUsername = String(profileResp.user.name || "").toLowerCase();
  const isPoc = isPocSlackUsername(slackUsername);
  const imageUrl = profile.image_72 || profile.image_48 || "";
  const now = new Date().toISOString();
  const workDate = localDate();

  const saves = await Promise.all([
    client.apps.datastore.put({
      datastore: Users.name,
      item: {
        user_id: inputs.user_id,
        display_name: displayName,
        slack_username: slackUsername,
        is_poc: isPoc,
        image_url: imageUrl,
        updated_at: now,
      },
    }),
    client.apps.datastore.put({
      datastore: CurrentCheckins.name,
      item: {
        user_id: inputs.user_id,
        display_name: displayName,
        slack_username: slackUsername,
        is_poc: isPoc,
        work_date: workDate,
        site: inputs.site,
        updated_at: now,
      },
    }),
    client.apps.datastore.put({
      datastore: CheckinHistory.name,
      item: {
        id: crypto.randomUUID(),
        user_id: inputs.user_id,
        display_name: displayName,
        work_date: workDate,
        site: inputs.site,
        checked_in_at: now,
      },
    }),
  ]);

  const failed = saves.find((r) => !r.ok);
  if (failed) return { error: failed.error || "Could not save check-in" };

  try {
    await ensureCheckinShortcut(client, inputs.channel_id);
    await ensureDailyPromptTrigger(client, inputs.channel_id);
    await ensureMidnightResetTrigger(client, inputs.channel_id);
    const canvasId = await upsertTeamCanvas(client, inputs.channel_id);
    return { outputs: { canvas_id: canvasId } };
  } catch (error) {
    return { error: error instanceof Error ? error.message : String(error) };
  }
});
