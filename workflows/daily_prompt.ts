import { DefineWorkflow, Schema } from "deno-slack-sdk/mod.ts";
import { DailyPromptFunction } from "../functions/daily_prompt/definition.ts";

const DailyPromptWorkflow = DefineWorkflow({
  callback_id: "onsite_daily_prompt",
  title: "Daily onsite check-in prompt",
  description: "Posts the daily Builder Thread check-in message at 6 AM Eastern.",
  input_parameters: {
    properties: {
      channel_id: { type: Schema.slack.types.channel_id },
    },
    required: ["channel_id"],
  },
});

DailyPromptWorkflow.addStep(DailyPromptFunction, {
  channel_id: DailyPromptWorkflow.inputs.channel_id,
});

export default DailyPromptWorkflow;
