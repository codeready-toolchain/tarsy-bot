# EP-0016: LLM Interaction Content Truncation

## Problem Statement

Even after EP-0015 MCP result summarization, there are **two distinct issues** with oversized content:

### Problem 1: LLM Context Overflow ⚠️
**Location**: MCPResultSummarizer user prompt creation  
**Risk**: LLM API failures when tool result content exceeds context limits
- GPT-5: 272k input tokens ≈ 1MB text
- Gemini 2.5: 1m input tokens ≈ 4MB text  
- Large tool results can exceed these limits

### Problem 2: Hook Layer Performance 📊
**Location**: All LLM interaction hooks (history, dashboard)
**Risk**: System performance degradation across multiple components
1. **Database Storage Bloat**: Large LLM interactions consume excessive database space (history hook)
2. **Dashboard Performance**: Browser struggles to render sessions with massive LLM interactions (dashboard hook)
3. **WebSocket Overhead**: Large payloads slow down real-time dashboard updates (dashboard hook)
4. **Network Transfers**: Large payloads increase bandwidth usage and latency

**Example**: Summarization user prompt can include 1M+ chars of tool result text.

## Solution Overview

Implement **dual-layer truncation** - defense in depth:

1. **Pre-LLM truncation**: Prevent context overflow in MCPResultSummarizer
2. **Post-LLM truncation**: Optimize hook processing for all LLM interaction hooks

**Design Principles:**
- **Provider-aware**: Different LLM context limits
- **Configurable**: Tunable per deployment
- **Safe**: Preserve essential content
- **Transparent**: Clear truncation metadata

## Implementation

### Phase 1: Pre-LLM Truncation (Prevent Context Overflow)

#### 1.1 LLMProviderConfig Type Extension

**Update**: `backend/tarsy/models/llm_models.py`

**Extend `LLMProviderConfig` TypedDict**:

```python
class LLMProviderConfig(TypedDict):
    """Type definition for LLM provider configuration.
    
    Defines the structure for LLM provider configurations including
    required fields (type, model, api_key_env) and optional settings
    (base_url, temperature, verify_ssl, max_tool_result_tokens).
    """
    type: ProviderType
    model: str
    api_key_env: str
    base_url: NotRequired[str]
    temperature: NotRequired[float]
    verify_ssl: NotRequired[bool]
    max_tool_result_tokens: NotRequired[int]
```

#### 1.2 Built-in Provider Configuration

**Update**: `backend/tarsy/config/builtin_config.py`

**Update `BUILTIN_LLM_PROVIDERS`**:

```python
# Central registry of all built-in LLM provider configurations
# Format: "provider-name" -> configuration_dict
BUILTIN_LLM_PROVIDERS: Dict[str, LLMProviderConfig] = {
    "openai-default": {
        "type": "openai",
        "model": "gpt-5",
        "api_key_env": "OPENAI_API_KEY",
        "temperature": DEFAULT_LLM_TEMPERATURE,
        "max_tool_result_tokens": 250000  # Conservative for 272K context
    },
    "google-default": {
        "type": "google", 
        "model": "gemini-2.5-flash",
        "api_key_env": "GOOGLE_API_KEY",
        "temperature": DEFAULT_LLM_TEMPERATURE,
        "max_tool_result_tokens": 950000  # Conservative for 1M context
    },
    "xai-default": {
        "type": "xai",
        "model": "grok-4", 
        "api_key_env": "XAI_API_KEY",
        "temperature": DEFAULT_LLM_TEMPERATURE,
        "max_tool_result_tokens": 200000  # Conservative for 256K context
    },
    "anthropic-default": {
        "type": "anthropic",
        "model": "claude-sonnet-4-20250514",
        "api_key_env": "ANTHROPIC_API_KEY",
        "temperature": DEFAULT_LLM_TEMPERATURE,
        "max_tool_result_tokens": 150000  # Conservative for 200K context
    }
}
```

#### 1.3 Complete Configuration Example

**Update**: `config/llm_providers.yaml.example`

```yaml
# LLM Providers Configuration File with Tool Result Limits
# This file allows you to override built-in default providers or add custom providers

llm_providers:
  # All built-in providers with tool result token limits
  openai-default:
    type: openai
    model: gpt-5
    api_key_env: OPENAI_API_KEY
    max_tool_result_tokens: 250000  # Conservative for 272K context
    
  google-default:
    type: google
    model: gemini-2.5-flash
    api_key_env: GOOGLE_API_KEY
    max_tool_result_tokens: 950000  # Conservative for 1M context
    
  xai-default:
    type: xai
    model: grok-4
    api_key_env: XAI_API_KEY
    max_tool_result_tokens: 200000  # Conservative for 256K context
    
  anthropic-default:
    type: anthropic
    model: claude-sonnet-4-20250514
    api_key_env: ANTHROPIC_API_KEY
    max_tool_result_tokens: 150000  # Conservative for 200K context

  # Custom provider example
  custom-high-capacity:
    type: google
    model: gemini-2.5-pro
    api_key_env: GOOGLE_API_KEY
    max_tool_result_tokens: 950000  # Conservative for 1M context
```

#### 1.4 MCPResultSummarizer Enhancement

**Location**: `backend/tarsy/integrations/mcp/summarizer.py`

**Required imports**:

```python
from typing import Dict, Any, Optional
from tarsy.integrations.llm.client import LLMClient
from tarsy.models.unified_interactions import LLMConversation
from tarsy.utils.logger import logger
```

**Update `__init__()` method** (remove ConfigService dependency):

```python
def __init__(self, llm_client: LLMClient):
    self.llm_client = llm_client
    # ... existing initialization ...
```

**Update `summarize_result()` method**:

```python
async def summarize_result(
    self,
    server_name: str,
    tool_name: str,
    result: Dict[str, Any],
    investigation_conversation: LLMConversation,
    session_id: str,
    stage_execution_id: Optional[str] = None,
    max_summary_tokens: int = 1000
) -> Dict[str, Any]:
    # Extract and potentially truncate result content
    result_content = result.get("result", str(result))
    if isinstance(result_content, dict):
        result_text = json.dumps(result_content, indent=2, default=str)
    else:
        result_text = str(result_content)
    
    # Apply tool result truncation based on current LLM provider limits
    result_text = self._truncate_tool_result_if_needed(result_text)
    
    # ... rest of existing method ...

def _truncate_tool_result_if_needed(self, result_text: str) -> str:
    """Truncate tool result content if it exceeds provider-specific limits."""
    # Get provider-specific limit directly from LLM client
    max_tool_result_tokens = self.llm_client.get_max_tool_result_tokens()
    
    # Rough token estimation: ~4 chars per token
    max_chars = max_tool_result_tokens * 4
    
    if len(result_text) > max_chars:
        truncated_text = result_text[:max_chars]
        original_size = len(result_text)
        
        # Add clear truncation marker
        result_text = (
            truncated_text + 
            f"\n\n[TOOL RESULT TRUNCATED - Original size: {original_size:,} chars, "
            f"Truncated to: {max_chars:,} chars for LLM context limits]"
        )
        
        logger.info(
            f"Truncated tool result from {original_size:,} to {len(result_text):,} chars "
            f"(limit: {max_tool_result_tokens:,} tokens)"
        )
    
    return result_text
```

#### 1.5 Required Dependency Methods

**LLMClient Enhancement**:

**Update**: `backend/tarsy/integrations/llm/client.py`

**Required imports**:

```python
from tarsy.models.llm_models import LLMProviderConfig
from tarsy.utils.logger import logger
```

```python
class LLMClient:
    def __init__(self, provider_name: str, provider_config: LLMProviderConfig):
        """Initialize LLM client with provider name and config."""
        self.provider_name = provider_name
        self.provider_config = provider_config
        # ... existing initialization ...
    
    def get_max_tool_result_tokens(self) -> int:
        """Return the maximum tool result tokens for the current provider."""
        try:
            max_tokens = self.provider_config.get("max_tool_result_tokens")
            if max_tokens is not None:
                return int(max_tokens)
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid max_tool_result_tokens in provider config: {e}")
        
        # Fallback to safe default for most models
        default_limit = 150000  # Conservative limit that works for most providers
        logger.info(f"Using default tool result limit: {default_limit:,} tokens")
        return default_limit
    
    # ... existing methods ...
```

### Phase 2: Post-LLM Truncation (Hook Layer Optimization)

#### 2.1 Global Constant

**Location**: `backend/tarsy/models/constants.py`

```python
# Maximum size for LLM interaction message content before hook processing
MAX_LLM_MESSAGE_CONTENT_SIZE = 1048576  # 1MB
```

#### 2.2 Base Hook Enhancement with Truncation

**Location**: `backend/tarsy/hooks/typed_context.py`

**Add truncation utility method**:

```python
from tarsy.models.constants import MAX_LLM_MESSAGE_CONTENT_SIZE
from tarsy.models.unified_interactions import MessageRole

def _apply_llm_interaction_truncation(interaction: LLMInteraction) -> LLMInteraction:
    """Apply content truncation to LLM interaction for hook processing."""
    if not interaction.conversation:
        return interaction
        
    truncated_conversation = interaction.conversation.model_copy(deep=True)
    truncation_applied = False
    
    for message in truncated_conversation.messages:
        # Only truncate user messages for hook processing
        if (message.role == MessageRole.USER and 
            len(message.content) > MAX_LLM_MESSAGE_CONTENT_SIZE):
            
            original_size = len(message.content)
            message.content = (
                message.content[:MAX_LLM_MESSAGE_CONTENT_SIZE] + 
                f"\n\n[HOOK TRUNCATED - Original size: {original_size:,} chars, "
                f"Hook size: {MAX_LLM_MESSAGE_CONTENT_SIZE:,} chars]"
            )
            truncation_applied = True
    
    if truncation_applied:
        # Create new interaction with truncated conversation
        truncated_interaction = interaction.model_copy()
        truncated_interaction.conversation = truncated_conversation
        return truncated_interaction
    
    return interaction
```

#### 2.3 Hook Layer Enhancements

**Location**: `backend/tarsy/hooks/typed_history_hooks.py`

**Update `TypedLLMHistoryHook.execute()`**:

```python
async def execute(self, interaction: LLMInteraction) -> None:
    """Log LLM interaction to history database with content truncation."""
    try:
        # Apply content truncation before database write
        truncated_interaction = _apply_llm_interaction_truncation(interaction)
        
        ok = await asyncio.to_thread(
            self.history_service.store_llm_interaction, truncated_interaction
        )
        # ... existing logging logic ...
    except Exception as e:
        # ... existing error handling ...
```

**Location**: `backend/tarsy/hooks/typed_dashboard_hooks.py`

**Update `TypedLLMDashboardHook.execute()`**:

```python
async def execute(self, interaction: LLMInteraction) -> None:
    """Broadcast LLM interaction to dashboard with content truncation."""
    try:
        # Apply content truncation before WebSocket broadcast
        truncated_interaction = _apply_llm_interaction_truncation(interaction)
        
        # ... existing dashboard broadcast logic using truncated_interaction ...
        
    except Exception as e:
        # ... existing error handling ...
```

#### 2.4 Import Additions

**Location**: `backend/tarsy/hooks/typed_history_hooks.py`
**Location**: `backend/tarsy/hooks/typed_dashboard_hooks.py`

```python
from tarsy.hooks.typed_context import _apply_llm_interaction_truncation
```
