"""
Test factories for context models.

This module provides factory functions for creating test instances of the
ChainContext and StageContext models for use in tests.
"""

import time
from typing import List
from unittest.mock import Mock

from mcp.types import Tool

from tarsy.models.agent_execution_result import AgentExecutionResult
from tarsy.models.alert import ProcessingAlert
from tarsy.models.constants import StageStatus
from tarsy.models.processing_context import (
    AvailableTools,
    ChainContext,
    StageContext,
    ToolWithServer,
)


class ChainContextFactory:
    """Factory for creating test ChainContext instances."""
    
    @staticmethod
    def create_basic() -> ChainContext:
        """Create a basic ChainContext for testing."""
        processing_alert = ProcessingAlert(
            alert_type="kubernetes",
            severity="warning",
            timestamp=int(time.time() * 1_000_000),
            environment="production",
            runbook_url=None,
            alert_data={"pod": "test-pod", "namespace": "default"}
        )
        return ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session-123",
            current_stage_name="analysis"
        )
    
    @staticmethod
    def create_with_runbook() -> ChainContext:
        """Create ChainContext with runbook content."""
        processing_alert = ProcessingAlert(
            alert_type="kubernetes",
            severity="critical",
            timestamp=int(time.time() * 1_000_000),
            environment="production",
            runbook_url="https://example.com/runbook",
            alert_data={
                "pod": "failing-pod",
                "namespace": "production",
                "error": "CrashLoopBackOff"
            }
        )
        context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="prod-session-456",
            current_stage_name="investigation"
        )
        context.runbook_content = "# Pod Failure Runbook\n\n## Investigation Steps\n1. Check pod logs\n2. Verify resource limits"
        context.chain_id = "k8s-troubleshooting-chain"
        return context
    
    @staticmethod
    def create_with_stage_results() -> ChainContext:
        """Create ChainContext with completed stage results."""
        processing_alert = ProcessingAlert(
            alert_type="aws",
            severity="warning",
            timestamp=int(time.time() * 1_000_000),
            environment="production",
            runbook_url=None,
            alert_data={"instance_id": "i-1234567890abcdef0", "region": "us-east-1"}
        )
        context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="aws-session-789",
            current_stage_name="remediation"
        )
        context.chain_id = "aws-ec2-chain"
        
        # Add completed data collection stage
        data_collection_result = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="DataCollectionAgent",
            stage_name="data-collection",
            stage_description="Data Collection",
            timestamp_us=int(time.time() * 1_000_000),
            result_summary="Collected instance metrics, logs, and CloudWatch data",
            final_analysis="Instance shows high CPU usage and memory pressure",
            duration_ms=5000
        )
        context.add_stage_result("data-collection", data_collection_result)
        
        # Add completed analysis stage
        analysis_result = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="AnalysisAgent",
            stage_name="analysis",
            stage_description="Root Cause Analysis",
            timestamp_us=int(time.time() * 1_000_000) + 10_000,
            result_summary="Identified memory leak in application code",
            final_analysis="Application has memory leak causing OOM kills",
            duration_ms=3000
        )
        context.add_stage_result("analysis", analysis_result)
        
        return context
    
    @staticmethod
    def create_complex_alert_data() -> ChainContext:
        """Create ChainContext with complex, nested alert data."""
        complex_data = {
            "alert_metadata": {
                "source": "prometheus",
                "rule_name": "KubernetesPodCrashLooping",
                "timestamp": "2024-01-15T10:30:00Z"
            },
            "pod_info": {
                "name": "api-server-7d4b9c8f6-xyz123",
                "namespace": "production",
                "labels": {
                    "app": "api-server",
                    "version": "v2.1.3",
                    "tier": "backend"
                },
                "restart_count": 15,
                "last_state": {
                    "terminated": {
                        "exit_code": 1,
                        "reason": "Error",
                        "message": "panic: runtime error: invalid memory address"
                    }
                }
            },
            "cluster_info": {
                "name": "prod-cluster-east",
                "region": "us-east-1",
                "node_count": 12
            },
            "annotations": {
                "monitoring.io/alert-level": "critical",
                "runbook.io/url": "https://runbooks.company.com/k8s/pod-crashes.md"
            }
        }
        
        processing_alert = ProcessingAlert(
            alert_type="KubernetesPodCrashLooping",
            severity="critical",
            timestamp=int(time.time() * 1_000_000),
            environment="production",
            runbook_url=None,
            alert_data=complex_data
        )
        return ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="complex-session-999",
            current_stage_name="triage"
        )


class AvailableToolsFactory:
    """Factory for creating test AvailableTools instances."""
    
    @staticmethod
    def create_kubernetes_tools() -> AvailableTools:
        """Create AvailableTools with Kubernetes-specific tools using official MCP Tool objects."""
        tools = [
            ToolWithServer(
                server="kubernetes-server",
                tool=Tool(
                    name="get_pods",
                    description="Get pod information and status",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "namespace": {
                                "type": "string",
                                "description": "Kubernetes namespace"
                            },
                            "label_selector": {
                                "type": "string", 
                                "description": "Label selector for filtering"
                            }
                        }
                    }
                )
            ),
            ToolWithServer(
                server="kubernetes-server",
                tool=Tool(
                    name="get_pod_logs",
                    description="Get logs from a specific pod",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "pod_name": {
                                "type": "string",
                                "description": "Name of the pod"
                            },
                            "namespace": {
                                "type": "string",
                                "description": "Pod namespace"
                            },
                            "tail_lines": {
                                "type": "integer",
                                "description": "Number of lines to tail"
                            }
                        }
                    }
                )
            ),
            ToolWithServer(
                server="kubernetes-server",
                tool=Tool(
                    name="describe_pod",
                    description="Get detailed pod description including events",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "pod_name": {
                                "type": "string",
                                "description": "Name of the pod"
                            },
                            "namespace": {
                                "type": "string",
                                "description": "Pod namespace"
                            }
                        }
                    }
                )
            )
        ]
        return AvailableTools(tools=tools)
    
    @staticmethod
    def create_aws_tools() -> AvailableTools:
        """Create AvailableTools with AWS-specific tools using official MCP Tool objects."""
        tools = [
            ToolWithServer(
                server="aws-server",
                tool=Tool(
                    name="describe_instances",
                    description="Describe EC2 instances",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "instance_ids": {
                                "type": "array",
                                "description": "List of instance IDs"
                            },
                            "filters": {
                                "type": "object",
                                "description": "EC2 filters"
                            }
                        }
                    }
                )
            ),
            ToolWithServer(
                server="aws-server",
                tool=Tool(
                    name="get_cloudwatch_metrics",
                    description="Get CloudWatch metrics for resources",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "metric_name": {
                                "type": "string",
                                "description": "CloudWatch metric name"
                            },
                            "namespace": {
                                "type": "string",
                                "description": "CloudWatch namespace"
                            },
                            "dimensions": {
                                "type": "object",
                                "description": "Metric dimensions"
                            }
                        }
                    }
                )
            )
        ]
        return AvailableTools(tools=tools)
    
    @staticmethod
    def create_mixed_tools() -> AvailableTools:
        """Create AvailableTools with tools from multiple servers using official MCP Tool objects."""
        k8s_tools = AvailableToolsFactory.create_kubernetes_tools().tools
        aws_tools = AvailableToolsFactory.create_aws_tools().tools
        
        # Add a monitoring tool
        monitoring_tool = ToolWithServer(
            server="monitoring-server",
            tool=Tool(
                name="query_prometheus",
                description="Execute Prometheus query",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "PromQL query"
                        },
                        "time_range": {
                            "type": "string",
                            "description": "Time range for query"
                        }
                    }
                }
            )
        )
        
        return AvailableTools(tools=k8s_tools + aws_tools + [monitoring_tool])
    



class MockAgentFactory:
    """Factory for creating mock agents for testing."""
    
    @staticmethod
    def create_kubernetes_agent() -> Mock:
        """Create a mock Kubernetes agent."""
        agent = type("KubernetesAgent", (Mock,), {})()
        agent.mcp_servers.return_value = ["kubernetes-server", "monitoring-server"]
        agent.custom_instructions.return_value = "Specialized Kubernetes troubleshooting agent"
        return agent
    
    @staticmethod
    def create_aws_agent() -> Mock:
        """Create a mock AWS agent."""
        agent = type("AWSAgent", (Mock,), {})()
        agent.mcp_servers.return_value = ["aws-server", "cloudwatch-server"]
        agent.custom_instructions.return_value = "AWS infrastructure analysis agent"
        return agent
    
    @staticmethod
    def create_configurable_agent(name: str, servers: List[str]) -> Mock:
        """Create a mock configurable agent with custom settings."""
        agent = type(name, (Mock,), {})()
        agent.mcp_servers.return_value = servers
        agent.custom_instructions.return_value = f"Configurable agent: {name}"
        return agent


class StageContextFactory:
    """Factory for creating test StageContext instances."""
    
    @staticmethod
    def create_basic() -> StageContext:
        """Create a basic StageContext for testing."""
        chain_context = ChainContextFactory.create_basic()
        available_tools = AvailableToolsFactory.create_kubernetes_tools()
        agent = MockAgentFactory.create_kubernetes_agent()
        
        return StageContext(
            chain_context=chain_context,
            available_tools=available_tools,
            agent=agent
        )
    
    @staticmethod
    def create_with_previous_stages() -> StageContext:
        """Create StageContext with previous completed stages."""
        chain_context = ChainContextFactory.create_with_stage_results()
        available_tools = AvailableToolsFactory.create_aws_tools()
        agent = MockAgentFactory.create_aws_agent()
        
        return StageContext(
            chain_context=chain_context,
            available_tools=available_tools,
            agent=agent
        )
    
    @staticmethod
    def create_kubernetes_scenario() -> StageContext:
        """Create StageContext for a Kubernetes troubleshooting scenario."""
        chain_context = ChainContextFactory.create_with_runbook()
        available_tools = AvailableToolsFactory.create_kubernetes_tools()
        agent = MockAgentFactory.create_kubernetes_agent()
        
        return StageContext(
            chain_context=chain_context,
            available_tools=available_tools,
            agent=agent
        )
    
    @staticmethod
    def create_complex_scenario() -> StageContext:
        """Create StageContext with complex alert data and mixed tools."""
        chain_context = ChainContextFactory.create_complex_alert_data()
        available_tools = AvailableToolsFactory.create_mixed_tools()
        agent = MockAgentFactory.create_configurable_agent(
            "ComplexScenarioAgent",
            ["kubernetes-server", "aws-server", "monitoring-server"]
        )
        
        return StageContext(
            chain_context=chain_context,
            available_tools=available_tools,
            agent=agent
        )


# EP-0012 Clean Implementation: Convenience functions for backward compatibility with tests
def create_test_chain_context() -> ChainContext:
    """Create a test ChainContext instance."""
    return ChainContextFactory.create_basic()

def create_test_stage_context() -> StageContext:
    """Create a test StageContext instance.""" 
    return StageContextFactory.create_basic()

def create_comparable_contexts_pair() -> tuple[ChainContext, ChainContext]:
    """Create two comparable ChainContext instances for testing."""
    return (
        ChainContextFactory.create_basic(),
        ChainContextFactory.create_with_runbook()
    )

def create_stage_context_comparison_pair() -> tuple[StageContext, StageContext]:
    """Create two comparable StageContext instances for testing."""
    return (
        StageContextFactory.create_basic(),
        StageContextFactory.create_with_previous_stages()
    )
