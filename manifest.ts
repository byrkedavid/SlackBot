import { Manifest } from "deno-slack-sdk/mod.ts";
import CheckInWorkflow from "./workflows/check_in.ts";
import ResetDailyWorkflow from "./workflows/reset_daily.ts";
import DailyPromptWorkflow from "./workflows/daily_prompt.ts";
import CurrentCheckins from "./datastores/current_checkins.ts";
import CheckinHistory from "./datastores/checkin_history.ts";
import Users from "./datastores/users.ts";
import AppState from "./datastores/app_state.ts";

export default Manifest({
  name: "Onsite",
  description: "Slack-native onsite location check-ins with a live team Canvas.",
  outgoingDomains: [],
  workflows: [CheckInWorkflow, ResetDailyWorkflow, DailyPromptWorkflow],
  datastores: [CurrentCheckins, CheckinHistory, Users, AppState],
  botScopes: [
    "commands",
    "chat:write",
    "chat:write.public",
    "datastore:read",
    "datastore:write",
    "users:read",
    "canvases:write",
    "triggers:read",
    "triggers:write",
  ],
});
