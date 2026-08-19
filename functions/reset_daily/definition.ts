import { DefineFunction, Schema } from "deno-slack-sdk/mod.ts";

export const ResetDailyFunction = DefineFunction({
  callback_id: "reset_daily_onsite",
  title: "Reset daily onsite locations",
  description: "Clears current onsite locations and refreshes the team views.",
  source_file: "functions/reset_daily/handler.ts",
  input_parameters: {
    properties: {
      channel_id: { type: Schema.slack.types.channel_id },
    },
    required: ["channel_id"],
  },
  output_parameters: { properties: {}, required: [] },
});
