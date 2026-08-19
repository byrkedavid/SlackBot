import { SlackFunction } from "deno-slack-sdk/mod.ts";
import { TriggerTypes } from "deno-slack-api/mod.ts";
import { RecordCheckinFunction } from "./definition.ts";
import CurrentCheckins from "../../datastores/current_checkins.ts";
import CheckinHistory from "../../datastores/checkin_history.ts";
import Users from "../../datastores/users.ts";
import AppState from "../../datastores/app_state.ts";
import { localDate, SITES } from "../../lib/constants.ts";
import { upsertTeamViews } from "../../lib/team_view.ts";

function nextEasternMidnightIso() {
  const now = new Date();
  const dateParts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/New_York",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const values = Object.fromEntries(dateParts.map((p) => [p.type, p.value]));
  const noonUtc = new Date(`${values.year}-${values.month}-${values.day}T12:00:00Z`);
  noonUtc.setUTCDate(noonUtc.getUTCDate() + 1);
  const nextParts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/New_York",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(noonUtc);
  const next = Object.fromEntries(nextParts.map((p) => [p.type, p.value]));

  const offsetParts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    timeZoneName: "longOffset",
  }).formatToParts(now);
  const zoneName = offsetParts.find((p) => p.type === "timeZoneName")?.value || "GMT-04:00";
  const offset = zoneName.replace("GMT", "");
  return `${next.year}-${next.month}-${next.day}T00:00:00${offset}`;
}

async function ensureMidnightResetTrigger(client: any, channelId: string) {
  const key = `reset_trigger:${channelId}`;
  const existing = await client.apps.datastore.get({ datastore: AppState.name, id: key });
  if (existing.ok && existing.item?.value) return;

  const created = await client.workflows.triggers.create({
    type: TriggerTypes.Scheduled,
    name: `Onsite midnight reset ${channelId}`,
    description: "Clear today's onsite locations at midnight Eastern Time.",
    workflow: "#/workflows/onsite_midnight_reset",
    inputs: {
      channel_id: { value: channelId },
    },
    schedule: {
      start_time: nextEasternMidnightIso(),
      timezone: "America/New_York",
      frequency: { type: "daily", repeats_every: 1 },
    },
  });

  const triggerId = created.trigger?.id;
  if (!created.ok || !triggerId) throw new Error(created.error || "Could not create midnight reset trigger");
  const save = await client.apps.datastore.put({ datastore: AppState.name, item: { key, value: triggerId } });
  if (!save.ok) throw new Error(save.error || "Could not save reset trigger ID");
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
    await ensureMidnightResetTrigger(client, inputs.channel_id);
    const { summaryTs } = await upsertTeamViews(client, inputs.channel_id);
    return { outputs: { summary_ts: summaryTs } };
  } catch (error) {
    return { error: error instanceof Error ? error.message : String(error) };
  }
});
