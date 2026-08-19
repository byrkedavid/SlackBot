import { SlackFunction } from "deno-slack-sdk/mod.ts";
import { ResetDailyFunction } from "./definition.ts";
import CurrentCheckins from "../../datastores/current_checkins.ts";
import { queryAll, upsertTeamViews } from "../../lib/team_view.ts";

export default SlackFunction(ResetDailyFunction, async ({ inputs, client }) => {
  const rows = await queryAll(client, CurrentCheckins.name);
  for (const row of rows) {
    const deleted = await client.apps.datastore.delete({
      datastore: CurrentCheckins.name,
      id: row.user_id,
    });
    if (!deleted.ok) return { error: deleted.error || `Could not clear ${row.user_id}` };
  }

  try {
    await upsertTeamViews(client, inputs.channel_id);
    return { outputs: {} };
  } catch (error) {
    return { error: error instanceof Error ? error.message : String(error) };
  }
});
