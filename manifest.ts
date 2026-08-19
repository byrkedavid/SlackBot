import { Manifest } from "deno-slack-sdk/mod.ts";
import CheckInWorkflow from "./workflows/check_in.ts";
import CurrentCheckins from "./datastores/current_checkins.ts";
import CheckinHistory from "./datastores/checkin_history.ts";
import Users from "./datastores/users.ts";
import AppState from "./datastores/app_state.ts";

export default Manifest({
  name: "Onsite",
  description: "Slack-native onsite location check-ins and a living team view.",
  outgoingDomains: [],
  workflows: [CheckInWorkflow],
  datastores: [CurrentCheckins, CheckinHistory, Users, AppState],
  botScopes: ["commands", "chat:write", "chat:write.public", "datastore:read", "datastore:write", "users:read"],
});
