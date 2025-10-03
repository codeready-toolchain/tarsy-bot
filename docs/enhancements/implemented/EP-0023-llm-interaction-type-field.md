# EP-0023: LLM Interaction Type Discriminator Field

## Problem Statement

The dashboard UI cannot reliably distinguish between different types of LLM interactions (regular ReAct, summarization, final analysis). Currently, it uses heuristics based on system message content patterns to detect summarization:

```typescript
// Current fragile detection
function isSummarizationInteraction(messages: LLMMessage[]): boolean {
  const systemMessage = messages.find(msg => msg.role === 'system');
  const content = systemMessage.content.toLowerCase();
  return content.includes('summarizing technical output') || ...
}
```

This causes rendering issues:
- **After timeline fix**: Summarization LLM interactions appear correctly in chronological order (MCP → Summarization → Next LLM)
- **UI Bug**: Summarization may be parsed as "Final Answer" by the ReAct parser fallback heuristic, causing duplicate rendering:
  - Once as summarization block (correct)
  - Once as final analysis block (incorrect)

The heuristic-based detection is fragile and breaks when:
- System prompts change
- Detection keywords are not present
- New interaction types are added

We need an explicit, database-backed type field to reliably distinguish interaction types.

## Design

### Type Constants (New)

Define interaction types as an enum for type safety:

```python
# backend/tarsy/models/constants.py (add to existing file)
from enum import Enum

class LLMInteractionType(str, Enum):
    """Types of LLM interactions for categorization and UI rendering."""
    INVESTIGATION = "investigation"
    SUMMARIZATION = "summarization"
    FINAL_ANALYSIS = "final_analysis"
```

### Database Schema Change

Add `interaction_type` field to `LLMInteraction` model:

```python
# backend/tarsy/models/unified_interactions.py
from tarsy.models.constants import LLMInteractionType

class LLMInteraction(SQLModel, table=True):
    # ... existing fields ...
    
    interaction_type: str = Field(
        default=LLMInteractionType.INVESTIGATION.value,
        sa_column=Column(String(50), nullable=False, 
                        server_default=LLMInteractionType.INVESTIGATION.value),
        description="Type of LLM interaction"
    )
```

**Type Values:**
- `LLMInteractionType.INVESTIGATION` → `"investigation"` - ReAct investigation/reasoning iterations (thought/action/observation loops)
- `LLMInteractionType.SUMMARIZATION` → `"summarization"` - MCP result summarization calls
- `LLMInteractionType.FINAL_ANALYSIS` → `"final_analysis"` - Stage conclusion with "Final Answer:" (any stage, any strategy)
  - Auto-detected when LLM response contains "Final Answer:"
  - Represents the concluding interaction of a stage
  - Can appear in multiple stages throughout a chain

### Migration Strategy (Using EP-0022 Alembic)

**Generate Migration:**
```bash
make migration msg="Add interaction_type to LLM interactions"
```

This creates: `backend/alembic/versions/20251003_HHMM_<hash>_add_interaction_type_to_llm_interactions.py`

**Edit Generated Migration:**
1. Verify it contains:
   - ✅ `op.add_column('llm_interactions', sa.Column('interaction_type', sa.String(50), ...)`
   - ✅ `nullable=False` with `server_default='investigation'`
   - ✅ `downgrade()` drops the column
2. Add the backfill queries (see below)

**Manual Addition Required - Backfill Existing Data:**

Add to the generated `upgrade()` function to categorize all existing interactions:

```python
# After the add_column() call, add:
connection = op.get_bind()

# Identify summarization interactions (system message contains summarization marker)
# Check for the specific system message content that only appears in summarization calls
connection.execute(sa.text("""
    UPDATE llm_interactions 
    SET interaction_type = 'summarization'
    WHERE conversation::text LIKE '%You are an expert at summarizing technical output%'
"""))

# Identify final_analysis interactions (last assistant message contains "Final Answer:")
# More complex: need to parse JSON and check last assistant message
# For PostgreSQL with JSONB - check if last assistant message starts with "Final Answer:"
connection.execute(sa.text("""
    UPDATE llm_interactions 
    SET interaction_type = 'final_analysis'
    WHERE interaction_type != 'summarization'
    AND EXISTS (
        SELECT 1 FROM (
            SELECT 
                msg->>'content' as content,
                ROW_NUMBER() OVER (ORDER BY ordinality DESC) as rn
            FROM jsonb_array_elements(conversation->'messages') WITH ORDINALITY AS msg
            WHERE msg->>'role' = 'assistant'
        ) last_assistant
        WHERE last_assistant.rn = 1
        AND (
            last_assistant.content LIKE 'Final Answer:%'
            OR last_assistant.content LIKE '% Final Answer:%'
            OR last_assistant.content LIKE '%\nFinal Answer:%'
        )
    )
"""))

# Explicitly set remaining records to 'investigation' (don't rely on default)
connection.execute(sa.text("""
    UPDATE llm_interactions 
    SET interaction_type = 'investigation'
    WHERE interaction_type NOT IN ('summarization', 'final_analysis')
"""))
```

**Backfill Logic:**
1. All records start with default `'investigation'` (from `server_default`)
2. Identify and mark `'summarization'` (MCP summaries)
3. Identify and mark `'final_analysis'` (excluding already-marked summarizations)
4. Explicitly set remaining records to `'investigation'` (ReAct iterations - don't rely on default)

**Note**: This backfill is **required** to properly categorize existing data. PostgreSQL syntax shown; for SQLite use `json_extract()` or similar text search functions.

### Backend Changes

#### 1. Update Summarization to Set Type

**File**: `backend/tarsy/integrations/mcp/summarizer.py`

```python
from tarsy.models.constants import LLMInteractionType

class MCPResultSummarizer:
    async def summarize_result(self, ...) -> Dict[str, Any]:
        # ... existing code to build conversation ...
        
        # Generate summary using LLM client
        response_conversation = await self.llm_client.generate_response(
            summarization_conversation, 
            session_id, 
            stage_execution_id,
            max_tokens=max_summary_tokens,
            interaction_type=LLMInteractionType.SUMMARIZATION  # ← NEW: Pass type constant
        )
        
        # ... return summary ...
```

#### 2. Update LLM Client with Auto-Detection

**File**: `backend/tarsy/integrations/llm/client.py`

```python
from tarsy.models.constants import LLMInteractionType

class LLMProviderClient:
    async def generate_response(
        self,
        conversation: LLMConversation,
        session_id: str,
        stage_execution_id: Optional[str] = None,
        max_tokens: Optional[int] = None,
        interaction_type: Optional[str] = None  # ← NEW: No default - explicit or auto-detect
    ) -> LLMConversation:
        
        async with llm_interaction_context(session_id, request_data, stage_execution_id) as ctx:
            # ... get LLM response ...
            response_conversation = await self._call_provider(...)
            
            # Determine interaction type
            if interaction_type is not None:
                # Explicit type provided - use as-is
                ctx.interaction.interaction_type = interaction_type
            else:
                # No type provided - auto-detect
                if self._contains_final_answer(response_conversation):
                    ctx.interaction.interaction_type = LLMInteractionType.FINAL_ANALYSIS
                else:
                    ctx.interaction.interaction_type = LLMInteractionType.INVESTIGATION
            
            # ... complete context ...
    
    def _contains_final_answer(self, conversation: LLMConversation) -> bool:
        """
        Check if the LAST message is from assistant and starts with 'Final Answer:'.
        
        This indicates a ReAct stage conclusion. Only checks the very last message
        in the conversation to avoid false positives.
        """
        if not conversation.messages:
            return False
        
        # Check LAST message only
        last_msg = conversation.messages[-1]
        
        # Must be from assistant
        if last_msg.role != "assistant":
            return False
        
        # Check if Final Answer appears at start of line
        content = last_msg.content.strip()
        if content.startswith("Final Answer:"):
            return True
        
        # Also check for Final Answer after newlines (multi-line messages)
        if "\nFinal Answer:" in last_msg.content:
            return True
        
        return False
```

**Key Logic:**
- If `interaction_type` provided → use it as-is (no auto-detection)
- If `interaction_type=None` (default):
  - Check if LAST message is assistant with "Final Answer:" → `FINAL_ANALYSIS`
  - Otherwise → `INVESTIGATION`
- Explicit types (`SUMMARIZATION`, `FINAL_ANALYSIS`) bypass auto-detection
- Most ReAct calls don't pass type → auto-detect correctly

#### 3. Update Hook Context Creation

**File**: `backend/tarsy/hooks/typed_context.py`

```python
from tarsy.models.constants import LLMInteractionType

@asynccontextmanager
async def llm_interaction_context(
    session_id: str, 
    request_data: Dict[str, Any], 
    stage_execution_id: Optional[str] = None
) -> AsyncContextManager[InteractionHookContext[LLMInteraction]]:
    
    interaction = LLMInteraction(
        session_id=session_id,
        stage_execution_id=stage_execution_id,
        model_name=request_data.get('model', 'unknown'),
        provider=request_data.get('provider', 'unknown'),
        temperature=request_data.get('temperature'),
        interaction_type=LLMInteractionType.INVESTIGATION.value  # ← NEW: Default value
    )
    
    async with InteractionHookContext(interaction, get_typed_hook_manager()) as ctx:
        yield ctx
```

#### 4. Update Final Analysis Controller

**File**: `backend/tarsy/agents/iteration_controllers/react_final_analysis_controller.py`

```python
from tarsy.models.constants import LLMInteractionType

class ReactFinalAnalysisController(IterationController):
    async def execute_analysis_loop(self, context: 'StageContext') -> str:
        """Execute final analysis with StageContext."""
        
        # ... build prompt and messages ...
        
        # Capture stage execution ID once for reuse
        stage_execution_id = context.agent.get_current_stage_execution_id()
        
        # Generate response with explicit final_analysis type
        conversation = await self.llm_client.generate_response(
            conversation, 
            context.session_id, 
            stage_execution_id,
            interaction_type=LLMInteractionType.FINAL_ANALYSIS  # ← NEW: Explicit type (no auto-detect)
        )
        
        # Extract and return the analysis
        analysis = conversation.get_latest_assistant_message().content
        return analysis
```

### Frontend Changes

#### Update Conversation Parser

**File**: `dashboard/src/utils/conversationParser.ts`

Replace heuristic detection with field check:

```typescript
// OLD: Heuristic-based detection
function isSummarizationInteraction(messages: LLMMessage[]): boolean {
  const systemMessage = messages.find(msg => msg.role === 'system');
  if (!systemMessage) return false;
  const content = systemMessage.content.toLowerCase();
  return content.includes('summarizing technical output') || ...;
}

// NEW: Field-based detection (simple and reliable)
function getInteractionStepType(interaction: LLMInteraction): 'investigation' | 'summarization' | 'final_analysis' {
  // Use explicit type field - always present after migration
  return interaction.interaction_type as 'investigation' | 'summarization' | 'final_analysis';
}

// Usage in parseStageConversation
for (const interaction of sortedInteractions) {
  const interactionType = getInteractionStepType(interaction);
  
  if (interactionType === 'summarization') {
    // Create summarization step
    const lastAssistantMessage = assistantMessages[assistantMessages.length - 1];
    if (lastAssistantMessage) {
      candidateSteps.push({
        type: 'summarization',
        content: lastAssistantMessage.content,
        timestamp_us: timestamp,
        success: true
      });
    }
  } else if (interactionType === 'final_analysis') {
    // Create final analysis step
    const lastAssistantMessage = assistantMessages[assistantMessages.length - 1];
    if (lastAssistantMessage) {
      candidateSteps.push({
        type: 'analysis',  // UI already has 'analysis' type
        content: lastAssistantMessage.content,
        timestamp_us: timestamp,
        success: true
      });
    }
  } else {
    // Investigation: Regular ReAct parsing
    const parsed = parseReActMessage(message.content);
    // ... handle thought/action/finalAnswer ...
  }
}
```

**Key Changes**: 
- Check `interaction.details.interaction_type` field instead of parsing system message content
- Handle all three types: `investigation`, `summarization`, `final_analysis`
- Map `final_analysis` → UI `'analysis'` type (existing UI component)

#### Type Definition Update

**File**: `dashboard/src/types/index.ts`

```typescript
export interface LLMInteraction {
  interaction_id: string;
  session_id: string;
  timestamp_us: number;
  model_name: string;
  provider?: string;
  conversation?: LLMConversation;
  success: boolean;
  error_message?: string;
  interaction_type: string;  // ← NEW: Required (migration backfills all records)
  // ... other fields ...
}
```

**Note**: Field is required because the migration backfills ALL existing records before frontend deployment.

### Testing Strategy

1. **Migration Test**: 
   ```bash
   # Test upgrade
   make migration-upgrade
   # Verify column exists
   # Test downgrade
   make migration-downgrade
   # Verify column removed
   ```

2. **Backend Unit Tests**:
   - Test `MCPResultSummarizer` sets `interaction_type="summarization"`
   - Test `LLMClient.generate_response` accepts and stores `interaction_type`
   - Test hook context creation with interaction type

3. **Integration Test**:
   - Create session with summarization
   - Verify database records have correct `interaction_type` values
   - Query interactions and verify type field

4. **E2E Test**:
   - Update `expected_conversations.py` to include `interaction_type` in assertions
   - Verify summarization interactions have `type="summarization"`
   - Verify regular interactions have `type="regular"`

5. **Frontend Test**:
   - Test conversation parser with new field
   - Verify summarization blocks render correctly
   - Verify no duplicate rendering as final analysis

## Implementation Plan

### Phase 0: Configure Migration Naming (One-Time Setup)
1. Update `backend/alembic.ini` line 14 to enable timestamp prefixes:
   ```ini
   # Change from:
   # file_template = %%(year)d_%%(month).2d_%%(day).2d_%%(hour).2d%%(minute).2d-%%(rev)s_%%(slug)s
   
   # To (uncommented and cleaner format):
   file_template = %%(year)d%%(month).2d%%(day).2d_%%(hour).2d%%(minute).2d_%%(rev)s_%%(slug)s
   ```
   
2. Rename existing migration file for consistency:
   ```bash
   cd backend/alembic/versions
   mv ae85467a75d2_initial_schema_baseline.py \
      20251002_2213_ae85467a75d2_initial_schema_baseline.py
   ```
   (Timestamp from git: 2025-10-02 22:13:28)
   
3. Update `down_revision` references if needed (usually automatic)

4. Verify migration history still works:
   ```bash
   make migration-history
   # Should show: 20251002_2213_ae85467a75d2 (head), Initial schema baseline
   ```

**Benefits:**
- All future migrations will have chronological ordering
- Easy to see migration sequence in file browser
- Existing migration renamed to match new convention

### Phase 1: Database Migration
1. Update `LLMInteraction` model with `interaction_type` field
2. Generate migration: `make migration msg="Add interaction_type to LLM interactions"`
3. Review generated migration in `backend/alembic/versions/20251003_HHMM_<hash>_add_interaction_type_to_llm_interactions.py`
4. Test migration:
   ```bash
   make migration-upgrade   # Apply
   make migration-downgrade # Rollback
   make migration-upgrade   # Re-apply
   ```
5. Verify column exists in both PostgreSQL and SQLite

### Phase 2: Backend Integration
1. Create `LLMInteractionType` enum in `backend/tarsy/models/constants.py`
2. Update `LLMInteraction` model to use enum values for defaults
3. Update `llm_interaction_context()` to use `LLMInteractionType.INVESTIGATION.value`
4. Update `LLMProviderClient.generate_response()`:
   - Add `interaction_type` parameter (default `None`)
   - Implement `_contains_final_answer()` helper method (checks LAST message only)
   - Add auto-detection logic: if `interaction_type=None`, detect final answer or default to `INVESTIGATION`
   - If `interaction_type` provided explicitly, use as-is (no auto-detection)
5. Update `MCPResultSummarizer.summarize_result()` to pass `interaction_type=LLMInteractionType.SUMMARIZATION`
6. Update `ReactFinalAnalysisController.execute_analysis_loop()` to pass `interaction_type=LLMInteractionType.FINAL_ANALYSIS`
7. **No changes needed** to `SimpleReActController` or `ReactStageController` (auto-detection handles them)
8. Add unit tests for all three interaction types + auto-detection behavior
9. Run backend tests: `make test-unit`

### Phase 3: Frontend Integration  
1. Update `LLMInteraction` TypeScript interface with `interaction_type: string` (required field)
2. Replace `isSummarizationInteraction(messages)` with `getInteractionStepType(interaction)`
3. Update conversation parser to handle all three types:
   - `investigation` → Parse as ReAct (thought/action/analysis)
   - `summarization` → Create summarization step
   - `final_analysis` → Create analysis step
4. Test locally with real session data
5. Verify no duplicate rendering in reasoning tab
6. Verify final analysis stages render correctly

### Phase 4: Testing & Validation
1. Create integration test for full flow:
   - Alert → Investigation (with type) → MCP call → Summarization (with type) → Continuation → Final Analysis (with type)
2. Update E2E test expectations with interaction types:
   - Investigation interactions: `interaction_type="investigation"`
   - Summarization interactions: `interaction_type="summarization"`
   - Final analysis interactions: `interaction_type="final_analysis"`
3. Manual testing:
   - Submit test alert with multi-stage chain
   - Verify investigation steps in reasoning tab
   - Verify summarization in reasoning tab (single block, no duplicate)
   - Verify final analysis renders correctly
   - Verify debug tab shows correct interaction types for all
4. Run full test suite: `make test`

## Technical Notes

### Auto-Detection Logic
- **When**: Only when `interaction_type=None` (not provided by caller)
- **Detection**: Check if LAST message in conversation is from assistant and contains "Final Answer:" at line start
- **Logic**: 
  - If type provided → use as-is (no detection)
  - If type=None + Final Answer detected → `FINAL_ANALYSIS`
  - If type=None + no Final Answer → `INVESTIGATION`
- **Controllers**: 
  - ReAct controllers: Don't pass type → auto-detect handles them
  - Summarizer/FinalAnalysis: Pass explicit type → no auto-detection overhead

### Backward Compatibility

**Migration Strategy**: The migration adds the `interaction_type` column with a default value and then **immediately backfills all existing records** with the correct type based on conversation patterns. This means:
- All records have `interaction_type` after migration completes
- No "missing" field scenario in normal operation
- Frontend can safely treat field as required (no null checks needed)

**Deployment Order**: Backend must deploy first (migration runs on startup), then frontend. This ensures:
1. Migration completes and backfills all data
2. API returns `interaction_type` for all records
3. Frontend expects required field and always receives it

**Auto-detection logic**: Handles existing ReAct patterns without controller changes

### SQLite vs PostgreSQL

**PostgreSQL**:
- Uses `jsonb_array_elements()` with window functions to find last assistant message
- Native JSONB operators for efficient querying
- The migration queries above are PostgreSQL-specific

**SQLite**:
- Simpler JSON handling without window functions
- Uses `json_extract()` and array indexing
- For SQLite, we'll use simpler text-based detection as a fallback:
  ```sql
  -- SQLite fallback (less precise but functional)
  WHERE conversation LIKE '%You are an expert at summarizing technical output%'
  ```

**Note**: The migration will include conditional logic based on database type, or use Alembic's `op.get_bind().dialect.name` to detect and apply appropriate queries.

### Future Extensions

Once `interaction_type` field is established, easy to add additional types:
- `"validation"` - for validation/verification steps
- `"reflection"` - for self-reflection or critique steps
- `"planning"` - for multi-step planning phases
- `"tool_selection"` - for tool discovery/selection reasoning
- Custom types for specific agent behaviors

### API Contract

No API changes needed - field is transparent to clients. Frontend reads it from existing interaction objects.

