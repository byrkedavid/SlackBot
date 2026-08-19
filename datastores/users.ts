import { DefineDatastore, Schema } from "deno-slack-sdk/mod.ts";

const Users = DefineDatastore({
  name: "onsite_users",
  primary_key: "user_id",
  attributes: {
    user_id: { type: Schema.slack.types.user_id },
    display_name: { type: Schema.types.string },
    image_url: { type: Schema.types.string },
    updated_at: { type: Schema.types.string },
  },
});
export default Users;
