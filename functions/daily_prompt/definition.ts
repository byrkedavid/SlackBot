import { DefineFunction, Schema } from "deno-slack-sdk/mod.ts";

export const DailyPromptFunction = DefineFunction({
  callback_id: "post_daily_onsite_prompt",
  title: "Post daily onsite prompt",
  description: "Posts the daily Builder Thread check-in message with a workflow button.",
  source_file: "functions/daily_prompt/handler.ts",
  input_parameters: {
    properties: {
      channel_id: { type: Schema.slack.types.channel_id },
    },
    required: ["channel_id"],
  },
  output_parameters: {
    properties: {},
    required: [],
  },
});
