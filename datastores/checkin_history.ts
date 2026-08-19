import { DefineDatastore, Schema } from "deno-slack-sdk/mod.ts";

const CheckinHistory = DefineDatastore({
  name: "checkin_history",
  primary_key: "id",
  attributes: {
    id: { type: Schema.types.string },
    user_id: { type: Schema.slack.types.user_id },
    display_name: { type: Schema.types.string },
    work_date: { type: Schema.types.string },
    site: { type: Schema.types.string },
    checked_in_at: { type: Schema.types.string },
  },
});

export default CheckinHistory;
