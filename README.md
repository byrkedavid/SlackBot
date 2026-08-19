# Onsite Slack Bot — Slack-hosted rewrite

This branch replaces the Python/Flask/SQLite runtime with a Slack-hosted Deno/TypeScript workflow app.

## What users get

- A Slack shortcut/button called **Update my onsite location**.
- A Slack form with the existing locations: ATL55, ATL66, ATL77, ATL88, ATL99, ATL118, Remote, and Off.
- One living summary message in the channel where the shortcut is used.
- The summary groups checked-in users by location and also shows tracked users who have not checked in today.
- Every check-in is retained in the Slack-hosted `checkin_history` datastore.

The summary message is the replacement for the old web dashboard. Everyone in the channel can see where the tracked users are without leaving Slack.

## Architecture

```text
Slack shortcut / bookmark
        ↓
OpenForm location picker
        ↓
record_checkin custom function
        ↓
Slack datastores
  - users
  - current_checkins
  - checkin_history
  - app_state
        ↓
chat.update / chat.postMessage
        ↓
Living onsite summary in Slack
```

There is no Flask server, Socket Mode process, SQLite database, Vercel service, or machine that must stay running for this version.

## Requirements

- A paid Slack workspace (Slack workflow apps require a paid plan).
- Permission in the AWS Slack workspace to install/deploy a custom Slack workflow app.
- Slack CLI installed and authenticated.
- Deno available locally for development/validation.

## Deploy

1. Check out this branch:

```bash
git checkout agent/slack-hosted-rewrite
```

2. Authenticate the Slack CLI if needed:

```bash
slack auth login
```

3. Validate/run the development version:

```bash
slack run
```

4. Create the check-in link trigger:

```bash
slack trigger create --trigger-def triggers/check_in.ts
```

Slack will print a Shortcut URL. Add that URL as a bookmark in your onsite channel or paste it into the channel. Slack will render it as a workflow launch control that opens the location form.

5. Test a few check-ins. The first submission creates the living summary in that channel. Later submissions edit the same summary message instead of posting new copies.

6. Deploy to Slack hosting:

```bash
slack deploy
```

7. Create the production trigger again after deployment:

```bash
slack trigger create --trigger-def triggers/check_in.ts
```

Local and deployed apps have separate triggers, so use the production Shortcut URL in the real channel.

## Current behavior

A summary looks roughly like:

```text
📍 Onsite — Wednesday, August 19, 2026

🏢 ATL77 — 3
@David, @Mike, @Chris

🏢 ATL88 — 2
@Alex, @Ryan

🏠 REMOTE — 1
@Sarah

⏳ Tracked users not checked in — 2
@John, @Matt

6 checked in · 8 tracked users · updates automatically
```

A user becomes a tracked user the first time they submit a location. That avoids trying to list every person in a large corporate Slack workspace.

## Changing sites

Edit `lib/constants.ts` and the matching choices in `workflows/check_in.ts`.

## Legacy Python files

The original Python files remain on this migration branch for reference while the Slack-hosted version is validated. They are not used by the Deno Slack app. Once the Slack-hosted deployment is confirmed in the AWS workspace, they can be removed in a cleanup commit.

## Important AWS note

Deployment still depends on your AWS Slack workspace's app-management policy. If custom workflow apps require admin approval, the manifest/scopes will need to be approved before the app can be installed for internal use.
