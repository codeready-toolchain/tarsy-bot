"""
Centralized configuration for all built-in agents and MCP servers.

This module serves as the SINGLE SOURCE OF TRUTH for:
- Built-in agent class names and import paths
- Built-in agent mappings (alert type → agent class)
- Built-in MCP server configurations

When adding new built-in agents or MCP servers, edit only this file.
All other modules (AgentFactory, MCPServerRegistry, ConfigurationLoader)
import their built-in definitions from here.

Note: This module contains only data structures to avoid circular imports.
Agent classes are imported dynamically by AgentFactory when needed.
"""

import copy
from typing import Dict, Any
from tarsy.models.llm_models import LLMProviderConfig
from tarsy.models.constants import DEFAULT_LLM_TEMPERATURE
from tarsy.models.mcp_transport_config import TRANSPORT_HTTP, TRANSPORT_STDIO, TRANSPORT_SSE


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
        "transport": {
            "type": TRANSPORT_STDIO,
            "command": "npx",
            "args": ["-y", "kubernetes-mcp-server@0.0.53", "--read-only", "--disable-destructive", "--kubeconfig", "${KUBECONFIG}"]
        },
        # "transport": {
        #     "type": TRANSPORT_SSE,
        #     "url": "http://localhost:8081/sse",
        #     # "bearer_token": "${KUBE_MCP_SERVER_TOKEN}",
        #     # "verify_ssl": False,
        #     "timeout": 10
        # },
        # "transport": {
        #     "type": TRANSPORT_HTTP,
        #     "url": "http://localhost:8081/mcp",
        #     # "bearer_token": "${KUBE_MCP_SERVER_TOKEN}",
        #     # "verify_ssl": False,
        #     "timeout": 10
        # },
        "instructions": """For Kubernetes operations:
- **IMPORTANT: In multi-cluster environments** (when the 'configuration_contexts_list' tool is available):
  * ALWAYS start by calling 'configuration_contexts_list' to see all available contexts and their server URLs
  * Use this information to determine which context to target before performing any operations
  * This prevents working on the wrong cluster and helps you understand the environment
- Be careful with cluster-scoped resource listings in large clusters
- Always prefer namespaced queries when possible
- If you get "server could not find the requested resource" error, check if you're using the namespace parameter correctly:
  * Cluster-scoped resources (Namespace, Node, ClusterRole, PersistentVolume) should NOT have a namespace parameter
  * Namespace-scoped resources (Pod, Deployment, Service, ConfigMap) REQUIRE a namespace parameter""",
        "data_masking": {
            "enabled": True,
            "pattern_groups": ["kubernetes"],  # Expands to kubernetes_secret, api_key, password
            "patterns": ["certificate", "token", "email"]  # Add individual patterns for comprehensive coverage
        }
    },
    # Future MCP servers will be added here:
    # "argocd-server": {
    #     "server_id": "argocd-server", 
    #     "server_type": "argocd",
    #     "enabled": True,
    #     "transport": {
    #         "type": TRANSPORT_STDIO,
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
        "replacement": r'\1 __MASKED_SECRET_DATA__\n',
        "description": "Masks entire Kubernetes data: section in YAML (line-start only, not metadata:)"
    },
    "kubernetes_stringdata_json": {
        "pattern": r'("stringData":)(\{[^}]*\})',
        "replacement": r'\1__MASKED_SECRET_DATA__',
        "description": "Masks stringData objects in JSON (quoted context only)"
    },
    "base64_secret": {
        "pattern": r'\b([A-Za-z0-9+/]{20,}={0,2})\b',
        "replacement": "__MASKED_BASE64_VALUE__",
        "description": "Base64-encoded values in secret contexts (20+ chars)"
    },
    "base64_short": {
        "pattern": r'(?<=:\s)([A-Za-z0-9+/]{4,19}={0,2})(?=\s|$)',
        "replacement": "__MASKED_SHORT_BASE64__",
        "description": "Short base64-encoded values (4-19 chars) after colons in Kubernetes contexts"
    },
    "api_key": {
        "pattern": r'(?i)(?:api[_-]?key|apikey|key)["\']?\s*[:=]\s*["\']?([A-Za-z0-9_\-]{20,})["\']?',
        "replacement": r'"api_key": "__MASKED_API_KEY__"',
        "description": "API keys in various formats"
    },
    "password": {
        "pattern": r'(?i)(?:password|pwd|pass)["\']?\s*[:=]\s*["\']?([^"\'\s\n]{6,})["\']?',
        "replacement": r'"password": "__MASKED_PASSWORD__"',
        "description": "Password fields"
    },
    "certificate": {
        "pattern": r'-----BEGIN [A-Z ]+-----.*?-----END [A-Z ]+-----',
        "replacement": '__MASKED_CERTIFICATE__',
        "description": "SSL/TLS certificates and private keys"
    },
    "certificate_authority_data": {
        "pattern": r'(?i)certificate-authority-data:\s*([A-Za-z0-9+/]{20,}={0,2})',
        "replacement": r'certificate-authority-data: __MASKED_CA_CERTIFICATE__',
        "description": "Certificate authority data in Kubernetes configs and YAML files"
    },
    "email": {
        "pattern": r'(?<!\\)\b[A-Za-z0-9._%+-]+@[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*\.[A-Za-z]{2,63}\b(?!\()',
        "replacement": '__MASKED_EMAIL__',
        "description": "Email addresses"
    },
    "token": {
        "pattern": r'(?i)(?:token|bearer|jwt)["\']?\s*[:=]\s*["\']?([A-Za-z0-9_\-\.]{20,})["\']?',
        "replacement": r'"token": "__MASKED_TOKEN__"',
        "description": "Access tokens, bearer tokens, and JWTs"
    },
    "ssh_key": {
        "pattern": r'ssh-(?:rsa|dss|ed25519|ecdsa)\s+[A-Za-z0-9+/=]+',
        "replacement": "__MASKED_SSH_KEY__",
        "description": "SSH public keys (all common algorithms)"
    }
}

# Central registry of built-in pattern groups for convenient configuration
# Format: "group_name" -> [list_of_pattern_names]
BUILTIN_PATTERN_GROUPS: Dict[str, list[str]] = {
    "basic": ["api_key", "password"],                          # Most common secrets
    "secrets": ["api_key", "password", "token"],               # Basic + tokens  
    "security": ["api_key", "password", "token", "certificate", "certificate_authority_data", "email", "ssh_key"], # Full security focus
    "kubernetes": ["kubernetes_data_section", "kubernetes_stringdata_json", "api_key", "password", "certificate_authority_data"], # Kubernetes-specific - masks data sections and stringData
    "all": ["base64_secret", "base64_short", "api_key", "password", "certificate", "certificate_authority_data", "email", "token", "ssh_key"]  # All patterns
}


# ==============================================================================
# BUILT-IN LLM PROVIDERS
# ==============================================================================

# Central registry of all built-in LLM provider configurations
# Format: "provider-name" -> LLMProviderConfig instance
BUILTIN_LLM_PROVIDERS: Dict[str, LLMProviderConfig] = {
    "openai-default": LLMProviderConfig(
        type="openai",
        model="gpt-5",
        api_key_env="OPENAI_API_KEY",
        temperature=DEFAULT_LLM_TEMPERATURE,
        max_tool_result_tokens=250000  # Conservative for 272K context
    ),
    "google-default": LLMProviderConfig(
        type="google", 
        model="gemini-2.5-pro",
        api_key_env="GOOGLE_API_KEY",
        temperature=DEFAULT_LLM_TEMPERATURE,
        max_tool_result_tokens=950000  # Conservative for 1M context
    ),
    "xai-default": LLMProviderConfig(
        type="xai",
        model="grok-4", 
        api_key_env="XAI_API_KEY",
        temperature=DEFAULT_LLM_TEMPERATURE,
        max_tool_result_tokens=200000  # Conservative for 256K context
    ),
    "anthropic-default": LLMProviderConfig(
        type="anthropic",
        model="claude-sonnet-4-20250514",
        api_key_env="ANTHROPIC_API_KEY",
        temperature=DEFAULT_LLM_TEMPERATURE,
        max_tool_result_tokens=150000  # Conservative for 200K context
    ),
    "vertexai-default": LLMProviderConfig(
        type="vertexai",
        model="claude-sonnet-4-5@20250929",  # Claude Sonnet 4.5 on Vertex AI
        api_key_env="VERTEX_AI_PROJECT",  # Format: "project_id:location" or "project_id"
        temperature=DEFAULT_LLM_TEMPERATURE,
        max_tool_result_tokens=150000  # Conservative for 200K context
    )
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


# ==============================================================================
# BUILT-IN DEFAULT RUNBOOK
# ==============================================================================

DEFAULT_RUNBOOK_CONTENT = """# Generic Troubleshooting Guide

## Investigation Steps

1. **Analyze the alert** - Review the provided alert data and identify the affected system/service
2. **Gather context** - Use available tools to check current system state and recent changes
3. **Identify root cause** - Investigate potential causes based on the alert type and symptoms
4. **Assess impact** - Determine scope and severity of the issue
5. **Recommend actions** - Suggest safe investigation or remediation steps

## Guidelines

- Verify information before suggesting changes
- Consider dependencies and potential side effects
- Document findings and actions taken
"""


# ==============================================================================
# CONVENIENCE ACCESSORS
# ==============================================================================


def get_builtin_llm_providers() -> Dict[str, LLMProviderConfig]:
    """Get all built-in LLM provider configurations."""
    # Create deep copies of BaseModel instances
    return {name: config.model_copy(deep=True) for name, config in BUILTIN_LLM_PROVIDERS.items()}
