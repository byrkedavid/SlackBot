import { DefineDatastore, Schema } from "deno-slack-sdk/mod.ts";

const CurrentCheckins = DefineDatastore({
  name: "current_checkins",
  primary_key: "user_id",
  attributes: {
    user_id: { type: Schema.slack.types.user_id },
    display_name: { type: Schema.types.string },
    work_date: { type: Schema.types.string },
    site: { type: Schema.types.string },
    updated_at: { type: Schema.types.string },
  },
});
export default CurrentCheckins;
