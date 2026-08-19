import { DefineFunction, Schema } from "deno-slack-sdk/mod.ts";

export const RecordCheckinFunction = DefineFunction({
  callback_id: "record_onsite_checkin",
  title: "Record onsite check-in",
  description: "Stores a user's location and refreshes the live team Canvas.",
  source_file: "functions/record_checkin/handler.ts",
  input_parameters: {
    properties: {
      user_id: { type: Schema.slack.types.user_id },
      channel_id: { type: Schema.slack.types.channel_id },
      site: { type: Schema.types.string },
    },
    required: ["user_id", "channel_id", "site"],
  },
  output_parameters: {
    properties: { canvas_id: { type: Schema.types.string } },
    required: ["canvas_id"],
  },
});
