"""
Pytest configuration and fixtures for integration tests.

This module provides fixtures for mocking external services in e2e tests.
"""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
from sqlmodel import Session, SQLModel, create_engine

from tarsy.agents.kubernetes_agent import KubernetesAgent
from tarsy.config.settings import Settings
from tarsy.integrations.llm.client import LLMClient, LLMManager
from tarsy.integrations.mcp.client import MCPClient
from tarsy.models.agent_execution_result import AgentExecutionResult
from tarsy.models.alert import Alert
from tarsy.models.constants import StageStatus
from tarsy.models.db_models import AlertSession
from tarsy.models.unified_interactions import LLMInteraction, MCPInteraction
from tarsy.models.agent_config import MCPServerConfigModel as MCPServerConfig
from tarsy.utils.timestamp import now_us
from tarsy.services.agent_factory import AgentFactory
from tarsy.services.agent_registry import AgentRegistry
from tarsy.services.alert_service import AlertService
from tarsy.services.history_service import HistoryService
from tarsy.services.mcp_server_registry import MCPServerRegistry
from tarsy.services.runbook_service import RunbookService


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    settings = Mock(spec=Settings)
    settings.gemini_api_key = "mock-gemini-key"
    settings.openai_api_key = "mock-openai-key"
    settings.github_token = "mock-github-token"
    settings.default_llm_provider = "gemini"
    settings.max_llm_mcp_iterations = 3
    settings.log_level = "INFO"
    settings.agent_config_path = None  # No agent config for integration tests
    
    # History/Database settings - use in-memory database for integration tests
    settings.history_enabled = True
    settings.history_database_url = "sqlite:///:memory:"
    
    # LLM providers configuration that LLMManager expects
    settings.llm_providers = {
        "gemini": {
            "model": "gemini-2.5-pro",
            "api_key_env": "GEMINI_API_KEY",
            "type": "gemini"
        },
        "openai": {
            "model": "gpt-4-1106-preview",
            "api_key_env": "OPENAI_API_KEY", 
            "type": "openai"
        }
    }
    
    # Mock the get_llm_config method that Settings class provides
    def mock_get_llm_config(provider: str):
        if provider not in settings.llm_providers:
            raise ValueError(f"Unsupported LLM provider: {provider}")
        config = settings.llm_providers[provider].copy()
        if provider == "gemini":
            config["api_key"] = settings.gemini_api_key
        elif provider == "openai":
            config["api_key"] = settings.openai_api_key
        return config
    
    settings.get_llm_config = mock_get_llm_config
    return settings


@pytest.fixture(scope="function")
def ensure_integration_test_isolation(mock_settings, monkeypatch):
    """Ensure integration tests use mock settings and don't get contaminated by e2e tests.
    
    This fixture is now opt-in - tests that need this isolation must explicitly use it.
    """
    # CRITICAL: Reset the global history service singleton to prevent e2e contamination
    import tarsy.services.history_service
    original_history_service = getattr(tarsy.services.history_service, '_history_service', None)
    
    # Only reset if it exists and is initialized
    if original_history_service is not None:
        tarsy.services.history_service._history_service = None
    
    # Force patch the settings globally for every integration test
    monkeypatch.setattr("tarsy.config.settings.get_settings", lambda: mock_settings)
    
    # Also ensure environment variables don't leak from e2e tests
    monkeypatch.delenv("HISTORY_DATABASE_URL", raising=False)
    monkeypatch.setenv("TESTING", "true")
    
    yield
    
    # Restore the original history service state only if we modified it
    if original_history_service is not None:
        tarsy.services.history_service._history_service = original_history_service


@pytest.fixture
def sample_alert():
    """Create a sample alert for testing."""
    return Alert(
        alert_type="kubernetes",
        runbook="https://github.com/company/runbooks/blob/main/k8s-namespace-terminating.md",
        severity="high",
        timestamp=1704110400000000,  # Fixed timestamp for testing
        data={
            "environment": "production",
            "cluster": "https://k8s-cluster.example.com",
            "namespace": "stuck-namespace",
            "pod": "problematic-pod-12345",
            "message": "Namespace 'stuck-namespace' has been in Terminating state for 30+ minutes",
            "context": "Multiple pods in the namespace are stuck with finalizers",
            "alert": "NamespaceTerminating"
        }
    )


@pytest.fixture
def sample_runbook_content():
    """Sample runbook content for testing."""
    return """# Kubernetes Namespace Stuck in Terminating

## Overview
This runbook helps resolve issues where a Kubernetes NamespaceTerminating state.

## Steps
1. Check for pods with finalizers
2. Examine resource quotas
3. Check for stuck resources
4. Review finalizer cleanup

## Commands
- `kubectl get namespace <name> -o yaml`
- `kubectl get pods -n <name>`
- `kubectl patch pod <pod-name> -n <name> -p '{"metadata":{"finalizers":null}}'`
"""


@pytest.fixture
def mock_llm_client():
    """Mock LLM client for testing."""
    client = Mock(spec=LLMClient)
    client.available = True
    
    # Mock successful responses
    async def mock_generate_response(messages, session_id, **kwargs):
        """Generate mock responses based on message content."""
        if not session_id:
            raise ValueError("session_id is required for LLM interactions")
        
        if not messages:
            return "No analysis available"
        
        user_content = ""
        for msg in messages:
            if hasattr(msg, 'content') and 'tool' in msg.content.lower():
                user_content = msg.content
                break
        
        # Mock tool selection response
        if "select tools" in user_content.lower() or "mcp tools" in user_content.lower():
            return '''```json
[
    {
        "server": "kubernetes-server",
        "tool": "kubectl_get_namespace",
        "parameters": {"namespace": "stuck-namespace"},
        "reason": "Check namespace status and finalizers"
    },
    {
        "server": "kubernetes-server", 
        "tool": "kubectl_get_pods",
        "parameters": {"namespace": "stuck-namespace"},
        "reason": "List pods in the terminating namespace"
    }
]
```'''
        
        # Mock continue/stop decision
        if "continue" in user_content.lower() and "next" in user_content.lower():
            return '''```json
{
    "continue": false,
    "reason": "Sufficient data collected for analysis"
}
```'''
        
        # Mock final analysis
        return """## Analysis Results

**Issue Identified**: The namespace 'stuck-namespace' is stuck in Terminating state due to pods with finalizers.

**Root Cause**: Pods in the namespace have finalizers that are preventing clean deletion.

**Resolution Steps**:
1. Identify pods with finalizers using kubectl
2. Remove finalizers manually if safe to do so
3. Force delete remaining resources if necessary

**Immediate Actions**:
- Check pod finalizers: `kubectl get pods -n stuck-namespace -o yaml`
- Remove finalizers: `kubectl patch pod <pod-name> -n stuck-namespace -p '{"metadata":{"finalizers":null}}'`

**Status**: Issue can be resolved by removing pod finalizers"""
    
    client.generate_response = AsyncMock(side_effect=mock_generate_response)
    return client


@pytest.fixture
def mock_llm_manager():
    """Mock LLM manager for testing."""
    manager = Mock(spec=LLMManager)
    manager.is_available.return_value = True
    manager.list_available_providers.return_value = ["gemini", "openai"]
    manager.get_availability_status.return_value = {"gemini": "available", "openai": "available"}
    
    # Create mock client
    mock_client = Mock(spec=LLMClient)
    mock_client.available = True
    
    def mock_generate_response_sync(messages, session_id, stage_execution_id=None, **kwargs):
        """Generate mock responses based on message content."""
        if not session_id:
            raise ValueError("session_id is required for LLM interactions")
        
        if not messages:
            return "No analysis available"
        
        user_content = ""
        system_content = ""
        for msg in messages:
            if hasattr(msg, 'content') and msg.content:
                if hasattr(msg, 'role'):
                    if msg.role == "system":
                        system_content += str(msg.content)
                    elif msg.role == "user":
                        user_content += str(msg.content)
                else:
                    user_content += str(msg.content)
        
        # Determine response type based on content
        combined_content = (user_content + " " + system_content).lower()
        
        # Mock tool selection response (initial)
        if ("select tools" in combined_content or "mcp tool selection" in combined_content) and "iterative" not in combined_content:
            return '''```json
[
    {
        "server": "kubernetes-server",
        "tool": "kubectl_get_namespace", 
        "parameters": {"namespace": "stuck-namespace"},
        "reason": "Check namespace status and finalizers"
    }
]
```'''
        
        # Mock iterative tool selection (continue/stop decision)
        if "iterative" in combined_content or "continue" in combined_content:
            return '''```json
{"continue": false, "reason": "Analysis complete"}
```'''
        
        # Mock final analysis
        return "**Analysis**: Namespace stuck due to finalizers. Remove finalizers to resolve."
    
    # Create AsyncMock that can track calls and return dynamic responses
    mock_client.generate_response = AsyncMock(side_effect=mock_generate_response_sync)
    manager.get_client.return_value = mock_client
    return manager


@pytest.fixture
def mock_mcp_server_config():
    """Mock MCP server configuration."""
    return MCPServerConfig(
        server_id="kubernetes-server",
        server_type="kubernetes",
        enabled=True,
        connection_params={
            "command": "npx",
            "args": ["-y", "kubernetes-mcp-server@latest"]
        },
        instructions="Kubernetes server instructions for testing"
    )


@pytest.fixture
def mock_mcp_server_registry(mock_mcp_server_config):
    """Mock MCP server registry."""
    registry = Mock(spec=MCPServerRegistry)
    registry.get_server_configs.return_value = [mock_mcp_server_config]
    registry.get_server_config.return_value = mock_mcp_server_config
    registry.get_all_server_ids.return_value = ["kubernetes-server"]
    return registry


@pytest.fixture
def mock_mcp_client():
    """Mock MCP client for testing."""
    client = Mock(spec=MCPClient)
    
    # Mock initialization
    client.initialize = AsyncMock()
    client.close = AsyncMock()
    
    # Mock tool listing - use simpler return structure
    def mock_list_tools_sync(session_id, server_name=None, stage_execution_id=None):
        """Mock tool listing response - synchronous version."""
        if server_name == "kubernetes-server":
            return {
                "kubernetes-server": [
                    {
                        "name": "kubectl_get_namespace",
                        "description": "Get namespace information",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "namespace": {"type": "string", "description": "Namespace name"}
                            },
                            "required": ["namespace"]
                        }
                    },
                    {
                        "name": "kubectl_get_pods", 
                        "description": "List pods in namespace",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "namespace": {"type": "string", "description": "Namespace name"}
                            },
                            "required": ["namespace"]
                        }
                    }
                ]
            }
        return {}
    
    # Use AsyncMock with side_effect to track calls and return dynamic responses
    client.list_tools = AsyncMock(side_effect=mock_list_tools_sync)
    
    # Mock tool execution - use simpler return structure  
    def mock_call_tool_sync(server_name, tool_name, parameters):
        """Mock tool execution response - synchronous version."""
        if server_name == "kubernetes-server":
            if tool_name == "kubectl_get_namespace":
                return {
                    "status": "success",
                    "output": """NAME             STATUS        AGE
stuck-namespace  Terminating   45m"""
                }
            elif tool_name == "kubectl_get_pods":
                return {
                    "status": "success", 
                    "output": """NAME                    READY   STATUS        RESTARTS   AGE
problematic-pod-12345   0/1     Terminating   0          45m"""
                }
        return {"status": "error", "output": "Tool not found"}
    
    # Use AsyncMock with side_effect to track calls and return dynamic responses
    client.call_tool = AsyncMock(side_effect=mock_call_tool_sync)
    return client


@pytest.fixture
def mock_runbook_service(sample_runbook_content):
    """Mock runbook service."""
    service = Mock(spec=RunbookService)
    service.download_runbook = AsyncMock(return_value=sample_runbook_content)
    service.close = AsyncMock()
    return service


@pytest.fixture
def mock_agent_registry():
    """Mock chain registry (adapted from agent registry)."""
    from tarsy.services.chain_registry import ChainRegistry
    from tarsy.models.agent_config import ChainConfigModel, ChainStageConfigModel
    registry = Mock(spec=ChainRegistry)
    
    # Dynamic chain routing based on alert type
    def get_chain_for_alert_type(alert_type):
        agent = "KubernetesAgent" if alert_type == "kubernetes" else "BaseAgent"
        return ChainConfigModel(
            chain_id=f'{alert_type}-chain',
            alert_types=[alert_type],
            stages=[ChainStageConfigModel(name='analysis', agent=agent)],
            description=f'Test chain for {alert_type}'
        )
    
    registry.get_chain_for_alert_type.side_effect = get_chain_for_alert_type
    registry.list_available_alert_types.return_value = ["kubernetes", "monitoring", "database", "network"]
    return registry


@pytest.fixture
def mock_agent_factory(mock_llm_manager, mock_mcp_client):
    """Mock agent factory."""
    factory = Mock(spec=AgentFactory)
    
    # Create a semi-mocked agent that calls dependencies but returns controlled results
    def create_mock_agent(agent_class_name, iteration_strategy=None):
        if agent_class_name == "KubernetesAgent":
            mock_agent = Mock(spec=KubernetesAgent)
            mock_agent.set_current_stage_execution_id = Mock()
            
            # Mock the process_alert method with NEW signature to match BaseAgent
            async def mock_kubernetes_process_alert(chain_context):
                if not chain_context.session_id:
                    raise ValueError("session_id is required for alert processing")
                
                # Simulate calling LLM client multiple times as a real agent would
                llm_client = mock_llm_manager.get_client()
                
                # Call for tool selection (initial)
                await llm_client.generate_response([
                    Mock(role="system", content="You are an expert SRE analyzing Kubernetes namespace issues. Use available MCP tools to diagnose problems."),
                    Mock(role="user", content="select tools for Kubernetes namespace analysis")
                ], session_id=chain_context.session_id)
                
                # Call for iterative decision
                await llm_client.generate_response([
                    Mock(role="system", content="You are an expert SRE with Kubernetes expertise. Determine if more analysis is needed."), 
                    Mock(role="user", content="iterative analysis - should we continue?")
                ], session_id=chain_context.session_id)
                
                # Call for final analysis
                analysis_result = await llm_client.generate_response([
                    Mock(role="system", content="You are an expert SRE specializing in Kubernetes troubleshooting. Provide actionable analysis."),
                    Mock(role="user", content="final analysis of namespace issue")
                ], session_id=chain_context.session_id)
                
                # Extract namespace from alert data for tool calls
                namespace = chain_context.alert_data.get('namespace', 'default')
                
                # Simulate calling MCP client for tool listing and execution (iterative analysis)
                await mock_mcp_client.list_tools(session_id=chain_context.session_id, server_name="kubernetes-server")
                await mock_mcp_client.call_tool("kubernetes-server", "kubectl_get_namespace", {"namespace": namespace})
                
                # Create comprehensive analysis including all relevant data from the alert
                alert_data = chain_context.alert_data
                analysis_parts = [f"Namespace '{namespace}' analyzed."]
                
                # Include service-specific information
                if 'service' in alert_data:
                    analysis_parts.append(f"Service: {alert_data['service']}")
                if 'database_type' in alert_data:
                    analysis_parts.append(f"Database type: {alert_data['database_type']}")
                if 'alert' in alert_data and alert_data['alert'] != namespace:
                    analysis_parts.append(f"Alert type: {alert_data['alert']}")
                
                # Include metrics and other nested objects if present
                for data_key, data_value in alert_data.items():
                    if isinstance(data_value, dict) and data_key not in ['labels', 'tags']:  # Already handled separately
                        # Add the key itself as context
                        analysis_parts.append(f"{data_key} analysis")
                        # Add nested values
                        for key, value in data_value.items():
                            if isinstance(value, (int, float)):
                                analysis_parts.append(f"{key}: {value}")
                            elif isinstance(value, dict):
                                for subkey, subvalue in value.items():
                                    analysis_parts.append(f"{key}.{subkey}: {subvalue}")
                
                # Include labels if present
                if 'labels' in alert_data and isinstance(alert_data['labels'], dict):
                    for key, value in alert_data['labels'].items():
                        analysis_parts.append(f"{key}: {value}")
                
                # Include tags if present
                if 'tags' in alert_data and isinstance(alert_data['tags'], list):
                    for tag in alert_data['tags']:
                        analysis_parts.append(f"tag: {tag}")
                
                # Include yaml_config if present
                if 'yaml_config' in alert_data and alert_data['yaml_config']:
                    if 'ConfigMap' in alert_data['yaml_config']:
                        analysis_parts.append("ConfigMap configuration detected")
                    if 'monitoring-config' in alert_data['yaml_config']:
                        analysis_parts.append("monitoring-config settings found")
                
                # Include array data structures
                for key, value in alert_data.items():
                    if isinstance(value, list) and value:
                        for item in value:
                            if isinstance(item, dict):
                                # Extract node names from cluster_nodes arrays
                                if 'node' in item:
                                    analysis_parts.append(f"node: {item['node']}")
                                # Extract other meaningful keys from array items
                                for subkey, subvalue in item.items():
                                    if isinstance(subvalue, str) and len(subvalue) < 50:
                                        analysis_parts.append(f"{subkey}: {subvalue}")
                
                # Infer context from runbook URL or content
                runbook_content = chain_context.runbook_content or ""
                # Also check if there's a runbook field in the alert data
                if 'runbook' in alert_data:
                    runbook_content += " " + str(alert_data['runbook'])
                
                if isinstance(runbook_content, str):
                    if 'network' in runbook_content.lower():
                        analysis_parts.append("network analysis performed")
                    if 'database' in runbook_content.lower():
                        analysis_parts.append("database analysis performed")
                    if 'monitoring' in runbook_content.lower():
                        analysis_parts.append("monitoring analysis performed")
                
                analysis_text = " ".join(analysis_parts) + " Analysis includes tool execution results."
                
                return AgentExecutionResult(
                    status=StageStatus.COMPLETED,
                    agent_name="KubernetesAgent",
                    timestamp_us=now_us(),
                    result_summary=analysis_text,
                    final_analysis=analysis_text  # Set final_analysis so alert service can extract it
                )
            
            mock_agent.process_alert.side_effect = mock_kubernetes_process_alert
            
        elif agent_class_name == "BaseAgent":
            from tarsy.agents.base_agent import BaseAgent
            mock_agent = Mock(spec=BaseAgent)
            mock_agent.set_current_stage_execution_id = Mock()
            
            # Mock the process_alert method for flexible alerts with NEW signature
            async def mock_base_process_alert(chain_context):
                if not chain_context.session_id:
                    raise ValueError("session_id is required for alert processing")
                
                # Simulate calling LLM client for flexible alert analysis
                llm_client = mock_llm_manager.get_client()
                
                # Generate analysis that includes comprehensive alert data content
                # Determine service/entity name from different alert types
                alert_data = chain_context.alert_data
                service_name = "unknown service"
                if 'service' in alert_data:
                    service_name = alert_data['service']
                elif 'db_type' in alert_data:
                    service_name = f"{alert_data['db_type']} database"
                elif 'database_type' in alert_data:
                    service_name = f"{alert_data['database_type']} database"
                elif 'device' in alert_data:
                    service_name = f"{alert_data['device']} network device"
                elif 'alert' in alert_data:
                    service_name = alert_data['alert']
                elif 'alertname' in alert_data:
                    service_name = alert_data['alertname']
                
                analysis_content = f"Analysis for {service_name} alert"
                
                # Include metrics data
                if 'metrics' in alert_data and isinstance(alert_data['metrics'], dict):
                    cpu_usage = alert_data['metrics'].get('cpu_usage', 0)
                    analysis_content += f" with CPU usage at {cpu_usage}%"
                
                # Include labels/region data
                if 'labels' in alert_data and isinstance(alert_data['labels'], dict):
                    region = alert_data['labels'].get('region')
                    zone = alert_data['labels'].get('zone')
                    if region:
                        analysis_content += f" in region {region}"
                    if zone:
                        analysis_content += f" zone {zone}"
                
                # Include tags if present  
                if 'tags' in alert_data and isinstance(alert_data['tags'], list):
                    if alert_data['tags']:
                        analysis_content += f" with tags: {', '.join(alert_data['tags'])}"
                
                # Include database info for database alerts
                if 'db_type' in alert_data:
                    analysis_content += f" database type: {alert_data['db_type']}"
                elif 'database_type' in alert_data:
                    analysis_content += f" database type: {alert_data['database_type']}"
                
                # Include cluster nodes for database alerts
                if 'cluster_nodes' in alert_data and isinstance(alert_data['cluster_nodes'], list):
                    node_info = []
                    for node in alert_data['cluster_nodes']:
                        node_name = node.get('node', 'unknown')
                        node_status = node.get('status', 'unknown')
                        node_info.append(f"{node_name}({node_status})")
                    analysis_content += f" cluster nodes: {', '.join(node_info)}"
                
                # Include connection pool info for database alerts
                if 'connection_pool' in alert_data and isinstance(alert_data['connection_pool'], dict):
                    pool = alert_data['connection_pool']
                    active = pool.get('active_connections', 0)
                    max_conn = pool.get('max_connections', 0)
                    analysis_content += f" connection_pool: {active}/{max_conn} active connections"
                
                # Include network device info for network alerts
                if 'device' in alert_data:
                    analysis_content += f" network device: {alert_data['device']}"
                
                # Include YAML config if present
                if 'yaml_config' in alert_data and alert_data['yaml_config']:
                    if 'ConfigMap' in alert_data['yaml_config']:
                        analysis_content += " includes ConfigMap configuration"
                    if 'monitoring-config' in alert_data['yaml_config']:
                        analysis_content += " with monitoring-config settings"
                        
                # Include additional monitoring system specific fields
                # Check both top-level and nested data fields
                data_section = alert_data.get('data', alert_data)
                
                # Prometheus fields
                if 'alertname' in alert_data:
                    analysis_content += f" alertname: {alert_data['alertname']}"
                elif 'alertname' in data_section:
                    analysis_content += f" alertname: {data_section['alertname']}"
                    
                if 'instance' in alert_data:
                    analysis_content += f" instance: {alert_data['instance']}"
                elif 'instance' in data_section:
                    analysis_content += f" instance: {data_section['instance']}"
                    
                if 'job' in alert_data:
                    analysis_content += f" job: {alert_data['job']}"
                elif 'job' in data_section:
                    analysis_content += f" job: {data_section['job']}"
                    
                if 'fingerprint' in alert_data:
                    analysis_content += f" fingerprint: {alert_data['fingerprint']}"
                elif 'fingerprint' in data_section:
                    analysis_content += f" fingerprint: {data_section['fingerprint']}"
                    
                if 'annotations' in alert_data and isinstance(alert_data['annotations'], dict):
                    if 'description' in alert_data['annotations']:
                        analysis_content += f" description: {alert_data['annotations']['description']}"
                elif 'annotations' in data_section and isinstance(data_section['annotations'], dict):
                    if 'description' in data_section['annotations']:
                        analysis_content += f" description: {data_section['annotations']['description']}"
                        
                # Handle labels field (both prometheus and general monitoring systems)
                if 'labels' in alert_data and isinstance(alert_data['labels'], dict):
                    labels = alert_data['labels']
                    if 'team' in labels:
                        analysis_content += f" team: {labels['team']}"
                    if 'environment' in labels:
                        analysis_content += f" env: {labels['environment']}"
                elif 'labels' in data_section and isinstance(data_section['labels'], dict):
                    labels = data_section['labels']
                    if 'team' in labels:
                        analysis_content += f" team: {labels['team']}"
                    if 'environment' in labels:
                        analysis_content += f" env: {labels['environment']}"
                        
                # Grafana fields
                if 'title' in alert_data:
                    analysis_content += f" title: {alert_data['title']}"
                elif 'title' in data_section:
                    analysis_content += f" title: {data_section['title']}"
                    
                if 'message' in alert_data:
                    analysis_content += f" message: {alert_data['message']}"
                elif 'message' in data_section:
                    analysis_content += f" message: {data_section['message']}"
                    
                if 'evalMatches' in alert_data and isinstance(alert_data['evalMatches'], list):
                    for match in alert_data['evalMatches']:
                        if 'metric' in match:
                            analysis_content += f" metric: {match['metric']}"
                elif 'evalMatches' in data_section and isinstance(data_section['evalMatches'], list):
                    for match in data_section['evalMatches']:
                        if 'metric' in match:
                            analysis_content += f" metric: {match['metric']}"
                            
                # Datadog fields  
                if 'metric' in alert_data:
                    analysis_content += f" metric: {alert_data['metric']}"
                elif 'metric' in data_section:
                    analysis_content += f" metric: {data_section['metric']}"
                    
                if 'host' in alert_data:
                    analysis_content += f" host: {alert_data['host']}"
                elif 'host' in data_section:
                    analysis_content += f" host: {data_section['host']}"
                    
                # New Relic fields
                if 'policy_name' in alert_data:
                    analysis_content += f" policy: {alert_data['policy_name']}"
                elif 'policy_name' in data_section:
                    analysis_content += f" policy: {data_section['policy_name']}"
                    
                if 'condition_name' in alert_data:
                    analysis_content += f" condition: {alert_data['condition_name']}"
                elif 'condition_name' in data_section:
                    analysis_content += f" condition: {data_section['condition_name']}"
                    
                if 'violation_url' in alert_data or 'violation_url' in data_section:
                    analysis_content += " with violation details"
                    
                # Splunk fields
                if 'search_name' in alert_data:
                    analysis_content += f" search: {alert_data['search_name']}"
                elif 'search_name' in data_section:
                    analysis_content += f" search: {data_section['search_name']}"
                    
                if 'results' in alert_data and isinstance(alert_data['results'], list):
                    if alert_data['results']:
                        analysis_content += f" results found: {len(alert_data['results'])} items"
                elif 'results' in data_section and isinstance(data_section['results'], list):
                    if data_section['results']:
                        analysis_content += f" results found: {len(data_section['results'])} items"
                        
                # Kubernetes specific fields for backward compatibility 
                if 'namespace' in alert_data:
                    if alert_data['namespace'] != 'stuck-namespace':  # Avoid overriding the hardcoded K8s test
                        analysis_content += f" namespace: {alert_data['namespace']}"
                elif 'namespace' in data_section:
                    if data_section['namespace'] != 'stuck-namespace':
                        analysis_content += f" namespace: {data_section['namespace']}"
                        
                if 'pod_name' in alert_data:
                    analysis_content += f" pod: {alert_data['pod_name']}"
                elif 'pod_name' in data_section:
                    analysis_content += f" pod: {data_section['pod_name']}"
                
                await llm_client.generate_response([
                    Mock(role="system", content="You are an expert SRE analyzing monitoring alerts."),
                    Mock(role="user", content=f"analyze alert data: {alert_data}")
                ], session_id=chain_context.session_id)
                
                return AgentExecutionResult(
                    status=StageStatus.COMPLETED,
                    agent_name="BaseAgent",
                    timestamp_us=now_us(),
                    result_summary=analysis_content,
                    final_analysis=analysis_content  # Set final_analysis so alert service can extract it
                )
            
            mock_agent.process_alert.side_effect = mock_base_process_alert
        
        else:
            # Default mock agent
            mock_agent = Mock()
            mock_agent.process_alert.return_value = AgentExecutionResult(
                status=StageStatus.COMPLETED,
                agent_name=agent_class_name,
                timestamp_us=now_us(),
                result_summary=f"Analysis completed by {agent_class_name}",
                final_analysis=f"Analysis completed by {agent_class_name}"  # Set final_analysis so alert service can extract it
            )
        
        return mock_agent
    
    # Make get_agent synchronous to match AlertService expectations
    def mock_get_agent(agent_identifier, iteration_strategy=None):
        return create_mock_agent(agent_identifier, iteration_strategy)
    
    factory.get_agent = Mock(side_effect=mock_get_agent)
    factory.create_agent = Mock(side_effect=create_mock_agent)
    factory.progress_callback = None
    return factory


@pytest.fixture
def progress_callback_mock():
    """Mock progress callback for testing."""
    callback = AsyncMock()
    return callback


@pytest.fixture
async def alert_service(ensure_integration_test_isolation, mock_settings, mock_runbook_service, mock_agent_registry, 
                       mock_mcp_server_registry, mock_mcp_client, mock_llm_manager,
                       mock_agent_factory):
    """Create AlertService with mocked dependencies."""
    service = AlertService(mock_settings)
    
    # Replace dependencies with mocks
    service.runbook_service = mock_runbook_service
    service.chain_registry = mock_agent_registry  # Using agent_registry mock but renamed for chain_registry
    service.mcp_server_registry = mock_mcp_server_registry
    service.mcp_client = mock_mcp_client
    service.llm_manager = mock_llm_manager
    
    # Initialize the service (this creates the real agent_factory)
    await service.initialize()
    
    # Replace the agent_factory with our mock AFTER initialization
    service.agent_factory = mock_agent_factory
    
    yield service


@pytest.fixture
def alert_service_with_mocks(
    ensure_integration_test_isolation,
    mock_settings,
    mock_llm_manager,
    mock_mcp_client,
    mock_mcp_server_registry,
    mock_runbook_service,
    mock_agent_registry,
    mock_agent_factory
):
    """Create AlertService with all dependencies mocked for integration testing."""
    # Create service with mocked settings
    service = AlertService(mock_settings)
    
    # Inject mocked dependencies
    service.llm_manager = mock_llm_manager
    service.mcp_client = mock_mcp_client
    service.mcp_server_registry = mock_mcp_server_registry
    service.runbook_service = mock_runbook_service
    service.chain_registry = mock_agent_registry  # Reuse the mock for chain registry
    service.agent_factory = mock_agent_factory
    # Create mock history service for proper testing
    mock_history_service = Mock(spec=HistoryService)
    mock_history_service.enabled = True
    mock_history_service.create_session.return_value = "test-session-id"
    mock_history_service.update_session_status = Mock()
    mock_history_service.complete_session = Mock()
    mock_history_service.record_error = Mock()
    service.history_service = mock_history_service
    
    # Bundle dependencies for easy access in tests
    mock_dependencies = {
        'llm_manager': mock_llm_manager,
        'mcp_client': mock_mcp_client,
        'mcp_registry': mock_mcp_server_registry,
        'runbook': mock_runbook_service,
        'registry': mock_agent_registry,
        'factory': mock_agent_factory,
        'history': mock_history_service
    }
    
    return service, mock_dependencies


# History Service Test Fixtures

@pytest.fixture
def history_test_database_engine():
    """Create in-memory SQLite engine for history service testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def mock_history_service():
    """Create mock history service for testing."""
    service = Mock(spec=HistoryService)
    service.enabled = True
    service.is_enabled = True
    service.create_session.return_value = "mock-session-123"
    service.update_session_status.return_value = True
    service.store_llm_interaction.return_value = True
    service.store_mcp_interaction.return_value = True
    service.get_sessions_list.return_value = ([], 0)
    service.get_session_details.return_value = None
    service.test_database_connection.return_value = True
    service.health_check.return_value = {
        "enabled": True,
        "healthy": True,
        "database_url": "sqlite:///test.db",
        "retention_days": 90
    }
    return service


@pytest.fixture
def sample_alert_session():
    """Create sample AlertSession for testing."""
    from datetime import datetime, timezone
    
    # Convert datetime to microseconds timestamp for started_at_us
    dt = datetime.now(timezone.utc)
    started_at_us = int(dt.timestamp() * 1_000_000)
    
    return AlertSession(
        session_id="test-session-123",
        alert_id="test-alert-456",
        alert_data={
            "alert_type": "NamespaceTerminating",
            "environment": "production",
            "cluster": "k8s-prod",
            "namespace": "stuck-namespace",
            "message": "Test alert message",
            "severity": "high"
        },
        agent_type="KubernetesAgent",
        alert_type="NamespaceTerminating",
        status="in_progress",
        started_at_us=started_at_us,
        session_metadata={"test": "metadata"},
        chain_id="test-integration-chain"
    )


@pytest.fixture
def sample_llm_interaction():
    """Create sample LLMInteraction for testing."""
    return LLMInteraction(
        interaction_id="llm-interaction-789",
        session_id="test-session-123",
        model_name="gpt-4",
        step_description="Initial analysis",
        request_json={"messages": [{"role": "user", "content": "Analyze the namespace termination issue"}]},
        response_json={"choices": [{"message": {"role": "assistant", "content": "The namespace is stuck due to finalizers"}, "finish_reason": "stop"}]},
        duration_ms=1500,
        token_usage={"prompt_tokens": 150, "completion_tokens": 50, "total_tokens": 200}
    )


@pytest.fixture
def sample_mcp_communication():
    """Create sample MCPInteraction for testing."""
    return MCPInteraction(
        communication_id="mcp-comm-101",
        session_id="test-session-123",
        server_name="kubernetes-server",
        communication_type="tool_call",
        tool_name="kubectl_get_namespace",
        tool_arguments={"namespace": "stuck-namespace"},
        tool_result={"status": "Terminating", "finalizers": ["test-finalizer"]},
        step_description="Check namespace status",
        duration_ms=800,
        success=True,
        available_tools=["kubectl_get_namespace", "kubectl_describe_namespace"]
    )


@pytest.fixture
def datetime_now_utc():
    """Provide current UTC datetime for testing."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)


@pytest.fixture
def history_service_with_test_db(history_test_database_engine):
    """Create HistoryService with test database engine."""
    from unittest.mock import patch

    from tarsy.services.history_service import HistoryService
    
    # Mock settings for history service
    mock_settings = Mock()
    mock_settings.history_enabled = True
    mock_settings.history_database_url = "sqlite:///:memory:"
    mock_settings.history_retention_days = 90
    
    with patch('tarsy.services.history_service.get_settings', return_value=mock_settings):
        service = HistoryService()
        
        # Initialize the service properly
        service.initialize()
        
        # Override database engine for testing if db_manager exists
        if service.db_manager:
            service.db_manager.engine = history_test_database_engine
            service.db_manager.SessionLocal = lambda: Session(history_test_database_engine)
        
        service._is_healthy = True
        service._initialization_attempted = True
        
        return service


@pytest.fixture
def mock_history_timeline_data():
    """Create mock timeline data for testing."""
    from datetime import datetime, timezone
    
    return {
        "session_info": {
            "session_id": "test-session-123",
            "alert_id": "test-alert-456",
            "alert_type": "NamespaceTerminating",
            "agent_type": "KubernetesAgent",
            "status": "completed",
            "started_at": datetime.now(timezone.utc),
            "completed_at": datetime.now(timezone.utc),
            "error_message": None
        },
        "chronological_timeline": [
            {
                "type": "llm_interaction",
                "timestamp": datetime.now(timezone.utc),
                "step_description": "Initial analysis",
                "prompt_text": "Analyze the issue",
                "response_text": "Found the problem",
                "model_used": "gpt-4",
                "duration_ms": 1500
            },
            {
                "type": "mcp_communication",
                "timestamp": datetime.now(timezone.utc),
                "step_description": "Check namespace status",
                "server_name": "kubernetes-server",
                "tool_name": "kubectl_get_namespace",
                "success": True,
                "duration_ms": 800
            }
        ],
        "summary": {
            "total_interactions": 2,
            "llm_interactions": 1,
            "mcp_communications": 1,
            "total_duration_ms": 2300
        }
    } 