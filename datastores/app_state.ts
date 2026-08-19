import { DefineDatastore, Schema } from "deno-slack-sdk/mod.ts";

const AppState = DefineDatastore({
  name: "app_state",
  primary_key: "key",
  attributes: {
    key: { type: Schema.types.string },
    value: { type: Schema.types.string },
  },
});
export default AppState;
