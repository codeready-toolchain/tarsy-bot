# EP-0009: LLM Token Usage Tracking - Design Document

## Overview
Add exact token usage tracking to existing LLM interactions using LangChain's `UsageMetadataCallbackHandler` for universal provider support.

## Current State
- LLM client exists in `/backend/tarsy/integrations/llm/client.py`
- Uses conversation-based approach returning `LLMConversation` objects directly
- `LLMInteraction` model exists in `/backend/tarsy/models/unified_interactions.py` but has **no token usage fields**
- Current `LLMInteraction` stores complete `conversation` using `PydanticJSONType` custom SQLAlchemy type
- No token usage tracking implemented yet

## Implementation Approach
**Method**: `UsageMetadataCallbackHandler` - works across all providers (OpenAI, Gemini, Grok)

No fallback methods - if provider doesn't support token usage, the field remains `None`.

## Code Changes Required

### 1. Update Models

**Required Changes - LLMInteraction Model - Add Token Usage Fields:**
```python
# Add these fields to the existing LLMInteraction model:
class LLMInteraction(SQLModel, table=True):
    # ... existing fields above ...
    
    # NEW: Add separate type-safe token fields  
    input_tokens: Optional[int] = Field(None, description="Input/prompt tokens")
    output_tokens: Optional[int] = Field(None, description="Output/completion tokens")  
    total_tokens: Optional[int] = Field(None, description="Total tokens used")

```

### 2. LLMClient._execute_with_retry() Method

**Required Changes - Add Usage Metadata Capture:**
```python
# Update method signature to return usage metadata  
async def _execute_with_retry(
    self, 
    langchain_messages: List, 
    max_retries: int = 3
) -> Tuple[Any, Optional[UsageMetadata]]:
    """Execute LLM call with usage tracking and retry logic."""
    
    for attempt in range(max_retries + 1):
        try:
            # Add callback handler to capture token usage
            callback = UsageMetadataCallbackHandler()
            response = await self.llm_client.ainvoke(
                langchain_messages, 
                config={"callbacks": [callback]}
            )
            
            # ... existing empty response validation logic ...
            
            # Return both response and usage metadata
            return response, callback.usage_metadata
            
        except Exception as e:
            # ... existing retry logic ...
```

### 3. LLMClient.generate_response() Method

**Required Changes - Add Token Usage Capture:**
```python
...
# Add these imports to /backend/tarsy/integrations/llm/client.py
from langchain_core.callbacks import UsageMetadataCallbackHandler
from langchain_core.messages import UsageMetadata
from typing import Optional, Tuple
...

# Update to capture and store token usage
async def generate_response(
    self, 
    conversation: LLMConversation, 
    session_id: str, 
    stage_execution_id: Optional[str] = None
) -> LLMConversation:
    
    async with llm_interaction_context(session_id, request_data, stage_execution_id) as ctx:
        
        langchain_messages = self._convert_conversation_to_langchain(conversation)
        
        # Get both response and usage metadata
        response, usage_metadata = await self._execute_with_retry(langchain_messages)
        
        # Store token usage in dedicated type-safe fields on interaction
        if usage_metadata:
            ctx.interaction.input_tokens = usage_metadata.input_tokens
            ctx.interaction.output_tokens = usage_metadata.output_tokens
            ctx.interaction.total_tokens = usage_metadata.total_tokens
        
        conversation.append_assistant_message(response.content)
        
        # Store complete conversation and token data
        ctx.interaction.conversation = conversation
        ctx.interaction.provider = self.provider_name
        ctx.interaction.model_name = self.model
        
        return conversation  # Token data stored on interaction, not returned
```

## Data Flow
1. LLM conversation processed through `generate_response()` method
2. LLM call made with `UsageMetadataCallbackHandler` attached via `_execute_with_retry()`
3. Callback captures token usage from provider
4. Usage data stored in separate type-safe fields on `LLMInteraction` 
5. Complete conversation stored alongside token data in database
6. Updated `LLMConversation` returned to caller (token data accessible via interaction record)
7. Token data automatically included in timeline events via history service

**Accessing Usage Data:**
```python
# From LLMInteraction database record - fully type-safe
interaction = get_llm_interaction(interaction_id)
total_tokens = interaction.total_tokens     # Optional[int]
input_tokens = interaction.input_tokens     # Optional[int]
output_tokens = interaction.output_tokens   # Optional[int]

# Easy database queries for high token usage
sessions_with_high_usage = session.query(LLMInteraction).filter(
    LLMInteraction.total_tokens > 1000
).all()
```

## Implementation Files

**Primary Changes:**
- `/backend/tarsy/integrations/llm/client.py` - Main LLM client changes (add `UsageMetadataCallbackHandler`)
- `/backend/tarsy/models/unified_interactions.py` - Add three token fields to `LLMInteraction` model

**Aggregation Changes (Backend Models):**
- `/backend/tarsy/models/history_models.py` - Add computed fields for stage-level token aggregation to `DetailedStage`
- `/backend/tarsy/models/history_models.py` - Add session-level token fields to `SessionStats` model
- `/backend/tarsy/services/history_service.py` - Update `get_session_summary()` to calculate session token totals

**Frontend Changes:**
- `/dashboard/src/types/index.ts` - Add token aggregation fields to TypeScript interfaces
- Various dashboard components - Update to display stage and session token totals

**Database Changes:**
- Database schema migration only - add three optional integer columns (`input_tokens`, `output_tokens`, `total_tokens`)
- No data migration needed - existing interactions will have `NULL` token values
- No columns to remove - `token_usage` field never existed in current schema

**Testing Updates:**
- Test token usage capture for all 4 providers (OpenAI, Google, XAI/Grok, Anthropic)
- Test token aggregation calculations at stage and session levels
- Test graceful degradation when usage data unavailable  
- Verify existing functionality unchanged
- Test dashboard display of token data at all levels
- Some test files may need minor updates to handle new token fields

**Additional Changes Needed for Token Aggregation:**

Following the existing codebase pattern for aggregations, we need:

### Stage-Level Token Aggregation (Backend Models)
Add computed fields to `DetailedStage` model in `/backend/tarsy/models/history_models.py`:

```python
# Add to DetailedStage class:
@computed_field
@property  
def stage_input_tokens(self) -> Optional[int]:
    """Sum of input tokens from all LLM interactions in this stage"""
    total = sum(
        interaction.details.input_tokens or 0 
        for interaction in self.llm_interactions 
        if interaction.details.input_tokens
    )
    return total if total > 0 else None

@computed_field
@property
def stage_output_tokens(self) -> Optional[int]:
    """Sum of output tokens from all LLM interactions in this stage"""
    total = sum(
        interaction.details.output_tokens or 0 
        for interaction in self.llm_interactions 
        if interaction.details.output_tokens
    )
    return total if total > 0 else None

@computed_field
@property
def stage_total_tokens(self) -> Optional[int]:
    """Sum of total tokens from all LLM interactions in this stage"""
    total = sum(
        interaction.details.total_tokens or 0 
        for interaction in self.llm_interactions 
        if interaction.details.total_tokens
    )
    return total if total > 0 else None
```

### Session-Level Token Aggregation (Backend Models)
Add fields to `SessionStats` model in `/backend/tarsy/models/history_models.py`:

```python
# Add to SessionStats class:
class SessionStats(BaseModel):
    # ... existing fields ...
    
    # NEW: Token usage aggregations
    session_input_tokens: int = 0
    session_output_tokens: int = 0  
    session_total_tokens: int = 0
```

And update the calculation in `HistoryService.get_session_summary()`:

```python
# Calculate token usage aggregations from all stages
session_input_tokens = 0
session_output_tokens = 0
session_total_tokens = 0

# Get detailed stages to calculate token sums
detailed_session = repo.get_session_details(session_id) 
if detailed_session:
    for stage in detailed_session.stages:
        if stage.stage_input_tokens:
            session_input_tokens += stage.stage_input_tokens
        if stage.stage_output_tokens: 
            session_output_tokens += stage.stage_output_tokens
        if stage.stage_total_tokens:
            session_total_tokens += stage.stage_total_tokens

session_stats = SessionStats(
    # ... existing fields ...
    session_input_tokens=session_input_tokens,
    session_output_tokens=session_output_tokens,
    session_total_tokens=session_total_tokens,
)
```

### Frontend TypeScript Types
Update `/dashboard/src/types/index.ts` to include token aggregation fields:

```typescript
// Add to Session interface:
export interface Session {
  // ... existing fields ...
  
  // NEW: Session-level token aggregations
  session_input_tokens?: number;
  session_output_tokens?: number;  
  session_total_tokens?: number;
}

// Add to StageExecution interface:
export interface StageExecution {
  // ... existing fields ...
  
  // NEW: Stage-level token aggregations  
  stage_input_tokens?: number;
  stage_output_tokens?: number;
  stage_total_tokens?: number;
}
```

### Frontend Token Display (Dashboard Components)
Update dashboard components to display the pre-calculated token data:

- **Debug tab**: Show per-interaction tokens (already partially implemented)
- **Stage cards**: Show stage token sums from `stage.stage_total_tokens` 
- **Session header**: Show session token sums from `sessionStats.session_total_tokens`
- **Session list**: Include session token totals

### Benefits of Backend Aggregation Approach:
- **Consistent**: Same calculations regardless of UI component
- **Efficient**: Database-level aggregations, no duplicate frontend calculations
- **Automatic**: Hook system propagates updates to dashboard
- **API Available**: Token aggregations accessible via existing API endpoints
- **Follows Patterns**: Matches existing duration and count aggregations

## Database Migration
- **Schema only**: Add `input_tokens`, `output_tokens`, `total_tokens` as nullable INTEGER columns
- **No data migration needed**: Old interactions will have `NULL` values (which map to `None` in Python)
- **Backward compatible**: Existing code unaffected by new optional fields

## API Surface Changes

### Timeline Event Details Structure
Token usage will be automatically included in timeline event details for LLM interactions:

```python
# Current LLMTimelineEvent structure
{
  "id": "abc123",
  "event_id": "abc123",
  "type": "llm", 
  "timestamp_us": 1703001234567890,
  "step_description": "LLM analysis using gpt-4-1106-preview",
  "duration_ms": 2340,
  "stage_execution_id": "stage_789",
  "details": {
    # Complete LLMInteraction object as details:
    "interaction_id": "abc123",
    "session_id": "session_456",
    "stage_execution_id": "stage_789",
    "timestamp_us": 1703001234567890,
    "duration_ms": 2340,
    "success": true,
    "error_message": null,
    "model_name": "gpt-4-1106-preview",
    "provider": "openai",
    "temperature": 0.7,
    "conversation": {
      "messages": [
        {"role": "system", "content": "You are an AI assistant..."},
        {"role": "user", "content": "Analyze this alert..."},
        {"role": "assistant", "content": "Based on the alert data..."}
      ]
    },
    # NEW: Token usage fields added to LLMInteraction model
    "input_tokens": 120,
    "output_tokens": 45,
    "total_tokens": 165
  }
}
```

### Stage-Level Token Aggregations
Stage executions will include computed token sums from all LLM interactions:

```python
# DetailedStage structure with token aggregations
{
  "execution_id": "stage_789",
  "stage_name": "Initial Analysis", 
  "status": "completed",
  # ... existing stage fields ...
  
  # NEW: Computed token aggregations from all LLM interactions in stage
  "stage_input_tokens": 450,   # Sum of input tokens from all stage LLM interactions
  "stage_output_tokens": 180,  # Sum of output tokens from all stage LLM interactions  
  "stage_total_tokens": 630,   # Sum of total tokens from all stage LLM interactions
  
  # Individual interactions still available with their own token data
  "llm_interactions": [
    {
      "details": {
        "input_tokens": 120,
        "output_tokens": 45,
        "total_tokens": 165
      }
    },
    # ... more interactions
  ]
}
```

### Session-Level Token Aggregations
Session statistics and overviews will include token totals across all stages:

```python
# SessionStats structure with session-wide token aggregations  
{
  "session_id": "session_456",
  "total_interactions": 12,
  "llm_interactions": 8,
  # ... existing session stats ...
  
  # NEW: Session-wide token aggregations from all stages
  "session_input_tokens": 2100,   # Sum from all stage_input_tokens
  "session_output_tokens": 890,   # Sum from all stage_output_tokens
  "session_total_tokens": 2990    # Sum from all stage_total_tokens  
}
```

### Where Token Data Appears

**Individual Interaction Tokens:**
- **Timeline events** - Individual LLM interaction token data (`interaction.total_tokens`)
- **WebSocket updates** - Real-time interaction token data

**Stage-Level Aggregated Tokens:**
- **`/api/v1/history/sessions/{session_id}`** - Stage token sums in `DetailedStage` objects
- **Dashboard stage cards** - Display aggregated stage token usage
- **WebSocket stage updates** - Real-time stage token aggregations

**Session-Level Aggregated Tokens:**
- **`/api/v1/history/sessions`** - Session list with token totals per session
- **`/api/v1/history/sessions/{session_id}/summary`** - Session statistics with token aggregations
- **Dashboard session header** - Display session-wide token usage
- **WebSocket session updates** - Real-time session token totals

### Access Patterns

**Individual Interaction Token Data:**
```javascript
// From timeline events - individual LLM interaction tokens
const interactionTokens = timelineEvent.details.total_tokens;
const inputTokens = timelineEvent.details.input_tokens;
const outputTokens = timelineEvent.details.output_tokens;

// Check if token data is available (will be null for old interactions)
if (timelineEvent.details.total_tokens) {
  displayInteractionTokens(timelineEvent.details);
}
```

**Stage-Level Aggregated Token Data:**
```javascript  
// From stage objects - aggregated tokens for entire stage
const stageTokens = stage.stage_total_tokens;
const stageInputTokens = stage.stage_input_tokens;
const stageOutputTokens = stage.stage_output_tokens;

// Display stage token summary
if (stage.stage_total_tokens) {
  displayStageTokenSummary({
    stageName: stage.stage_name,
    totalTokens: stage.stage_total_tokens,
    inputTokens: stage.stage_input_tokens,
    outputTokens: stage.stage_output_tokens
  });
}
```

**Session-Level Aggregated Token Data:**
```javascript
// From session statistics - aggregated tokens for entire session  
const sessionTokens = sessionStats.session_total_tokens;
const sessionInputTokens = sessionStats.session_input_tokens;
const sessionOutputTokens = sessionStats.session_output_tokens;

// Display session token overview
if (sessionStats.session_total_tokens) {
  displaySessionTokenOverview({
    sessionId: session.session_id,
    totalTokens: sessionStats.session_total_tokens,
    inputTokens: sessionStats.session_input_tokens, 
    outputTokens: sessionStats.session_output_tokens,
    llmInteractions: sessionStats.llm_interactions
  });
}
```

**Multi-Level Token Display:**
```javascript
// Dashboard can show token usage at all levels simultaneously
function TokenUsageDisplay({ session, stages, interactions }) {
  return (
    <div>
      {/* Session-level total */}
      <SessionTokenSummary tokens={session.session_total_tokens} />
      
      {/* Stage-level breakdown */}
      {stages.map(stage => (
        <StageTokenSummary 
          key={stage.execution_id}
          stageName={stage.stage_name}
          tokens={stage.stage_total_tokens}
        />
      ))}
      
      {/* Individual interaction details (debug view) */}
      {interactions.map(interaction => (
        <InteractionTokenDetails
          key={interaction.event_id}
          tokens={interaction.details.total_tokens}
          model={interaction.details.model_name}
        />
      ))}
    </div>
  );
}
```

## Implementation Plan

### Phase 1: Core Token Capture
1. **LLM Client Updates**: 
   - Add imports: `UsageMetadataCallbackHandler`, `UsageMetadata`
   - Update `_execute_with_retry()` to return `Tuple[Any, Optional[UsageMetadata]]`
   - Update `generate_response()` to capture and store token data in `ctx.interaction`
2. **Model Updates**: Add token fields to `LLMInteraction` in `unified_interactions.py`

### Phase 2: Backend Aggregations  
1. **Stage Aggregations**: Add computed fields to `DetailedStage` model:
   - `stage_input_tokens`, `stage_output_tokens`, `stage_total_tokens`
2. **Session Aggregations**: 
   - Add token fields to `SessionStats` model
   - Update `HistoryService.get_session_summary()` to calculate session token totals
3. **API Integration**: Verify token fields flow through existing endpoints

### Phase 3: Frontend Display
1. **TypeScript Types**: Add token fields to `Session` and `StageExecution` interfaces
2. **Component Updates**:
   - Session list: Show session token totals
   - Session header: Display session aggregations  
   - Stage cards: Show stage token sums
   - Debug tab: Enhanced interaction token display (already partially exists)
3. **Multi-level Token Display**: Create reusable components for different aggregation levels

### Phase 4: Testing & Validation
1. **Backend Tests**: Token capture, aggregation calculations, API responses
2. **Integration Tests**: All 4 LLM providers, graceful degradation
3. **Frontend Tests**: Token display across all dashboard views
4. **E2E Validation**: Complete token flow from LLM call to dashboard display

## Provider Support Matrix

**Current LangChain Integration (from pyproject.toml):**
- `langchain-openai>=0.3.0`
- `langchain-google-genai>=2.1.0`  
- `langchain-xai>=0.2.0` (Grok/X.AI)
- `langchain-anthropic>=0.3.0`

**Token Usage Support with UsageMetadataCallbackHandler:**
| Provider  | Integration Module       | Token Usage Support |
|-----------|-------------------------|---------------------|
| OpenAI    | `langchain-openai`      | ✅ Full Support     |
| Google    | `langchain-google-genai`| ✅ Full Support     |
| XAI/Grok  | `langchain-xai`         | ✅ Expected Support |
| Anthropic | `langchain-anthropic`   | ✅ Full Support     |

**Notes:**
- All providers use LangChain's standardized `UsageMetadataCallbackHandler` 
- Token usage support depends on provider API returning usage metadata
- Fields will be `None` if provider doesn't return usage data (graceful degradation)
