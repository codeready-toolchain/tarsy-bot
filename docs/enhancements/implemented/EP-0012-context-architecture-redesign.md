# Context Architecture Redesign

**Status**: 📋 **IMPLEMENTED**

## Problem Statement

Current context system has architectural issues:
- Misleading names (`AlertProcessingData` is actually chain context, `IterationContext` is actually stage context)
- Massive field duplication between `IterationContext` and `PromptContext` (5 out of 9 fields duplicated)
- Unnecessary wrapper (`ChainExecutionContext` around `Dict[str, AgentExecutionResult]`)
- Union types requiring runtime type checking
- **API-only methods mixed with processing logic**: `get_severity()`, `get_environment()` belong in AlertService API formatting
- **Stage execution order lost**: `ChainExecutionContext.stage_results` is unordered `Dict[str, AgentExecutionResult]`
- **Session ID handling inconsistency**: `session_id` passed separately to `process_alert()` instead of being part of context
- **Type inconsistency**: `stage_outputs` declared as `Dict[str, Dict[str, Any]]` but actually contains `AgentExecutionResult` objects

## New Architecture

### 2-Level Context Hierarchy

```
ChainContext (entire processing session)
    ├── alert_type, alert_data, session_id
    ├── current_stage_name, stage_outputs
    └── processing methods
    
StageContext (single stage execution)
    ├── chain_context: ChainContext
    ├── available_tools: AvailableTools  
    ├── agent: BaseAgent
    └── derived properties (no duplication)
```

### Eliminated Complexity
- ❌ PromptContext (use StageContext directly)
- ❌ ChainExecutionContext wrapper (use `Dict[str, AgentExecutionResult]` with explicit ordering)
- ❌ Union types (always use concrete types)
- ❌ API-only methods in processing models (`get_severity`, `get_environment` → AlertService)
- ❌ Temporary conversion utilities (removed after migration)
- ✅ **Fixed**: Stage execution order preserved via `List[tuple[str, AgentExecutionResult]]`

## Implementation

### 1. ChainContext (rename from AlertProcessingData)

```python
class ChainContext(BaseModel):
    """Context for entire chain processing session."""
    
    # Core data
    alert_type: str
    alert_data: Dict[str, Any]  # Flexible client data
    session_id: str  # FIXED: Now required field, set during creation
    
    # Chain execution state  
    current_stage_name: str  # Always set (not Optional)
    stage_outputs: Dict[str, AgentExecutionResult] = Field(default_factory=dict)  # FIXED: Correct type
    
    # Processing support
    runbook_content: Optional[str] = None
    chain_id: Optional[str] = None
    
    def get_original_alert_data(self) -> Dict[str, Any]:
        return self.alert_data.copy()
    
    def get_runbook_content(self) -> str:
        return self.runbook_content or ""
    
    def get_previous_stages_results(self) -> List[tuple[str, AgentExecutionResult]]:
        """Get completed stage results in execution order."""
        # Dict preserves insertion order (Python 3.7+) and stages are added sequentially
        # so iteration order = execution order
        return [
            (stage_name, result) 
            for stage_name, result in self.stage_outputs.items()
            if result.status.value == "completed"
        ]
    
    def add_stage_result(self, stage_name: str, result: AgentExecutionResult):
        self.stage_outputs[stage_name] = result
    
    # NOTE: get_severity() and get_environment() REMOVED
    # These are API formatting methods that belong in AlertService, not processing models
```

### 2. StageContext (rename from IterationContext)

```python
@dataclass
class StageContext:
    """Context for single stage execution - eliminates all duplication."""
    
    # Core references (no duplication!)
    chain_context: ChainContext
    available_tools: AvailableTools
    agent: 'BaseAgent'
    
    # Convenient derived properties
    @property
    def alert_data(self) -> Dict[str, Any]:
        return self.chain_context.get_original_alert_data()
    
    @property
    def runbook_content(self) -> str:
        return self.chain_context.get_runbook_content()
    
    @property
    def session_id(self) -> str:
        return self.chain_context.session_id
    
    @property
    def stage_name(self) -> str:
        return self.chain_context.current_stage_name
    
    @property
    def agent_name(self) -> str:
        return self.agent.__class__.__name__
    
    @property
    def mcp_servers(self) -> List[str]:
        return self.agent.mcp_servers()
    
    @property
    def previous_stages_results(self) -> List[tuple[str, AgentExecutionResult]]:
        return self.chain_context.get_previous_stages_results()
    
    def has_previous_stages(self) -> bool:
        return len(self.previous_stages_results) > 0
    
    def format_previous_stages_context(self) -> str:
        """Format previous stage results for prompts in execution order."""
        results = self.previous_stages_results
        if not results:
            return "No previous stage context available."
        
        sections = []
        for stage_name, result in results:  # Now iterating over ordered list
            stage_title = result.stage_description or stage_name
            sections.append(f"## Results from '{stage_title}' stage:")
            sections.append(result.result_summary)
            sections.append("")
        
        return "\n".join(sections)
```

### 3. AvailableTools (structured typing with migration safety)

```python
class MCPTool(BaseModel):
    server: str
    name: str
    description: str
    parameters: List[Dict[str, Any]]

class AvailableTools(BaseModel):
    tools: List[Union[MCPTool, Dict[str, Any]]]  # MIGRATION SAFETY: Support both formats during transition
    
    @classmethod
    def from_legacy_format(cls, legacy_tools: List[Dict[str, Any]]) -> 'AvailableTools':
        """TEMPORARY: Convert legacy List[Dict] to AvailableTools during migration."""
        # This method will be DELETED in Phase 6
        return cls(tools=legacy_tools)
    
    def to_prompt_format(self) -> str:
        if not self.tools:
            return "No tools available."
        
        formatted_tools = []
        for tool in self.tools:
            if isinstance(tool, MCPTool):
                formatted_tools.append(f"{tool.server}.{tool.name}: {tool.description}")
            else:  # Legacy Dict[str, Any] during migration
                # Handle legacy format temporarily
                formatted_tools.append(f"{tool.get('server', 'unknown')}.{tool.get('name', 'tool')}: {tool.get('description', 'No description')}")
        return "\n".join(formatted_tools)
```

**Note**: The `from_legacy_format()` method and `Union` type support will be **completely removed** in Phase 6 cleanup, leaving only clean `List[MCPTool]`.

## Migration Steps

### Phase 0: Create New Models

**Create new module with clean implementations - no breaking changes yet:**

```bash
# Create new module
backend/tarsy/models/processing_context.py
```

**Why `processing_context.py`?**
- Contains both ChainContext and StageContext 
- Clear scope: models for processing contexts
- Avoids confusion with other context types
- Easy to find and understand

1. **Implement ChainContext** (complete, clean implementation)
2. **Implement StageContext** (complete, clean implementation)  
3. **Implement AvailableTools** (if not exists)
4. **Write comprehensive unit tests** for new models
5. **Test in isolation** - verify all functionality works
6. **Add conversion utilities** (old model → new model, **temporary - will be removed in Phase 6**)

**Benefits**: 
- ✅ No existing code broken - **zero risk**
- ✅ New models tested in isolation
- ✅ Side-by-side comparison possible
- ✅ Easy rollback if issues found
- ✅ Can develop/test new architecture independently
- ✅ Gradual migration reduces deployment risk

### Phase 1: Gradual Integration Start

1. **Update imports strategically**
   ```python
   # Start with non-critical imports
   from tarsy.models.processing_context import ChainContext, StageContext
   # Keep old imports working: from tarsy.models.alert_processing import AlertProcessingData
   ```

2. **Add compatibility methods to old models** (TEMPORARY - will be DELETED in Phase 6)
   ```python
   # In AlertProcessingData - add TEMPORARY compatibility bridge
   def to_chain_context(self, session_id: str) -> ChainContext:
       """TEMPORARY: Convert to new ChainContext model with session_id injection."""
       # This method will be COMPLETELY REMOVED in Phase 6
       return ChainContext(
           alert_type=self.alert_type,
           alert_data=self.alert_data,
           session_id=session_id,  # FIXED: Inject session_id during conversion
           current_stage_name=self.current_stage_name,
           stage_outputs=self.stage_outputs,  # Already AgentExecutionResult objects
           runbook_content=self.runbook_content,
           chain_id=self.chain_id
       )
   ```

### Phase 2: Start Using New Models in Tests

1. **Create test factory using new models**
   ```python
   # In test files - start using ChainContext
   def create_test_chain_context() -> ChainContext:
       return ChainContext(
           alert_type="kubernetes",
           alert_data={"test": "data"},
           session_id="test-session-123",  # FIXED: Always include session_id
           current_stage_name="analysis"
       )
   ```

2. **Add TEMPORARY compatibility tests** (will be DELETED in Phase 6)
   ```python
   # TEMPORARY: Test both old and new side-by-side during migration
   def test_context_conversion_compatibility():  # ← TEMPORARY TEST - WILL BE DELETED
       """TEMPORARY: Test old→new conversion works correctly."""
       old_context = create_test_alert_processing_data()
       new_context = old_context.to_chain_context("test-session-123")
       
       assert new_context.session_id == "test-session-123"
       assert new_context.alert_type == old_context.alert_type
       assert new_context.stage_outputs == old_context.stage_outputs
   ```

   **Note**: All conversion tests will be **COMPLETELY REMOVED** in Phase 6.

### Phase 3: Update Agent Layer

1. **Add new process_alert overload** (TEMPORARY - don't remove old one yet)
   ```python
   # In BaseAgent - TEMPORARY support for both signatures during migration
   async def process_alert(self, context: Union[AlertProcessingData, ChainContext], session_id: Optional[str] = None):
       if isinstance(context, AlertProcessingData):
           # TEMPORARY: Convert to new model with session_id injection
           if not session_id:
               raise ValueError("session_id is required when using AlertProcessingData")
           chain_context = context.to_chain_context(session_id)  # FIXED: Pass session_id
           return await self._process_alert_new(chain_context)
       else:
           # context is ChainContext - session_id already included
           if session_id and session_id != context.session_id:
               logger.warning(f"session_id parameter ({session_id}) differs from context.session_id ({context.session_id})")
           return await self._process_alert_new(context)
   ```

   **Final signature** (after Phase 6 cleanup):
   ```python
   # Clean final signature - no Union types, no separate session_id
   async def process_alert(self, context: ChainContext) -> AgentExecutionResult:
       # session_id is already in context.session_id
   ```

2. **Update iteration controllers to create StageContext**
   ```python
   # Create StageContext from ChainContext 
   stage_context = StageContext(
       chain_context=chain_context,
       available_tools=tools,
       agent=self
   )
   ```

### Phase 4: Update Prompt System

1. **Update prompt builders to accept StageContext**
   ```python
   def build_prompt(self, context: StageContext) -> str:
       alert_data = context.alert_data
       previous_stages = context.format_previous_stages_context()
   ```

2. **Remove PromptContext usage** - replace with StageContext

### Phase 5: Update AlertService

1. **Start using ChainContext in AlertService**
   ```python
   # FIXED: Create ChainContext with session_id from the start
   chain_context = ChainContext(
       alert_type=alert.alert_type,
       alert_data=alert.alert_data,
       session_id=session_id,  # FIXED: Set session_id during creation
       current_stage_name=stage.name,
       runbook_content=alert.get_runbook_content(),  # Transfer existing data
       chain_id=chain_definition.chain_id
   )
   
   # Clean single-parameter call (no separate session_id)
   await agent.process_alert(chain_context)
   ```

### Phase 6: Final Migration & Cleanup

**🔥 CRITICAL: This phase COMPLETELY REMOVES all temporary migration code**

#### 6.1: **Delete All Conversion Utilities**
```python
# DELETE COMPLETELY - No conversion methods remain
# ❌ AlertProcessingData.to_chain_context() → DELETED
# ❌ AvailableTools.from_legacy_format() → DELETED  
# ❌ All to_*() and from_*() methods → DELETED
# ❌ All "TEMPORARY" marked code → DELETED

# RESULT: Clean implementation only - zero legacy conversion code
```

#### 6.2: **Delete Old Model Classes Entirely**
```python
# DELETE COMPLETELY:
# ❌ AlertProcessingData class → DELETED
# ❌ IterationContext class → DELETED
# ❌ ChainExecutionContext class → DELETED
# ❌ PromptContext class → DELETED

# RESULT: Only new models exist: ChainContext, StageContext, AvailableTools
```

#### 6.3: **Clean Up All Union Types**
```python
# BEFORE (temporary migration code):
async def process_alert(self, context: Union[AlertProcessingData, ChainContext], ...):

# AFTER (final clean implementation):
async def process_alert(self, context: ChainContext) -> AgentExecutionResult:
    # Clean, single type - no runtime checks needed
```

#### 6.4: **Delete All Temporary Tests**
```python
# DELETE COMPLETELY - All conversion tests removed:
# ❌ test_context_conversion_compatibility() → DELETED
# ❌ test_alert_processing_data_conversion() → DELETED  
# ❌ test_bidirectional_compatibility() → DELETED
# ❌ All tests marked "TEMPORARY" → DELETED

# RESULT: Only clean tests for new models remain
```

#### 6.5: **Update All Imports & Remove Files**
```python
# Replace all old imports:
# ❌ from tarsy.models.alert_processing import AlertProcessingData
# ✅ from tarsy.models.processing_context import ChainContext, StageContext

# Consider removing files:
# ❌ backend/tarsy/models/alert_processing.py (if fully migrated)
# ✅ Update all __init__.py files to export only new models
```

#### 6.6: **Final AvailableTools Cleanup** 
```python
# BEFORE (migration compatibility):
class AvailableTools(BaseModel):
    tools: List[Union[MCPTool, Dict[str, Any]]]  # ← Remove Union

# AFTER (final clean implementation):
class AvailableTools(BaseModel):
    tools: List[MCPTool]  # ← Clean, single type only
    
    def to_prompt_format(self) -> str:
        # Clean implementation - no legacy format handling
        formatted_tools = [f"{tool.server}.{tool.name}: {tool.description}" for tool in self.tools]
        return "\n".join(formatted_tools) if formatted_tools else "No tools available."
```

#### 6.7: **Move API Formatting to AlertService**
```python
# In AlertService - local formatting functions for API responses:
def _format_alert_severity(alert_data: Dict[str, Any]) -> str:
    return alert_data.get('severity', 'warning')

def _format_alert_environment(alert_data: Dict[str, Any]) -> str:
    return alert_data.get('environment', 'production')

# Use ONLY in API responses, never in ChainContext
```

## Error Handling Strategy

### Context Creation Errors
```python
class ContextConversionError(Exception):
    """Raised when context conversion fails during migration."""
    pass

# During migration phases - handle conversion failures gracefully:
try:
    chain_context = old_context.to_chain_context(session_id)
except Exception as e:
    logger.error(f"Context conversion failed: {e}")
    # Fallback to old processing path during migration
    raise ContextConversionError(f"Failed to convert context: {e}")
```

### Migration Safety Guards
```python
# Add validation during migration
def validate_context_conversion(old_context, new_context, session_id):
    """Validate that context conversion preserves all critical data."""
    assert new_context.alert_type == old_context.alert_type
    assert new_context.session_id == session_id
    assert len(new_context.stage_outputs) == len(old_context.stage_outputs)
    # Validate all critical fields are preserved
```

## Test Strategy

### Phase 0-5: **Migration Testing**
```python
# TEMPORARY test utilities - will be DELETED in Phase 6
class TemporaryTestUtils:
    """TEMPORARY: Test utilities for migration period only."""
    
    @staticmethod
    def create_test_contexts_pair() -> tuple[AlertProcessingData, ChainContext]:
        """Create matching old/new contexts for migration testing."""
        # This entire class will be DELETED in Phase 6
        
def test_migration_data_preservation():
    """TEMPORARY: Ensure migration preserves all data."""
    # This test will be DELETED in Phase 6
    old_context, new_context = TemporaryTestUtils.create_test_contexts_pair()
    # Test data preservation...
```

### Phase 6: **Final Clean Tests**
```python
# FINAL test strategy - only test new models directly
class TestChainContext:
    """Test clean ChainContext implementation."""
    
    def test_chain_context_creation(self):
        """Test creating ChainContext with all required fields."""
        context = ChainContext(
            alert_type="kubernetes",
            alert_data={"pod": "failing"},
            session_id="session-123",
            current_stage_name="analysis"
        )
        assert context.session_id == "session-123"
        assert context.current_stage_name == "analysis"

# NO conversion tests, NO compatibility tests, NO temporary test utilities
```

## Files to Change

### New Module (Phase 0)
- `backend/tarsy/models/processing_context.py` → **NEW** - Contains ChainContext, StageContext, AvailableTools

### Core Models (Later phases)
- `backend/tarsy/models/alert_processing.py` → Add TEMPORARY compatibility bridge, eventually DELETE
- `backend/tarsy/agents/iteration_controllers/base_iteration_controller.py` → Gradually migrate to new StageContext

### Agents  
- `backend/tarsy/agents/base_agent.py` → Remove create_prompt_context, update process_alert signature
- `backend/tarsy/agents/iteration_controllers/*.py` → Use StageContext directly
- `backend/tarsy/agents/prompts/*.py` → Accept StageContext instead of PromptContext

### Services
- `backend/tarsy/services/alert_service.py` → Set session_id during ChainContext creation, call process_alert(chain_context)
- `backend/tarsy/services/alert_service.py` → Add local formatting functions for severity/environment (API responses only)

### Tests  
- `backend/tests/unit/agents/` → Add TEMPORARY migration tests, then clean up to new context tests only
- `backend/tests/unit/models/` → Add TEMPORARY conversion tests, then clean up to new model tests only
- `backend/tests/integration/` → Update end-to-end flows, remove all temporary tests in Phase 6

## Success Criteria

### Phase 0 Complete:
- [ ] New `processing_context.py` module created with all new models
- [ ] ChainContext, StageContext, AvailableTools fully implemented
- [ ] Comprehensive unit tests for new models pass
- [ ] TEMPORARY conversion utilities from old models working
- [ ] Performance benchmarks established for new vs old context access

### Migration Safety (Phases 1-5):
- [ ] **Context conversion is lossless**: All data preserved during old→new conversion
- [ ] **Session ID handling is consistent**: session_id properly injected during ChainContext creation
- [ ] **Type compatibility maintained**: AgentExecutionResult objects work in both systems  
- [ ] **Error handling is robust**: Context conversion failures don't break processing
- [ ] **TEMPORARY tests validate conversion**: All migration scenarios tested
- [ ] **Gradual rollout works**: Can run old and new systems side-by-side

### Final Architecture (After Phase 6):
- [ ] Zero field duplication between contexts
- [ ] Clear 2-level hierarchy: Chain → Stage  
- [ ] Names match actual scope/lifetime (ChainContext, StageContext)
- [ ] No Union types in context system 
- [ ] Single source of truth for all context data
- [ ] **Stage execution order preserved** in context formatting
- [ ] Simplified agent API: `process_alert(chain_context)` only
- [ ] **Property access performance acceptable**: No significant slowdown from @property methods
- [ ] **Memory usage unchanged or improved**: New context system efficient

### Final Cleanup Complete (Phase 6):
- [ ] **🔥 ZERO conversion utilities**: No to_*() or from_*() methods exist anywhere
- [ ] **🔥 ZERO compatibility code**: No Union[Old, New] types remain in any signature
- [ ] **🔥 ZERO temporary tests**: No tests for deleted conversion utilities
- [ ] **🔥 Old model cleanup**: AlertProcessingData, IterationContext, ChainExecutionContext, PromptContext COMPLETELY DELETED
- [ ] **🔥 Clean codebase**: Only new models and their direct tests remain
- [ ] **Alert API cleaned**: severity/environment moved to AlertService local functions
- [ ] **Clean imports**: Only processing_context module imported, all old imports removed
- [ ] **Files removed**: alert_processing.py deleted if fully migrated
- [ ] **No legacy imports**: All old model imports purged from entire codebase

## Implementation Notes

### Why This Approach is Better:

- **Zero-risk start** - Phase 0 creates new models without touching existing code
- **Gradual migration** - Each phase is small and testable
- **Side-by-side testing** - Can compare old vs new behavior during migration
- **Easy rollback** - If issues found, just stop using new models
- **No big-bang deployment** - Reduces risk of breaking production
- **🔥 Complete cleanup guarantee** - Phase 6 eliminates ALL temporary code

### Technical Details:

- **Start with new module** - `processing_context.py` with clean implementations
- **🔥 TEMPORARY compatibility bridges** - `to_chain_context()` methods ONLY during migration
- **Test incrementally** - Run tests after each phase, then DELETE temporary tests
- **Properties are cheap** - Use them liberally to avoid duplication
- **🔥 TEMPORARY Union types** - Support both old and new ONLY during migration
- **Session ID injection** - Pass session_id to conversion methods, embed in ChainContext
- **Performance monitoring** - Benchmark property access vs direct field access

### Migration Code Lifecycle:

```python
# Phase 1-5: TEMPORARY code exists
def to_chain_context(self, session_id: str):  # ← TEMPORARY
    """TEMPORARY: Will be DELETED in Phase 6"""
    
# Phase 6: TEMPORARY code DELETED
# ❌ No conversion methods exist
# ❌ No compatibility code exists  
# ❌ No Union types exist
# ✅ Only clean new models remain
```

### Final State Guarantees:

- **🔥 Zero legacy code**: No conversion utilities, no compatibility layers
- **🔥 Zero temporary tests**: All migration tests deleted
- **🔥 Clean architecture**: Only ChainContext, StageContext, AvailableTools exist
- **Single source of truth**: No data duplication between contexts
- **Clean signatures**: `process_alert(chain_context: ChainContext)` only

### Module Name Choice:

`processing_context.py` is better than:
- ❌ `chain_context.py` - too narrow, also has StageContext
- ❌ `contexts.py` - too vague, could be anything  
- ✅ `processing_context.py` - clear scope, descriptive

### Critical Success Factor:

**Phase 6 cleanup is MANDATORY** - this is not optional. All temporary migration code MUST be deleted to achieve the clean architecture. Any remaining conversion utilities or compatibility code represents technical debt that defeats the purpose of this redesign.

This redesign eliminates architectural debt and creates a maintainable, clean context system with zero legacy code.
