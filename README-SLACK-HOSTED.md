# Slack-hosted Onsite migration

This branch starts from `codex/slack-native-onsite` and moves the core runtime to Slack's Deno platform while keeping the cleaned-up behavior as the reference.

## Included now

- Native Slack check-in form for ATL55/66/77/88/99/118, Remote, and Off.
- Slack datastores instead of local SQLite for users, current status, history, and summary state.
- One living channel summary updated in place after every check-in.
- Full team visibility in that summary: users are grouped by current location, and tracked users without a location today appear under **No location set today**.
- Historical check-in records remain stored for the upcoming history workflow.

## Intentionally not brought back

The cleaned branch had already removed the Flask dashboard, static website, schedule/expected-user system, and custom daily scheduler. This hosted implementation keeps those removed.

## Run locally

1. Install Deno and the Slack CLI.
2. Authenticate the CLI with your permitted Slack workspace.
3. From this branch run `slack run`.
4. Create the development shortcut with `slack trigger create --trigger-def triggers/check_in.ts`.
5. Paste the generated shortcut into the onsite channel or add it as a channel bookmark.
6. Test check-ins from multiple Slack users and confirm the living summary updates in place.

## Deploy

After development validation:

1. Run `slack deploy`.
2. Create the production trigger again with `slack trigger create --trigger-def triggers/check_in.ts` against the deployed app.
3. Replace the development shortcut/bookmark with the production one.

## Next migration pieces

The legacy cleaned branch still serves as the reference for `/onsite-history` and admin check-in/reset. Those should be migrated only after this core flow compiles in the target AWS Slack workspace so we do not expose an admin workflow without confirmed access-control configuration.
