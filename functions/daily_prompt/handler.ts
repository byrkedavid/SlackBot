import { SlackFunction } from "deno-slack-sdk/mod.ts";
import { DailyPromptFunction } from "./definition.ts";
import AppState from "../../datastores/app_state.ts";

export default SlackFunction(DailyPromptFunction, async ({ inputs, client }) => {
  const shortcutKey = `checkin_shortcut_url:${inputs.channel_id}`;
  const shortcutState = await client.apps.datastore.get({
    datastore: AppState.name,
    id: shortcutKey,
  });
  const shortcutUrl = shortcutState.ok && shortcutState.item?.value
    ? shortcutState.item.value
    : undefined;

  if (!shortcutUrl) {
    return { error: "Check-in workflow link has not been initialized for this channel yet." };
  }

  const post = await client.chat.postMessage({
    channel: inputs.channel_id,
    text: "✅ Builder Thread — update your onsite location for today.",
    blocks: [
      {
        type: "section",
        text: {
          type: "mrkdwn",
          text: "✅ *Builder Thread*\nUpdate your location/site when you are onsite.\nCheck your emails.\nCheck your PPE.\nHydrate and Be Safe.",
        },
      },
      {
        type: "actions",
        elements: [
          {
            type: "workflow_button",
            text: { type: "plain_text", text: "📍 Update Onsite Location", emoji: true },
            action_id: "daily_onsite_checkin",
            style: "primary",
            workflow: {
              trigger: {
                url: shortcutUrl,
                customizable_input_parameters: [
                  { name: "channel_id", value: inputs.channel_id },
                ],
              },
            },
          },
        ],
      },
    ],
  });

  if (!post.ok) return { error: post.error || "Could not post daily onsite prompt" };
  return { outputs: {} };
});
