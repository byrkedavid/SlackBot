import { DefineWorkflow, Schema } from "deno-slack-sdk/mod.ts";
import { RecordCheckinFunction } from "../functions/record_checkin/definition.ts";

const CheckInWorkflow = DefineWorkflow({
  callback_id: "onsite_check_in",
  title: "Update my onsite location",
  description: "Choose where you are working today and update the team view.",
  input_parameters: {
    properties: {
      interactivity: { type: Schema.slack.types.interactivity },
      channel_id: { type: Schema.slack.types.channel_id },
      user_id: { type: Schema.slack.types.user_id },
    },
    required: ["interactivity", "channel_id", "user_id"],
  },
});

const form = CheckInWorkflow.addStep(Schema.slack.functions.OpenForm, {
  title: "Where are you today?",
  interactivity: CheckInWorkflow.inputs.interactivity,
  submit_label: "Update location",
  fields: {
    elements: [{
      name: "site", title: "Location", type: Schema.types.string,
      enum: ["ATL55", "ATL66", "ATL77", "ATL88", "ATL99", "ATL118", "REMOTE", "OFF"],
      choices: [
        { value: "ATL55", title: "🏢 ATL55" }, { value: "ATL66", title: "🏢 ATL66" },
        { value: "ATL77", title: "🏢 ATL77" }, { value: "ATL88", title: "🏢 ATL88" },
        { value: "ATL99", title: "🏢 ATL99" }, { value: "ATL118", title: "🏢 ATL118" },
        { value: "REMOTE", title: "🏠 Remote" }, { value: "OFF", title: "🏖️ Off" },
      ],
    }],
    required: ["site"],
  },
});
CheckInWorkflow.addStep(RecordCheckinFunction, {
  user_id: CheckInWorkflow.inputs.user_id,
  channel_id: CheckInWorkflow.inputs.channel_id,
  site: form.outputs.fields.site,
});
export default CheckInWorkflow;
