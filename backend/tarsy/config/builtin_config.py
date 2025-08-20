"""
Centralized configuration for all built-in agents and MCP servers.

This module serves as the SINGLE SOURCE OF TRUTH for:
- Built-in agent class names and import paths
- Built-in agent mappings (alert type → agent class)
- Built-in MCP server configurations

When adding new built-in agents or MCP servers, edit only this file.
All other modules (AgentRegistry, AgentFactory, MCPServerRegistry, ConfigurationLoader)
import their built-in definitions from here.

Note: This module contains only data structures to avoid circular imports.
Agent classes are imported dynamically by AgentFactory when needed.
"""

import copy
from typing import Dict, Any


# ==============================================================================
# BUILT-IN AGENTS (Single source of truth)
# ==============================================================================

# Central registry of all built-in agents, including import path and metadata
# Format: "ClassName" -> { "import": "module.Class", "iteration_strategy": IterationStrategy, ... }
BUILTIN_AGENTS: Dict[str, Dict[str, Any]] = {
    "KubernetesAgent": {
        "import": "tarsy.agents.kubernetes_agent.KubernetesAgent",
        # Store as plain string to avoid importing agent enums here (prevents circular imports)
        "iteration_strategy": "react",  # ReAct strategy for complex k8s troubleshooting
        "description": "Kubernetes-specialized agent using ReAct pattern for systematic analysis",
    },
    # Future agents will be added here:
    # "ArgoCDAgent": {
    #     "import": "tarsy.agents.argocd_agent.ArgoCDAgent",
    #     "iteration_strategy": "react",
    #     "description": "ArgoCD-specialized agent using ReAct pattern for deployment analysis",
    # },
}


# ==============================================================================
# BUILT-IN CHAIN DEFINITIONS (Replace BUILTIN_AGENT_MAPPINGS)
# ==============================================================================

# Built-in chain definitions as single source of truth
# Convert existing single-agent mappings to 1-stage chains and add multi-stage examples
BUILTIN_CHAIN_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    # Convert existing single-agent mappings to 1-stage chains
    "kubernetes-agent-chain": {
        "alert_types": ["kubernetes", "NamespaceTerminating"],
        "stages": [
            {"name": "analysis", "agent": "KubernetesAgent"}
        ],
        "description": "Single-stage Kubernetes analysis"
    },
    
    # Example multi-agent chain (future capability)
    #"kubernetes-troubleshooting-chain": {
    #    "alert_types": ["KubernetesIssue", "PodFailure"],
    #    "stages": [
    #        {"name": "data-collection", "agent": "KubernetesAgent"},
    #        {"name": "root-cause-analysis", "agent": "KubernetesAgent"}
    #    ],
    #    "description": "Multi-stage Kubernetes troubleshooting workflow"
    #}
}


# ==============================================================================
# BUILT-IN MCP SERVERS
# ==============================================================================

# Central registry of all built-in MCP server configurations
# Format: "server-id" -> configuration_dict
BUILTIN_MCP_SERVERS: Dict[str, Dict[str, Any]] = {
    "kubernetes-server": {
        "server_id": "kubernetes-server",
        "server_type": "kubernetes",
        "enabled": True,
        "connection_params": {
            "command": "npx",
            "args": ["-y", "kubernetes-mcp-server@latest", "--read-only", "--disable-destructive", "--kubeconfig", "${KUBECONFIG}"]
        },
        "instructions": """For Kubernetes operations:
- Be careful with cluster-scoped resource listings in large clusters
- Always prefer namespaced queries when possible
- Use kubectl explain for resource schema information
- Check resource quotas before creating new resources""",
        "data_masking": {
            "enabled": True,
            "pattern_groups": ["kubernetes"],  # Expands to kubernetes_secret, api_key, password
            "patterns": ["certificate", "token"]  # Add individual patterns for comprehensive coverage
        }
    },
    # Future MCP servers will be added here:
    # "argocd-server": {
    #     "server_id": "argocd-server", 
    #     "server_type": "argocd",
    #     "enabled": True,
    #     "connection_params": {
    #         "command": "npx",
    #         "args": ["-y", "argocd-mcp-server@latest", "--server", "${ARGOCD_SERVER}", "--auth-token", "${ARGOCD_TOKEN}"]
    #     },
    #     "instructions": "ArgoCD-specific instructions..."
    # },
}


# ==============================================================================
# BUILT-IN MASKING PATTERNS
# ==============================================================================

# Central registry of all built-in masking patterns for MCP server responses
# Format: "pattern_name" -> {"pattern": regex, "replacement": text, "description": text}
BUILTIN_MASKING_PATTERNS: Dict[str, Dict[str, str]] = {
    "kubernetes_data_section": {
        "pattern": r'^(data:)(\s*\n(?:\s+[^:\n]+:[^\n]*\n?)*)',
        "replacement": r'\1 ***MASKED_SECRET_DATA***\n',
        "description": "Masks entire Kubernetes data: section in YAML (line-start only, not metadata:)"
    },
    "kubernetes_stringdata_json": {
        "pattern": r'("stringData":)(\{[^}]*\})',
        "replacement": r'\1***MASKED_SECRET_DATA***',
        "description": "Masks stringData objects in JSON (quoted context only)"
    },
    "base64_secret": {
        "pattern": r'\b([A-Za-z0-9+/]{20,}={0,2})\b',
        "replacement": "***MASKED_BASE64_VALUE***",
        "description": "Base64-encoded values in secret contexts (20+ chars)"
    },
    "base64_short": {
        "pattern": r'(?<=:\s)([A-Za-z0-9+/]{4,19}={0,2})(?=\s|$)',
        "replacement": "***MASKED_SHORT_BASE64***",
        "description": "Short base64-encoded values (4-19 chars) after colons in Kubernetes contexts"
    },
    "api_key": {
        "pattern": r'(?i)(?:api[_-]?key|apikey|key)["\']?\s*[:=]\s*["\']?([A-Za-z0-9_\-]{20,})["\']?',
        "replacement": r'"api_key": "***MASKED_API_KEY***"',
        "description": "API keys in various formats"
    },
    "password": {
        "pattern": r'(?i)(?:password|pwd|pass)["\']?\s*[:=]\s*["\']?([^"\'\s\n]{6,})["\']?',
        "replacement": r'"password": "***MASKED_PASSWORD***"',
        "description": "Password fields"
    },
    "certificate": {
        "pattern": r'-----BEGIN [A-Z ]+-----.*?-----END [A-Z ]+-----',
        "replacement": '***MASKED_CERTIFICATE***',
        "description": "SSL/TLS certificates and private keys"
    },
    "token": {
        "pattern": r'(?i)(?:token|bearer|jwt)["\']?\s*[:=]\s*["\']?([A-Za-z0-9_\-\.]{20,})["\']?',
        "replacement": r'"token": "***MASKED_TOKEN***"',
        "description": "Access tokens, bearer tokens, and JWTs"
    }
}

# Central registry of built-in pattern groups for convenient configuration
# Format: "group_name" -> [list_of_pattern_names]
BUILTIN_PATTERN_GROUPS: Dict[str, list[str]] = {
    "basic": ["api_key", "password"],                          # Most common secrets
    "secrets": ["api_key", "password", "token"],               # Basic + tokens  
    "security": ["api_key", "password", "token", "certificate"], # Full security focus
    "kubernetes": ["kubernetes_data_section", "kubernetes_stringdata_json", "api_key", "password"], # Kubernetes-specific - masks data sections and stringData
    "all": ["base64_secret", "base64_short", "api_key", "password", "certificate", "token"]  # All patterns
}


# ==============================================================================
# BUILT-IN LLM PROVIDERS
# ==============================================================================

# Central registry of all built-in LLM provider configurations
# Format: "provider-name" -> configuration_dict
BUILTIN_LLM_PROVIDERS: Dict[str, Dict[str, Any]] = {
    "openai-default": {
        "type": "openai",
        "model": "gpt-5",
        "api_key_env": "OPENAI_API_KEY"
    },
    "google-default": {
        "type": "google", 
        "model": "gemini-2.5-flash",
        "api_key_env": "GOOGLE_API_KEY"
    },
    "xai-default": {
        "type": "xai",
        "model": "grok-4-latest", 
        "api_key_env": "XAI_API_KEY"
    },
    "anthropic-default": {
        "type": "anthropic",
        "model": "claude-4-sonnet",
        "api_key_env": "ANTHROPIC_API_KEY"
    }
}


# ==============================================================================
# CONVENIENCE ACCESSORS
# ==============================================================================

def get_builtin_agent_class_names() -> set[str]:
    """Get all built-in agent class names."""
    return set(BUILTIN_AGENTS.keys())


def get_builtin_mcp_server_ids() -> set[str]:
    """Get all built-in MCP server IDs."""
    return set(BUILTIN_MCP_SERVERS.keys())


def get_builtin_agent_config(agent_class_name: str) -> Dict[str, Any]:
    """Get configuration for a built-in agent class (includes import and metadata)."""
    return BUILTIN_AGENTS.get(agent_class_name, {})


def get_builtin_agent_import_mapping() -> Dict[str, str]:
    """Get mapping of built-in agent class names to their import paths."""
    return {name: meta.get("import", "") for name, meta in BUILTIN_AGENTS.items()}


def get_builtin_chain_definitions() -> Dict[str, Dict[str, Any]]:
    """Get all built-in chain definitions."""
    return copy.deepcopy(BUILTIN_CHAIN_DEFINITIONS)


def get_builtin_llm_providers() -> Dict[str, Dict[str, Any]]:
    """Get all built-in LLM provider configurations."""
    return copy.deepcopy(BUILTIN_LLM_PROVIDERS)
