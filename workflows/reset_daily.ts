import { DefineWorkflow, Schema } from "deno-slack-sdk/mod.ts";
import { ResetDailyFunction } from "../functions/reset_daily/definition.ts";

const ResetDailyWorkflow = DefineWorkflow({
  callback_id: "onsite_midnight_reset",
  title: "Reset onsite locations",
  description: "Clears daily onsite locations at midnight and refreshes the team view.",
  input_parameters: {
    properties: {
      channel_id: { type: Schema.slack.types.channel_id },
    },
    required: ["channel_id"],
  },
});

ResetDailyWorkflow.addStep(ResetDailyFunction, {
  channel_id: ResetDailyWorkflow.inputs.channel_id,
});

export default ResetDailyWorkflow;
