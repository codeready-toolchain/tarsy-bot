# EP-0029: Slack Notification Integration

+**Status**: Phase 1 (Implemented) / Phase 2 (WIP)
**Created:** 2025-11-18

---

## Overview

Add a direct integration of Slack notifications for TARSy alert events, providing real-time visibility into alert analysis.

---

## Problem Statement

SRE teams need immediate visibility into alert analysis without constantly monitoring the TARSy dashboard or analyzing the alerts manually. Alerts and analysis failures should trigger notifications in team communication channels (Slack) for faster response times and better incident awareness.

---

## Key Architectural Decisions
1. **Dedicate Agent for Summary**
   - Separate `ExecutiveSummaryAgent` responsible only for generating concise executive summaries
   - **Benefits of this approach:**
     - **Timeline Clarity**: Summary generation appears as distinct LLM interaction in audit trail, making it easy to track when/how summaries are created
     - **Low Brittleness**: Independent failure handling - if summary generation fails, core analysis remains unaffected and session still completes successfully
     - **Configurability**: Summary generation can be conditionally enabled
2. **Optional by Design** 
   - Slack notifications can be enabled or disabled via environment configuration
3. **Integration at AlertService Layer**
   - Notifications triggered after chain completion (success/failure)
   - In case of success, uses AI-generated summary
   - Includes session link to dashboard for detailed investigation
4. **Single Responsibility**
   - `SlackService` handles only Slack communication
   - `AlertService` owns notification timing/logic
   - Clean separation of concerns

---

## Goals (Phase 1: Summary generation)

1. **Summary**: Concise 1-4 line summary of the final analysis


## Goals (Phase 2: Slack Integration)

1. **Real-time Notifications**: Send Slack messages when alerts analysis are processed (success or failure)
2. **Rich Context**: Include analysis summary, error details, and direct link to dashboard
3. **Message Formatting**: Use familiar alert formatting
4. **Optional Integration**: Allow disabling Slack without affecting core functionality

---

## Use Cases

### UC-1: Standard Slack Notification
**Actor**: SRE Engineer  
**Scenario**: Suspicious activity alert

1. TARSy receives an alert
2. TARSy processes alert
3. AI generates analysis and 1-4 line analysis summary
4. Slack notification sent to the Slack team channel

---

## Design

### Architecture

### High-Level Flow (Phase 1: Summary)

```text
┌─────────────────────────────────────────────────┐
│ 1. Session Completion                           │
│    Alert Processing → Final Analysis → Summary  │
└─────────────────────────────────────────────────┘
```

### High-Level Flow (Phase 2: Slack Integration)

```text
┌─────────────────────────────────────────────────┐
│ 1. External System (e.g. GuardDuty)             │
│    Posts alert to Slack channel                 │
└──────────────────┬──────────────────────────────┘
                   |
                   ▼
┌─────────────────────────────────────────────────┐
│ 2. Slack Channel (e.g. #guardydutty-alerts)     │
│    Finding in us-east-1 ....                    │
└──────────────────┬──────────────────────────────┘
                   |
                   | TARSy processes alert
                   ▼
┌─────────────────────────────────────────────────┐
│ 3. Session Completion                           │
│    Alert Processing → Final Analysis → Summary  │
└──────────────────┬──────────────────────────────┘
                   |
                   ▼
┌─────────────────────────────────────────────────┐
│ 4. Slack Service                                │
│    if slack_service.enabled:                    │
│     1. Send message with analysis summary       │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│ 5. Slack Channel (e.g. #guardydutty-alerts)     │
│    Analysis: The security alert is a false.     │
│ positive, triggered by ...                      │
│    View Analysis Details: http://localhost:...  │
└─────────────────────────────────────────────────┘
```

### UC-2: Slack Notification Threading
**Actor**: SRE Engineer  
**Scenario**: Suspicious activity alert

1. TARSy receives an alert
2. TARSy processes alert
3. AI generates analysis and 1-4 line analysis summary
4. Slack notification sent to the Slack team channel

---

## Design

### Architecture

### High-Level Flow (Phase 1: Summary)

```text
┌─────────────────────────────────────────────────┐
│ 1. Session Completion                           │
│    Alert Processing → Final Analysis → Summary  │
└─────────────────────────────────────────────────┘
```

### High-Level Flow (Phase 2: Slack Integration)

```text
┌─────────────────────────────────────────────────┐
│ 1. External System (e.g. GuardDuty)             │
│    Posts alert to Slack channel                 │
└──────────────────┬──────────────────────────────┘
                   |
                   ▼
┌─────────────────────────────────────────────────┐
│ 2. Slack Channel (e.g. #guardydutty-alerts)     │
│    Finding in us-east-1 ....                    │
└──────────────────┬──────────────────────────────┘
                   |
                   | TARSy processes alert
                   ▼
┌─────────────────────────────────────────────────┐
│ 3. Session Completion                           │
│    Alert Processing → Final Analysis → Summary  │
└──────────────────┬──────────────────────────────┘
                   |
                   ▼
┌─────────────────────────────────────────────────┐
│ 4. Slack Service                                │
│    if slack_service.enabled:                    │
│     1. Find target alert message by identifier  │
│     2. Reply in thread with analysis summary    │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│ 5. Slack Channel (e.g. #guardydutty-alerts)     │
│    Analysis: The security alert is a false.     │
│ positive, triggered by ...                      │
│    View Analysis Details: http://localhost:...  │
└─────────────────────────────────────────────────┘
```

---

## Implementation Plan

### Phase 1: Summary

Generate concise 1-4 line AI-powered summaries of alert analysis results for quick triage and external notifications.

#### 1. Database Schema Changes
- **Added**: `final_analysis_summary` field to `AlertSession` model (optional string)
- **Migration**: Created idempotent Alembic migration adding `final_analysis_summary` column
  - Column: `final_analysis_summary TEXT NULL`
  - Includes existence check to support test environments

#### 2. Executive Summary Agent Implementation
- **Create**: `backend/tarsy/integrations/notifications/summarizer.py`
  - `ExecutiveSummaryAgent` class with `generate_executive_summary()` method
  - Uses LLM (via `LLMManager`) to generate concise summaries
  - Configured with `max_tokens=150` to ensure brevity
  - Raises `ValueError` on empty content
  - Uses prompt builder for consistent prompting
  - Uses new interaction type: `LLMInteractionType.FINAL_ANALYSIS_SUMMARY`

#### 3. Prompt Engineering
- **Update**: `backend/tarsy/agents/prompts/builders.py`
  - Added `build_final_analysis_summary_prompt()` method
  - Prompts LLM to generate 1-4 line summaries optimized for Slack notifications
  - Emphasizes brevity and actionable information

#### 4. Alert Service Integration
- **Modify**: `backend/tarsy/services/alert_service.py`
  - Initialized `ExecutiveSummaryAgent` in `initialize()` method
  - Generates summary after analysis completion: `await self.final_analysis_summarizer.generate_executive_summary()`
  - Persists summary alongside final analysis in single atomic update
  - Avoids race conditions by bundling both fields in `_update_session_status()`

#### 5. History Service Updates
- **Modify**: `backend/tarsy/services/history_service.py`
  - Updated `update_session_status()` signature to accept `final_analysis_summary` parameter
  - Persists summary to database when provided

#### 6. Update Final Analysis Summary API Endpoint
- **Modify**: `GET /api/v1/history/sessions/{session_id}/final-analysis`
  - Include: `final_analysis_summary`

#### 7. Testing
- Update existing tests with necessary changes and address new ones


### Phase 2: Slack Integration

Create a Slack service that finds the target alert notification in a Slack channel and replies with TARSy's AI-generated analysis as a threaded response.

#### 1. Alert Correlation Strategy Research
  - Find the best way to locate the target alert message in Slack

#### 2. **Core Service**
  - Implement `SlackService` with API client initialization
  - Implement message search functionality
  - Implement threaded reply posting
  - Success notifications with summary
  - Failure notifications with error details
  - Session link to dashboard for detailed analysis
  - Add message formatting
  - Optional enablement

#### 3. **Integration**
  - Integrate with `AlertService` completion flow

#### 4. **Testing** 
  - Unit tests for `SlackService` methods
  - Integration tests with mocked Slack API
  - E2E tests

#### 5. **Documentation**
  - Update configuration guide
  - Document Slack app setup process
---

## Benefits

### Phase 1: Summary
- **Faster Triage**: 1-4 line summary enable quick alert assessment without reading full analysis

### Phase 2: Slack Integration
- **Real-Time Awareness**: Immediate notifications in team channels without direct dashboard access
- **Context Preservation**: Link to dashboard for full investigation details
- **Reduced Alert Fatigue**: Concise summary format prevents notification overload
- **Optional Integration**: No impact on teams not using Slack
---