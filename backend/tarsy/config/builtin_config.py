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

from typing import Dict, Any


# ==============================================================================
# BUILT-IN AGENT CLASS NAMES
# ==============================================================================

# Central registry of all built-in agent class names
# Format: "ClassName" -> "import.path.ClassName"
BUILTIN_AGENT_CLASS_IMPORTS: Dict[str, str] = {
    "KubernetesAgent": "tarsy.agents.kubernetes_agent.KubernetesAgent",
    # Future agents will be added here:
    # "ArgoCDAgent": "tarsy.agents.argocd_agent.ArgoCDAgent",
    # "KubernetesAWSAgent": "tarsy.agents.kubernetes_aws_agent.KubernetesAWSAgent",
}


# ==============================================================================
# BUILT-IN AGENT MAPPINGS  
# ==============================================================================

# Central registry of alert type to agent class mappings
# Format: "alert_type" -> "ClassName"
BUILTIN_AGENT_MAPPINGS: Dict[str, str] = {
    "kubernetes": "KubernetesAgent",           # Generic kubernetes alerts
    "NamespaceTerminating": "KubernetesAgent", # Specific kubernetes alert type
    # Future mappings will be added here:
    # "argocd": "ArgoCDAgent",
    # "aws-kubernetes": "KubernetesAWSAgent",
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
# CONVENIENCE ACCESSORS
# ==============================================================================

def get_builtin_agent_class_names() -> set[str]:
    """Get all built-in agent class names."""
    return set(BUILTIN_AGENT_CLASS_IMPORTS.keys())


def get_builtin_mcp_server_ids() -> set[str]:
    """Get all built-in MCP server IDs.""" 
    return set(BUILTIN_MCP_SERVERS.keys())


def get_builtin_alert_types() -> set[str]:
    """Get all built-in alert types."""
    return set(BUILTIN_AGENT_MAPPINGS.keys())


def get_builtin_masking_pattern_names() -> set[str]:
    """Get all built-in masking pattern names."""
    return set(BUILTIN_MASKING_PATTERNS.keys())


def get_builtin_pattern_group_names() -> set[str]:
    """Get all built-in pattern group names."""
    return set(BUILTIN_PATTERN_GROUPS.keys()) 