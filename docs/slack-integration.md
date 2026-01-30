# Slack Integration

TARSy can send automatic notifications to Slack when alert processing completes, fails, or pauses. This feature is **disabled by default** and requires configuration to enable.

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
- Notifies when alert processing starts (for Slack-originated alerts only)
- Includes analysis summary with link to detailed dashboard view
- Reports errors when alert processing fails
- Notifies when alert processing pauses (hit max iterations)

You can also enable Slack Notification Threading by setting the Slack message fingerprint, and TARSy will correlate the message with the target message via fingerprint.


**Default State**: Slack integration is **disabled by default**. TARSy will process alerts normally without sending any Slack notifications until you configure it.

## How It Works

### Standard Slack Message Notification

1. **Alert arrives**
2. **TARSy processes** the alert
3. **After processing**, TARSy posts a Slack message to the target channel with:
   - Analysis summary (success - green color)
   - Error message (failure - red color)
   - Pause message (paused - yellow color)
   - Link to full analysis in dashboard (`<dashboard-url>/sessions/<session-id>`)

**Note**: Start notifications are NOT sent for standard (non-threaded) alerts to avoid unnecessary noise.

### Threaded Slack Message Notification
1. **Alert arrives** with a Slack message fingerprint (unique identifier)
2. **TARSy starts processing** and immediately sends a start notification to the thread
3. **TARSy processes** the alert
4. **After processing**, TARSy searches the Slack channel history (last 24 hours) for the message with the fingerprint
5. **Finds target message**, posts a threaded reply with:
   - Analysis summary, error message, or pause notification
   - Link to full analysis in dashboard (`<dashboard-url>/sessions/<session-id>`)

**Note**: Start notifications are ONLY sent for alerts with a Slack message fingerprint (Slack-originated alerts). This provides immediate feedback in the original Slack thread that processing has begun.

## Setup Instructions

### Step 1: Create a Slack App

1. Go to the Slack Apps page: [Slack Apps](https://api.slack.com/apps)
2. Create your Slack app

### Step 2: Configure Bot Permissions

In your app's **OAuth & Permissions** page, under **Bot Token Scopes**, add these scopes:

| Scope | Purpose |
| ------- | --------- |
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

If you want to enable Slack notification threading, you need to provide the `slack_message_fingerprint` when sending the request to TARSy.

### Fingerprint Requirements

The fingerprint matching is **flexible and forgiving**:

- **Case-insensitive**: `"Fingerprint: 123"`, `"fingerprint: 123"`, and `"FINGERPRINT: 123"` all match
- **Whitespace-normalized**: Extra spaces, newlines, and tabs are ignored
- **Position-independent**: The fingerprint can appear anywhere in the message text or attachments

**Examples of valid fingerprint placements in Slack messages:**

```
# Beginning of message
Fingerprint: alert-123
Alert: Pod CrashLooping in namespace prod

# Middle of message  
Alert: High CPU usage
Fingerprint: alert-456
Environment: production

# End of message (with or without newline)
Alert: Database connection timeout
Environment: staging
Fingerprint: alert-789
```

**All these variations will match `"fingerprint: alert-123"`:**
- `"Fingerprint: alert-123"` ✓
- `"fingerprint: alert-123"` ✓
- `"FINGERPRINT: alert-123"` ✓
- `"Fingerprint:    alert-123"` (extra spaces) ✓
- `"Fingerprint: alert-123\n"` (with newline) ✓

### How TARSy Finds Your Message

1. Searches the last **24 hours** of channel history (up to 50 messages)
2. Checks message text and all attachment fields (`text` and `fallback`)
3. Uses case-insensitive matching with whitespace normalization
4. Returns the first message that contains the fingerprint


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

#### Example: Post a message with fingerprint

```bash
curl -k -X POST https://slack.api.slack.com/api/chat.postMessage \
  -H "Authorization: Bearer <slack-app-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "channel": "'"<slack-channel>"'",
    "text": "Fingerprint: 121212\nMessage: Namespace test terminating"
  }'
```

**Note**: The fingerprint format is flexible - case and whitespace don't matter. All these work:
- `"Fingerprint: 121212"`
- `"fingerprint: 121212"`  
- `"FINGERPRINT:121212"`

5. Manual Alert Submission in TARSy Dashboard. Include the same fingerprint value (case-insensitive):
<img width="1625" height="420" alt="image" src="https://github.com/user-attachments/assets/b8b77435-ae82-4236-b551-7a16cfcb7bd1" />

6. Check the TARSy report in the Slack message thread

### Start Notifications

When an alert with a Slack message fingerprint arrives (Slack-originated alert):
1. TARSy immediately sends a start notification to the Slack thread with a green color
2. The message includes:
   - Start indicator (🔄) showing processing has begun
   - Message: "Processing alert started. This may take a few minutes..."
   - Link to session details for real-time monitoring

**Key behaviors:**
- **Only sent for Slack-originated alerts** (those with a `slack_message_fingerprint`)
- **Not sent for standard alerts** (submitted via API/dashboard without a fingerprint)
- Provides immediate feedback in the Slack thread
- Allows users to track the processing lifecycle: START → (PAUSE if needed) → COMPLETE/FAIL

### Pause Notifications

When a session reaches its maximum iteration limit and pauses:
1. TARSy sends a pause notification to Slack with a yellow (warning) color
2. The message includes:
   - Pause reason (e.g., "Stage paused after 10 iterations")
   - Instructions to resume via the dashboard
   - Link to session details for resuming
3. After resuming the session and it completes or fails, a final notification is sent