import { Trigger } from "deno-slack-sdk/types.ts";
import { TriggerContextData, TriggerTypes } from "deno-slack-api/mod.ts";
import CheckInWorkflow from "../workflows/check_in.ts";

const CheckInTrigger: Trigger<typeof CheckInWorkflow.definition> = {
  type: TriggerTypes.Shortcut,
  name: "Update my onsite location",
  description: "Open the onsite location picker and refresh the living summary.",
  workflow: `#/workflows/${CheckInWorkflow.definition.callback_id}`,
  inputs: {
    interactivity: { value: TriggerContextData.Shortcut.interactivity },
    channel_id: { value: TriggerContextData.Shortcut.channel_id },
    user_id: { value: TriggerContextData.Shortcut.user_id },
  },
};

export default CheckInTrigger;
