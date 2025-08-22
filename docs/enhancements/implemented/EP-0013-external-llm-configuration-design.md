# EP-0013: External LLM Provider Configuration Design

## Problem Statement

Current LLM provider configuration is hardcoded in `tarsy/integrations/llm/client.py`, making it inflexible to:
- Configure different base URLs for the same provider type (e.g., OpenAI direct vs OpenAI proxy)
- Override model names per provider instance
- Add new provider configurations without code changes

## Solution Overview

Provide built-in default providers for easy out-of-the-box experience, with optional external YAML file (`config/llm_providers.yaml`) for custom configurations and overrides. Users can start using the system immediately with just GOOGLE_API_KEY (defaults to google-default provider), or set LLM_PROVIDER and corresponding API keys for other providers, or create YAML for advanced configurations.

## Built-in Default Providers

### Available Out-of-the-Box
```python
# OOTB: Just set GOOGLE_API_KEY (defaults to google-default)
# Or override with LLM_PROVIDER and corresponding API key:
# LLM_PROVIDER=openai-default      # gpt-5
# LLM_PROVIDER=google-default      # gemini-2.5-flash (DEFAULT)
# LLM_PROVIDER=xai-default         # grok-4-latest
# LLM_PROVIDER=anthropic-default   # claude-4-sonnet

openai-default:
  type: openai
  model: gpt-5
  api_key_env: OPENAI_API_KEY

google-default:  
  type: google
  model: gemini-2.5-flash
  api_key_env: GOOGLE_API_KEY
  
xai-default:
  type: xai  
  model: grok-4-latest
  api_key_env: XAI_API_KEY
  
anthropic-default:
  type: anthropic
  model: claude-4-sonnet
  api_key_env: ANTHROPIC_API_KEY
```

## Configuration File Structure

### File Location
- `config/llm_providers.yaml` (optional, with `config/llm_providers.yaml.example` template)

### YAML Schema (Optional Configuration)
```yaml
# Optional: Override built-in defaults or add custom providers
llm_providers:
  # Override built-in openai-default with different model
  openai-default:
    type: openai
    model: gpt-4  # Override default gpt-5
    api_key_env: OPENAI_API_KEY
    
  # Add custom OpenAI proxy provider  
  openai-gemini-proxy:
    type: openai
    model: gemini-2.5-pro
    api_key_env: OPENAI_API_KEY
    base_url: https://my-openai-proxy.domain.com:443/v1beta/openai
    
  # Add custom provider with specific model
  gpt-4-turbo:
    type: openai
    model: gpt-4-turbo-preview
    api_key_env: OPENAI_API_KEY
    temperature: 0.0
    
  # Custom Gemini provider
  gemini-2.5-flash:
    type: google
    model: gemini-2.5-flash
    api_key_env: GOOGLE_API_KEY
    
  # Custom Grok provider
  grok-4:
    type: xai
    model: grok-4-latest
    api_key_env: XAI_API_KEY
    
  # Custom Claude provider
  claude-4.1-opus:
    type: anthropic
    model: claude-4.1-opus
    api_key_env: ANTHROPIC_API_KEY
```

### Configuration Priority
1. **YAML providers** (if file exists) - highest priority
2. **Built-in defaults** - fallback for providers not in YAML
3. **Hardcoded fallback** - if YAML file doesn't exist

### Field Definitions
- `type`: Provider type (openai, google, xai, anthropic) - maps to LLM_PROVIDERS function
- `model`: Model name to use
- `api_key_env`: Environment variable name containing API key
- `base_url`: (Optional) Custom base URL, if not specified LangChain uses provider defaults
- `temperature`: (Optional) Default temperature override

## Implementation Changes

### 1. Settings Class (`config/settings.py`)
- Add `llm_config_path: str = Field(default="../config/llm_providers.yaml")`
- Define built-in default providers (openai-default, google-default, xai-default, anthropic-default)
- Set llm_provider to "google-default" for OOTB experience
- Add YAML loading method that merges with built-in defaults
- Update `get_llm_config()` to use merged provider data (YAML + defaults)
- **Rename API key fields and environment variables:**
  - `gemini_api_key` → `google_api_key` (GEMINI_API_KEY → GOOGLE_API_KEY)
  - `grok_api_key` → `xai_api_key` (GROK_API_KEY → XAI_API_KEY)  
  - `openai_api_key` remains unchanged (OPENAI_API_KEY)
  - Add `anthropic_api_key` field (ANTHROPIC_API_KEY)
- Update API key field mappings for google/xai/anthropic provider types

### 2. LLM Client (`integrations/llm/client.py`)
- Update `_create_openai_client()` to accept `base_url` parameter
- Modify all provider functions to accept optional `base_url` parameter
- Update `LLMClient._initialize_client()` to pass base_url from config
- Update LLM_PROVIDERS mapping keys: "gemini" -> "google", "grok" -> "xai", add "anthropic"

### 3. Provider Function Updates
```python
# Current
def _create_openai_client(temp, api_key, model, disable_ssl_verification=False):
    client_kwargs = {
        "base_url": "https://hardcoded-url...",  # Remove this
        
# New
def _create_openai_client(temp, api_key, model, disable_ssl_verification=False, base_url=None):
    client_kwargs = {
        "model_name": model,
        "temperature": temp, 
        "api_key": api_key
    }
    
    # Only set base_url if explicitly provided, otherwise let LangChain use defaults
    if base_url:
        client_kwargs["base_url"] = base_url
```

### 4. Configuration Loading
- Load built-in defaults first (openai-default, google-default, etc.)  
- If YAML exists, load and merge with defaults (YAML overrides defaults)
- If YAML doesn't exist, use only built-in defaults
- Validate required fields (type, model, api_key_env) for all providers
- Only pass base_url to provider functions if specified in configuration

### 5. Environment Template
Update `env.template` with new API key variable names:
```bash
# LLM Provider Configuration
# Built-in providers available out-of-the-box:
# OOTB: Just set GOOGLE_API_KEY to use google-default (gemini-2.5-flash)
# Or override with LLM_PROVIDER:
# - openai-default (gpt-5)
# - google-default (gemini-2.5-flash) [DEFAULT]
# - xai-default (grok-4-latest)  
# - anthropic-default (claude-4-sonnet)

# OOTB setup - just set this and you're ready to go:
GOOGLE_API_KEY=your_google_api_key_here

# Optional: Override LLM provider
# LLM_PROVIDER=google-default

# Optional: Path to custom LLM providers configuration file
# LLM_CONFIG_PATH=./config/llm_providers.yaml
```

## Backwards Compatibility

- Built-in default providers work immediately with just GOOGLE_API_KEY (defaults to google-default, no YAML required)
- If `config/llm_providers.yaml` doesn't exist, use built-in defaults seamlessly  
- `LLM_PROVIDER` environment variable selects which provider to use
- Provider type mappings updated: "gemini" -> "google", "grok" -> "xai", add "anthropic" 
- New default provider names: openai-default, google-default, xai-default, anthropic-default
- **BREAKING CHANGE: API key environment variable names updated (no backward compatibility):**
  - `GEMINI_API_KEY` → `GOOGLE_API_KEY` 
  - `GROK_API_KEY` → `XAI_API_KEY`
  - `OPENAI_API_KEY` remains unchanged
  - New: `ANTHROPIC_API_KEY`

## Validation Requirements

- Validate YAML structure on load
- Ensure required fields present (type, model, api_key_env)
- Validate provider `type` exists in LLM_PROVIDERS (openai, google, xai, anthropic)
- Log warnings for missing API keys  
- Log errors for invalid configurations

## Files to Modify

1. `backend/tarsy/config/settings.py` - Add YAML loading, rename API key fields
2. `backend/tarsy/integrations/llm/client.py` - Update provider functions  
3. `backend/env.template` - Update with new API key variable names and LLM_CONFIG_PATH
4. `backend/config/llm_providers.yaml.example` - Create template
5. Update existing hardcoded `llm_providers` references
6. Update any documentation referencing old API key names (GEMINI_API_KEY, GROK_API_KEY)

## Implementation Steps

1. **Rename API key fields and environment variables** (breaking change)
   - Update Settings class field names: gemini_api_key → google_api_key, grok_api_key → xai_api_key
   - Add anthropic_api_key field
   - Update get_llm_config() method mappings
2. Define built-in default providers in Settings class
3. Add YAML loading and merging logic to Settings class  
4. Update provider functions to accept base_url parameter
5. Modify LLMClient to use merged configuration (defaults + YAML)
6. Create YAML schema and example file
7. Update environment template with new API key variable names
8. Add configuration validation for both defaults and YAML
9. Test OOTB experience with just GOOGLE_API_KEY (no other config)
10. Test built-in providers work out-of-the-box with different LLM_PROVIDER values
11. Test YAML overrides and custom providers

## Success Criteria

- **Ultra-easy setup**: Users can start immediately with just GOOGLE_API_KEY (no other config needed)
- **No configuration required**: Google Gemini works out-of-the-box as the default provider
- **Full flexibility**: Can override built-in providers or add custom ones via YAML
- **Multiple instances**: Can configure multiple OpenAI provider instances with different base URLs
- **Model-aware naming**: Provider names clearly indicate the model (gpt-5, gemini-2.5-flash, etc.)
- **Breaking changes handled**: API key environment variables updated (GEMINI_API_KEY→GOOGLE_API_KEY, GROK_API_KEY→XAI_API_KEY), other configurations continue to work
- **Clear validation**: Configuration errors are logged with helpful messages  
- **Provider type mappings**: Work correctly (google, xai, anthropic) with built-in defaults
