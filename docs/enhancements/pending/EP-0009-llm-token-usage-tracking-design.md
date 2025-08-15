# EP-0009: LLM Token Usage Tracking - Design Document

## Overview
Add exact token usage tracking to existing LLM interactions using LangChain's `UsageMetadataCallbackHandler` for universal provider support.

## Current State
- LLM client exists in `/backend/tarsy/integrations/llm/client.py`
- `LLMUsage` and `LLMResponse` models already exist with `usage` field
- Currently `usage=None` with comment "LangChain doesn't provide usage info by default"
- Token usage data stored in `LLMInteraction.token_usage` field

## Implementation Approach
**Method**: `UsageMetadataCallbackHandler` - works across all providers (OpenAI, Gemini, Grok)

No fallback methods - if provider doesn't support token usage, the field remains `None`.

## Code Changes Required

### 1. Update Models
```python
# LLMInteraction - Add three token fields, remove token_usage
class LLMInteraction(SQLModel, table=True):
    # ... existing fields ...
    
    # Add separate type-safe token fields
    input_tokens: Optional[int] = Field(None, description="Input/prompt tokens")
    output_tokens: Optional[int] = Field(None, description="Output/completion tokens")  
    total_tokens: Optional[int] = Field(None, description="Total tokens used")
    
    # Remove: token_usage: Optional[dict] = Field(...)

# LLMResponse - Remove unused usage field (clean up dead code)
class LLMResponse(SQLModel):
    """LLM response structure matching API format."""
    choices: List[LLMChoice] = Field(..., description="Response choices")
    model: Optional[str] = Field(None, description="Model used")
    # Remove: usage: Optional[LLMUsage] = Field(None, description="Token usage")

# LLMUsage model can also be removed (no longer used)
# Remove: class LLMUsage(SQLModel): ...
```

### 2. LLMClient._execute_with_retry() Method
```python
# Update method signature for type safety
async def _execute_with_retry(
    self, 
    messages: List[LLMMessage], 
    request_id: str, 
    max_retries: int = 3
) -> Tuple[Any, Optional[UsageMetadata]]:

    # Add callback handler to capture usage
    callback = UsageMetadataCallbackHandler()
    response = await self.llm_client.ainvoke(
        langchain_messages, 
        config={"callbacks": [callback]}
    )

    # Extract and return both response and usage (type-safe)
    return response, callback.usage_metadata
```

### 3. LLMClient.generate_response() Method
```python
# Update response creation to include usage (type-safe)
response, usage_metadata = await self._execute_with_retry(messages, request_id)

# Store token usage in dedicated type-safe fields
if usage_metadata:
    ctx.interaction.input_tokens = usage_metadata.input_tokens
    ctx.interaction.output_tokens = usage_metadata.output_tokens
    ctx.interaction.total_tokens = usage_metadata.total_tokens

# Create clean typed_response (no usage field)
typed_response = LLMResponse(
    choices=[...],
    model=self.model
    # No usage field - token data stored directly on interaction
)
```

### 4. Add Imports
```python
from langchain_core.callbacks import UsageMetadataCallbackHandler
from langchain_core.messages import UsageMetadata
from typing import Optional, Tuple

# Remove unused import:
# from tarsy.models.unified_interactions import LLMUsage
```

## Data Flow
1. LLM call made with `UsageMetadataCallbackHandler` attached
2. Callback captures token usage from provider
3. Usage data stored in separate type-safe fields on `LLMInteraction`
4. Response JSON kept simple and unchanged
5. Available in database via dedicated typed columns

**Accessing Usage Data:**
```python
# From LLMInteraction database record - fully type-safe
interaction = get_llm_interaction(interaction_id)
total_tokens = interaction.total_tokens     # Optional[int]
input_tokens = interaction.input_tokens     # Optional[int]
output_tokens = interaction.output_tokens   # Optional[int]

# Easy database queries
sessions_with_high_usage = session.query(LLMInteraction).filter(
    LLMInteraction.total_tokens > 1000
).all()
```

## Testing Requirements
- Test token usage capture for all 3 providers (OpenAI, Gemini, Grok)
- Test handling when usage data unavailable
- Verify existing functionality unchanged
- Test database storage of token usage

## Benefits
- Exact token counts per interaction
- Usage tracking and optimization data
- Fully type-safe access (no dict key lookups)
- Universal provider support
- Clean code (removes unused `LLMUsage` model and `usage` field)
- Proper database schema (integer columns vs JSON)
- Easy database querying and filtering
- Better IDE support and autocomplete
- No legacy/dead code hanging around

## Implementation Files
- `/backend/tarsy/integrations/llm/client.py` - Main LLM client changes  
- `/backend/tarsy/models/unified_interactions.py` - Add token fields to LLMInteraction, remove usage from LLMResponse
- `/backend/tarsy/services/history_service.py` - Include token fields in timeline event details
- Database schema migration only - add three optional integer columns, remove JSON column
- Test files may need minor updates (remove usage field references)

## Database Migration
- **Schema only**: Add `input_tokens`, `output_tokens`, `total_tokens` as nullable INTEGER columns
- **No data migration needed**: Old interactions will have `NULL` values (which map to `None` in Python)
- **Backward compatible**: Existing code unaffected by new optional fields

## API Surface Changes

### Timeline Event Details Structure
Token usage will be automatically included in timeline event details for LLM interactions:

```python
# Current structure
{
  "event_id": "abc123",
  "type": "llm_interaction", 
  "timestamp_us": 1703001234567890,
  "step_description": "Generate analysis recommendations",
  "details": {
    "interaction_id": "def456",
    "model_name": "gpt-4-1106-preview",
    "provider": "openai", 
    "request_id": "req_789",
    "duration_ms": 2340,
    "success": true
    # NEW: Token usage fields added automatically
    "input_tokens": 120,
    "output_tokens": 45,
    "total_tokens": 165
  }
}
```

### Where Token Data Appears
- **`/api/v1/history/sessions`** - Session list with interaction summaries
- **`/api/v1/history/sessions/{session_id}`** - Full session details with timeline
- **WebSocket timeline updates** - Real-time updates include token data
- **Dashboard components** - Can display token usage per interaction

### Access Pattern
```javascript
// Dashboard can access token data from timeline events
const tokenUsage = timelineEvent.details.total_tokens;
const inputTokens = timelineEvent.details.input_tokens;
const outputTokens = timelineEvent.details.output_tokens;

// Check if token data is available (will be null for old interactions)
if (timelineEvent.details.total_tokens) {
  displayTokenUsage(timelineEvent.details);
}
```

## History Service Changes

The history service needs a minor update to include token fields in timeline event details:

```python
# In create_timeline_event_for_llm_interaction()
def create_timeline_event_for_llm_interaction(interaction: LLMInteraction) -> TimelineEvent:
    details = {
        "interaction_id": interaction.interaction_id,
        "model_name": interaction.model_name,
        "provider": interaction.provider,
        "request_id": interaction.request_id,
        "duration_ms": interaction.duration_ms,
        "success": interaction.success,
        # NEW: Include token usage if available
        "input_tokens": interaction.input_tokens,
        "output_tokens": interaction.output_tokens,
        "total_tokens": interaction.total_tokens
    }
    # Filter out None values to keep API clean
    details = {k: v for k, v in details.items() if v is not None}
    
    return TimelineEvent(
        event_id=interaction.interaction_id,
        type="llm_interaction",
        timestamp_us=interaction.timestamp_us,
        step_description=interaction.step_description,
        details=details,
        duration_ms=interaction.duration_ms,
        stage_execution_id=interaction.stage_execution_id
    )
```

## Provider Support Matrix
| Provider | Token Usage Support |
|----------|---------------------|
| OpenAI   | ✅ Full             |
| Gemini   | ✅ Full             |
| Grok/XAI | ✅ Expected         |

## Risk Assessment
- **Low Risk**: Uses optional fields that default to `None`
- **Database Migration Required**: Adding new columns, removing existing `token_usage` JSON column
- **Graceful Degradation**: Fields remain `None` if usage unavailable
- **Backward Compatibility**: Existing code unaffected (only adds new fields)
