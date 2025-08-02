# EP-0009: LLM Reasoning Capabilities for Enhanced Incident Response - Design Document

**Status:** Draft  
**Created:** 2025-01-08  
**Requirements:** `docs/enhancements/pending/EP-0009-reasoning-capabilities-requirements.md`

---

## Design Principles

**Core Guidelines:**
- **Balanced Simplicity**: Enhance existing components with reasoning capabilities while maintaining current functionality
- **Maintainability**: Use established patterns from the multi-layer agent architecture
- **Reliability**: Graceful degradation when reasoning providers are unavailable
- **Compatibility**: Zero breaking changes to existing non-reasoning workflows

---

## Implementation Strategy

### Architecture Approach
- [x] **Extension**: Extend existing components with new functionality  
- [x] **Targeted Enhancement**: Apply reasoning only to tool selection prompts, preserving existing analysis prompts

**Rationale**: The current multi-layer agent architecture is well-designed and stable. Rather than replacing components, we'll extend LLMClient, BaseAgent, PromptBuilder, and UI components to support reasoning capabilities while maintaining full backward compatibility. Reasoning enhancement is applied selectively to tool selection prompts where decision-making benefits from explicit reasoning, while preserving the excellent structure of existing analysis prompts.

### Component Changes

**Components to Extend:** 
- `backend/tarsy/integrations/llm/client.py`: Add reasoning configuration lookup and enhanced API parameter handling
- `backend/tarsy/agents/base_agent.py`: Integrate reasoning-aware prompt building and response processing
- `backend/tarsy/agents/prompt_builder.py`: Add `<thinking>` encouragement to tool selection prompts when `enable_reasoning: true` is configured
- `backend/tarsy/models/history.py`: Extend LLMInteraction model to capture reasoning data
- `backend/tarsy/hooks/base_hooks.py`: Enhanced LLM interaction logging to extract reasoning
- `dashboard/src/components/SessionDetailPage.tsx`: Add reasoning process display

**New Components:**
- `backend/tarsy/utils/reasoning_extractor.py`: Extract reasoning content from LLM responses using universal `<thinking>` tag parsing
- `dashboard/src/components/ReasoningDisplay.tsx`: Reusable reasoning process display component

### Compatibility Strategy
- **External API Compatibility**: Required - no breaking changes to existing API endpoints
- **Database Compatibility**: Additive schema changes only - new fields added to existing tables
- **Configuration Compatibility**: Full backward compatibility - reasoning features are opt-in and configured per provider

---

## Technical Design

### Data Structures

**Enhanced LLM Provider Configuration:**
```python
# backend/tarsy/integrations/llm/client.py
LLM_PROVIDERS = {
    "openai": {
        "client_factory": lambda temp, api_key, model: ChatOpenAI(
            model_name=model or "gpt-4-1106-preview", 
            temperature=temp, 
            api_key=api_key
        ),
        # No reasoning config = standard model, no special handling
    },
    "gemini": {
        "client_factory": lambda temp, api_key, model: ChatGoogleGenerativeAI(
            model=model or "gemini-2.5-pro-exp-03-25", 
            temperature=temp, 
            google_api_key=api_key
        ),
        "reasoning_params": {
            # API parameters to enable reasoning for hybrid models
            "thinkingConfig": {
                "includeThoughts": True,
                "thinkingBudget": 2000
            }
        }
        # enable_reasoning defaults to False - API handles reasoning mode
    },
    "grok": {
        "client_factory": lambda temp, api_key, model: ChatXAI(
            model_name=model or "grok-3-latest", 
            api_key=api_key, 
            temperature=temp
        ),
        "enable_reasoning": True  # Add <thinking> encouragement to prompts
        # No reasoning_params = standard model, use prompt engineering only
    }
}

# Future reasoning-dedicated providers can be added:
# "openai-o1": {
#     "client_factory": lambda temp, api_key, model: ChatOpenAI(
#         model=model or "o1-preview",
#         temperature=temp,
#         api_key=api_key
#     ),
#     # Pure reasoning model - no config needed, handles reasoning internally
# }
```

**Configuration Options:**
- **`enable_reasoning`**: `true/false` - Whether to add `<thinking>` encouragement to prompts (default: `false`)
- **`reasoning_params`**: `dict` - API parameters to enable reasoning mode for hybrid models (optional)
- **No config**: Standard model with no special reasoning handling

**Modified Data Models:**
```python
# backend/tarsy/models/history.py
class LLMInteraction(SQLModel, table=True):
    # ... existing fields unchanged ...
    reasoning_content: Optional[str] = Field(
        default=None,
        description="Raw reasoning process from LLM (thinking content)"
    )
    reasoning_summary: Optional[str] = Field(
        default=None,
        description="Human-readable summary of reasoning process"
    )
    has_reasoning: bool = Field(
        default=False,
        description="Whether this interaction included reasoning"
    )
```

**New Data Models:**
```python
# backend/tarsy/utils/reasoning_extractor.py
@dataclass
class ReasoningExtraction:
    has_reasoning: bool         # Whether reasoning was found
    raw_reasoning: str         # Raw <thinking> content
    summary: str               # Cleaned summary for display
    final_response: str        # Response without reasoning tags
```

### API Design

**No New API Endpoints Required** - reasoning capabilities are integrated into existing endpoints:

**Enhanced API Responses:**
- Existing history endpoints (`/api/v1/history/sessions/{id}`) will include reasoning data when available
- WebSocket updates include reasoning status for real-time monitoring
- No breaking changes to request/response formats

### Database Design

**Schema Changes:**
- **Modified Tables**: `llm_interactions` - add `reasoning_content`, `reasoning_summary`, `has_reasoning` columns
- **Migration Strategy**: Additive schema migration - existing data unaffected, new fields default to NULL/false

### Integration Points

**Internal Integrations:**
- **LLMClient**: Uses centralized `LLM_PROVIDERS` configuration to read `enable_reasoning` and `reasoning_params` settings
- **BaseAgent**: Receives reasoning configuration from LLMClient and passes to PromptBuilder for tool selection methods
- **PromptBuilder**: Adds `<thinking>` encouragement only to **tool selection prompts** (`build_mcp_tool_selection_prompt`, `build_iterative_mcp_tool_selection_prompt`) when `enable_reasoning: true` is configured
- **History Service**: Always attempts to extract reasoning from responses using universal `<thinking>` tag parsing
- **Dashboard UI**: Displays reasoning processes in session detail views when available

**External Integrations:**
- **OpenAI API**: No special configuration by default, future `openai-o1` provider needs no special handling
- **Google Gemini API**: Uses `reasoning_params` with `thinkingConfig` to enable reasoning via API
- **Provider Configuration**: All reasoning capabilities centrally configured in `LLM_PROVIDERS` dictionary
- **Universal Parsing**: All providers expected to use `<thinking>...</thinking>` tags for reasoning output

---

## Implementation Design

### Core Logic Flow
1. **Provider Configuration Lookup**: LLMClient reads `enable_reasoning` and `reasoning_params` from centralized `LLM_PROVIDERS` dictionary
2. **API Parameter Application**: Apply `reasoning_params` (if present) to LLM API calls to enable reasoning mode
3. **Targeted Prompt Enhancement**: PromptBuilder adds `<thinking>` encouragement only to **tool selection prompts** when `enable_reasoning: true`
4. **Selective LLM Interaction**: Tool selection prompts called with reasoning enhancement; analysis prompts remain unchanged
5. **Universal Response Processing**: All responses parsed for `<thinking>...</thinking>` tags regardless of provider
6. **History Capture**: Reasoning data (when found) stored through existing hook system
7. **UI Display**: Reasoning processes displayed in Dashboard UI when available

### Error Handling Strategy
- **Provider Configuration Missing**: Default to no reasoning configuration, log warning
- **API Parameter Application Failures**: Fall back to standard API calls without reasoning parameters
- **Reasoning Extraction Failures**: Store raw response, continue processing, log error
- **UI Display Errors**: Show "Reasoning unavailable" message, don't break session display

### Security Design
- **Authentication**: Uses existing LLM provider authentication (API keys)
- **Authorization**: No additional authorization - follows existing agent permissions
- **Data Protection**: Reasoning content follows same security as other LLM interactions
- **Input Validation**: Reasoning extraction validates content before storage

### Performance Considerations
- **Optimization Strategy**: Reasoning configuration loaded once at startup, no runtime detection needed
- **Scalability Approach**: Reasoning data stored in existing history database, no additional infrastructure

---

## File Structure

### Files to Create
```
backend/tarsy/utils/
  reasoning_extractor.py     # Extract reasoning from LLM responses using universal <thinking> parsing

dashboard/src/components/
  ReasoningDisplay.tsx       # Reusable reasoning display component
```

### Files to Modify
- `backend/tarsy/integrations/llm/client.py`: Update `LLM_PROVIDERS` with centralized reasoning configuration and add reasoning-aware API calls
- `backend/tarsy/agents/base_agent.py`: Integrate reasoning configuration from LLMClient
- `backend/tarsy/agents/prompt_builder.py`: Add `<thinking>` encouragement when `enable_reasoning: true` is configured
- `backend/tarsy/models/history.py`: Add reasoning fields to LLMInteraction
- `backend/tarsy/hooks/base_hooks.py`: Universal reasoning extraction in LLM hooks using `<thinking>` tag parsing
- `dashboard/src/components/SessionDetailPage.tsx`: Display reasoning in session details

---

## Implementation Guidance

### Key Design Decisions
- **Centralized Configuration**: All reasoning capabilities configured in single `LLM_PROVIDERS` dictionary, reducing complexity and improving maintainability
- **Universal Parsing**: Always parse for `<thinking>` tags regardless of provider, ensuring consistent reasoning capture
- **Flexible Configuration**: Use `enable_reasoning` for prompt encouragement and `reasoning_params` for API-based reasoning enablement
- **Backward Compatibility**: Extend existing components rather than replacing them, ensuring zero breaking changes

### Implementation Priority
1. **Phase 1**: Centralized provider configuration and API parameter handling (LLMClient)
2. **Phase 2**: Reasoning-aware prompt building and universal response parsing (PromptBuilder, ReasoningExtractor)
3. **Phase 3**: History capture and UI display (History hooks, Dashboard UI)

### Risk Areas
- **Provider API Changes**: Hybrid model API parameters may change - mitigate with flexible `reasoning_params` configuration
- **Response Format Assumptions**: Current implementation assumes all models use `<thinking>` tags - can be extended to support different tag formats per provider if needed
- **Performance Impact**: Reasoning responses are slower - mitigate with appropriate timeout handling

### Implementation Details

#### Scope: Targeted Enhancement Strategy

**Enhanced Prompts:**
- `build_mcp_tool_selection_prompt` - Initial tool selection decisions
- `build_iterative_mcp_tool_selection_prompt` - Iterative tool selection and continue/stop decisions

**Unchanged Prompts:**
- `build_analysis_prompt` - Comprehensive alert analysis (already well-structured)
- `build_partial_analysis_prompt` - Intermediate analysis insights
- All other existing prompts remain as-is

**Rationale:** Tool selection requires tactical decision-making that benefits from explicit reasoning, while analysis prompts already provide excellent structure and detailed guidance that could be confused by additional reasoning encouragement.

#### Centralized Provider Configuration
```python
# backend/tarsy/integrations/llm/client.py
class LLMClient:
    def get_reasoning_config(self, provider: str) -> Dict:
        """Get reasoning configuration for provider"""
        provider_config = LLM_PROVIDERS.get(provider, {})
        return {
            "enable_reasoning": provider_config.get("enable_reasoning", False),
            "reasoning_params": provider_config.get("reasoning_params", {})
        }
    
    def build_api_call(self, prompt: str, reasoning_config: Dict) -> Dict:
        """Build API call with reasoning parameters if needed"""
        api_params = {"messages": [{"role": "user", "content": prompt}]}
        
        # Apply reasoning parameters if present (for hybrid models like Gemini)
        if reasoning_config["reasoning_params"]:
            api_params.update(reasoning_config["reasoning_params"])
        
        return api_params
```

#### Targeted Tool Selection Enhancement
```python
# backend/tarsy/agents/prompt_builder.py
def build_mcp_tool_selection_prompt(self, context: PromptContext, reasoning_config: Dict = None) -> str:
    """Build MCP tool selection prompt with optional reasoning enhancement"""
    base_prompt = f"""# MCP Tool Selection Request
Based on the following alert and runbook, determine which MCP tools should be called...
{self._build_alert_section(context.alert_data)}
{self._build_runbook_section(context.runbook_content)}
## Available MCP Tools
{json.dumps(context.available_tools, indent=2)}"""

    # Add reasoning enhancement only for tool selection decisions
    if reasoning_config and reasoning_config.get("enable_reasoning", False):
        base_prompt += """

<thinking>
Let me systematically determine what diagnostic information I need:
1. What specific symptoms and issues does the alert describe?
2. What diagnostic steps does the runbook suggest I should follow?
3. Which MCP tools would provide the specific information needed for those steps?
4. What exact parameters do I need for each tool to get the right data?
</thinking>"""

    base_prompt += """
## Instructions
Analyze the alert and runbook to determine which MCP tools should be called...
"""
    return base_prompt

def build_iterative_mcp_tool_selection_prompt(self, context: PromptContext, reasoning_config: Dict = None) -> str:
    """Build iterative tool selection prompt with optional reasoning enhancement"""
    # Similar pattern for iterative decision-making
    # Analysis prompts (build_analysis_prompt) remain unchanged
```

#### Universal Response Processing
```python
# backend/tarsy/utils/reasoning_extractor.py
def extract_reasoning(response: str) -> ReasoningExtraction:
    """Universal reasoning extraction using <thinking> tags"""
    import re
    
    thinking_match = re.search(r'<thinking>(.*?)</thinking>', response, re.DOTALL)
    
    if thinking_match:
        raw_reasoning = thinking_match.group(1).strip()
        clean_response = re.sub(r'<thinking>.*?</thinking>', '', response, flags=re.DOTALL).strip()
        
        return ReasoningExtraction(
            has_reasoning=True,
            raw_reasoning=raw_reasoning,
            summary=raw_reasoning[:200] + "..." if len(raw_reasoning) > 200 else raw_reasoning,
            final_response=clean_response
        )
    
    return ReasoningExtraction(
        has_reasoning=False,
        raw_reasoning="",
        summary="",
        final_response=response
    )
```

---

## Summary

This centralized configuration approach provides:

### **Benefits:**
- **Single Source of Truth**: All reasoning capabilities configured in one place
- **Easy Extensibility**: Adding new providers or models requires only configuration changes
- **Consistent Behavior**: Universal `<thinking>` tag parsing across all providers
- **Provider Flexibility**: Each provider can use its optimal reasoning enablement method

### **Implementation Phases:**
1. **Phase 1**: Update `LLM_PROVIDERS` with reasoning configuration
2. **Phase 2**: Implement reasoning-aware API calls and prompt building
3. **Phase 3**: Add universal reasoning extraction and UI display

When creating the implementation plan, break this design into specific, testable phases that can be validated independently. Start with Phase 1 (centralized configuration) to establish the foundation before building the reasoning-aware prompt and response processing components.