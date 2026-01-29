# Slack Integration

TARSy can send automatic notifications to Slack when alert processing completes or fails. This feature is **disabled by default** and requires configuration to enable.

## Table of Contents
- [Overview](#overview)
- [How It Works](#how-it-works)
- [Setup Instructions](#setup-instructions)
- [Configuration](#configuration)
- [Slack Notification Threading](#slack-notification-threading)
- [How to test locally](#how-to-test-locally)

## Overview

When configured, TARSy automatically:
- Sends Slack messages to the target Slack channel
- Includes analysis summary with link to detailed dashboard view
- Reports errors when alert processing fails

You can also enable Slack Notification Threading by setting the Slack message fingerprint, and TARSy will correlate the message with the target message via fingerprint.


**Default State**: Slack integration is **disabled by default**. TARSy will process alerts normally without sending any Slack notifications until you configure it.

## How It Works

### Standard Slack Message Notification

1. **Alert arrives**
2. **TARSy processes** the alert
3. **After processing**, TARSy posts a Slack message to the target channel with:
   - Analysis summary or error message
   - Link to full analysis in dashboard (`<dashboard-url>/sessions/<session-id>`)

### Threaded Slack Message Notification
1. **Alert arrives** with a Slack message fingerprint (unique identifier)
2. **TARSy processes** the alert
3. **After processing**, TARSy searches the Slack channel history (last 24 hours) for the message with the fingerprint
4. **Finds target message**, posts a threaded reply with:
   - Analysis summary or error message
   - Link to full analysis in dashboard (`<dashboard-url>/sessions/<session-id>`)

## Setup Instructions

### Step 1: Create a Slack App

1. Go to the Slack Apps page: [Slack Apps](https://api.slack.com/apps)
2. Create your Slack app

### Step 2: Configure Bot Permissions

In your app's **OAuth & Permissions** page, under **Bot Token Scopes**, add these scopes:

| Scope | Purpose |
|-------|---------|
| `channels:history` | Read messages in public channels (to find original alerts) |
| `groups:history` | Read messages in private channels |
| `chat:write` | Post messages and replies |
| `channels:read` | View basic channel info |
| `groups:read` | View basic private channel info |


### Step 3: Install App to Workspace

1. Under OAuth Tokens, click **"Install to Workspace"** (or **"Reinstall App"** if updating scopes)
2. Authorize the app
3. **Copy the Bot User OAuth Token** (starts with `xoxb-`)

### Step 4: Invite Bot to Channel

In your Slack channel, invite your bot: /invite @your-bot-name


### Step 5: Get Channel ID

Right-click on your channel → **"View channel details"** → Copy the Channel ID (e.g., `C12345678`)

Or find it in the channel URL: `https://your-workspace.slack.com/archives/C12345678`


## Configuration

Edit `backend/.env` and add your Slack credentials:

```
# =============================================================================
# Slack Notification Configuration
# =============================================================================

# Slack Bot token (starts with xoxb-)
SLACK_BOT_TOKEN=xoxb-your-token-here

# Slack channel ID (e.g., C12345678 or channel-name)
SLACK_CHANNEL=C12345678
```

You should also add your Dashboard URL in CORS_ORIGIN setting:

```
# =============================================================================
# CORS Configuration
# =============================================================================
# Allowed origins for CORS (comma-separated list)
# For development, include your alert dev UI URL
# For production, use your actual domain
CORS_ORIGINS=<your-dashboard-url>
```

## Slack Notification Threading
If you want to enable Slack notification threading, you need to provide the `slack_message_fingerprint`, when sending the request to TARSy. Be aware that the target message that you want TARSy to reply to should contain the same fingerprint.


## How to test locally

### Standard Slack Message Notification

1. Follow the [Setup Instructions](#setup-instructions)
2. Follow the [Configuration](#configuration)
3. Deploy TARSy
4. Manual Alert Submission in TARSy Dashboard
5. Check the TARSy report in the Slack channel


### Threaded Slack Message Notification

1. Follow the [Setup Instructions](#setup-instructions)
2. Follow the [Configuration](#configuration)
3. Deploy TARSy
4. Post a message containing a fingerprint to your Slack Channel. TARSy will search the last 24 hours of channel history to find a message with that fingerprint and reply to it.

For example:
```bash
curl -k -X POST https://slack.api.slack.com/api/chat.postMessage \
  -H "Authorization: Bearer <slack-app-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "channel": "'"<slack-channel>"'",
    "text": "Fingerprint: 121212\nMessage: Namespace 'test' terminating"
  }'
```

5. Manual Alert Submission in TARSy Dashboard. Do not forget to include the fingerprint
<img width="1625" height="420" alt="image" src="https://github.com/user-attachments/assets/b8b77435-ae82-4236-b551-7a16cfcb7bd1" />

6. Check the TARSy report in the Slack message thread