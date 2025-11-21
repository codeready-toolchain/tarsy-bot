# EP-0029: Slack Notification Integration

**Status**: Implemented
**Created:** 2025-11-18

---

## Overview

As a temporary solution (while pending Cockpit implementation), add a direct integration of Slack notifications for TARSy alert events, providing real-time visibility into alert analysis.

---

## Problem Statement

SRE teams need immediate visibility into alert analysis without constantly monitoring the TARSy dashboard or analyzing the alerts manually. Alerts and analysis failures should trigger notifications in team communication channels (Slack) for faster response times and better incident awareness.

---

## Key Architectural Decisions
1. **Webhook-Based Integration**
   - Uses Slack Incoming Webhooks
2. **Optional by Design** 
   - Auto-disables when `SLACK_WEBHOOK_URL` is empty
3. **Integration at AlertService Layer**
   - Notifications triggered after chain completion (success/failure)
   - In case of success, uses AI-generated resume
   - Includes session link to dashboard for detailed investigation
4. **Single Responsibility**
   - `SlackService` handles only Slack communication
   - `AlertService` owns notification timing/logic
   - Clean separation of concerns

---

## Goals (Phase 1: Resume generation)

1. **Resume**: Concise 1-2 line resume of the analysis


## Goals (Phase 2: Slack Integration)

1. **Real-time Notifications**: Send Slack messages when alerts analysis are processed (success or failure)
2. **Rich Context**: Include analysis resume, error details, and direct link to dashboard
3. **Message Formatting**: Use familiar alert formatting
4. **Optional Integration**: Allow disabling Slack without affecting core functionality

---

## Use Cases

### UC-1: Alert Notification
**Actor**: SRE Engineer  
**Scenario**: Suspicious activity alert

1. TARSy receives an alert
2. TARSy processes alert
3. AI generates analysis and 1-2 line resume
4. Slack notification sent to the Slack team channel

---

## Design

### Architecture

### High-Level Flow (Phase 1: Resume)

```
┌─────────────────────────────────────────────────┐
│ 1. Session Completion                           │
│    Alert Processing → Final Analysis → Resume   │
└─────────────────────────────────────────────────┘
```

### High-Level Flow (Phase 2: Slack Integration)

```
┌─────────────────────────────────────────────────┐
│ 1. Session Completion                           │
│    Alert Processing → Final Analysis → Resume   │
└──────────────────┬──────────────────────────────┘
                   |
                   ▼
┌─────────────────────────────────────────────────┐
│ 4. Slack Notification (Slack Service)           │
│    if slack_service.enabled:                    │
│      • Format message                           │
│      • Include analysis/error + session link    │  
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│ 5. Slack Channel                                │
│    🚒 Firing:                                   │
│    - Alert: kubernetes                          │
│    Severity: warning                            │
│    Environment: production                      │
│    Cluster: rm1                                 │
│    Analysis: The security alert is a false.     │
│ positive, triggered by ...                      │
│    View Analysis Details: http://localhost:...  │
└─────────────────────────────────────────────────┘
```

---

## Implementation Plan

### Phase 1: Resume

Added AI-generated resume (1-2 line summary) to `ChainExecutionResult` and on phase 2 integrate it into Slack notifications. This provides concise alert summary in Slack channel instead of verbose full analysis text.

**Possible Changes**:
- Add `resume` field to `ChainExecutionResult`
- Modified `AlertService` to extract resume from agent execution results


### Phase 2: Slack Integration

Integrate Slack webhook notifications to send alert result analysis to the Slack team channel.

**Planned Features**:
- `Slack Service` with webhook-based notifications
-  Message formatting
-  Success notifications with resume
-  Failure notifications with error details
-  Session link to dashboard for detailed analysis
-  Optional enablement


---

## Benefits

### Phase 1: Resume
- **Faster Triage**: 1-2 line resume enable quick alert assessment without reading full analysis

### Phase 2: Slack Integration
- **Real-Time Awareness**: Immediate notifications in team channels without direct dashboard access
- **Context Preservation**: Link to dashboard for full investigation details
- **Reduced Alert Fatigue**: Concise resume format prevents notification overload
- **Optional Integration**: No impact on teams not using Slack
---