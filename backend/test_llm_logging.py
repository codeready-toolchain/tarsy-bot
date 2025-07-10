#!/usr/bin/env python3
"""
Test script to verify LLM communication logging is working correctly.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add the backend directory to the Python path
sys.path.insert(0, str(Path(__file__).parent))

from app.config.settings import Settings
from app.integrations.llm.client import LLMManager
from app.integrations.llm.langchain_client import LangChainLLMClient
from app.utils.logger import setup_logging, get_module_logger
from app.models.alert import Alert
from app.models.llm import LLMMessage

# Setup logging
setup_logging("DEBUG")
logger = get_module_logger(__name__)

async def test_llm_manager_logging():
    """Test logging with LLMManager (original client)."""
    print("Testing LLMManager logging...")
    
    # Load settings
    settings = Settings()
    
    # Initialize LLM manager
    llm_manager = LLMManager(settings)
    
    # Test alert data
    alert_data = {
        "alert": "HighMemoryUsage",
        "severity": "warning",
        "environment": "production",
        "cluster": "test-cluster",
        "namespace": "default",
        "pod": "test-pod",
        "message": "Memory usage is above 80%"
    }
    
    runbook_data = {
        "title": "High Memory Usage Runbook",
        "description": "Steps to investigate high memory usage",
        "steps": ["Check memory metrics", "Analyze memory leaks", "Scale if needed"]
    }
    
    mcp_data = {
        "prometheus": [
            {"metric": "memory_usage", "value": "85%", "timestamp": "2024-01-01T12:00:00Z"}
        ]
    }
    
    try:
        # Test alert analysis
        logger.info("Testing LLM alert analysis...")
        analysis = await llm_manager.analyze_alert(alert_data, runbook_data, mcp_data)
        print(f"Analysis result: {analysis[:100]}...")
        
        # Test MCP tool determination
        logger.info("Testing MCP tool determination...")
        available_tools = {
            "prometheus": [
                {"name": "query_metrics", "description": "Query Prometheus metrics"}
            ],
            "kubernetes": [
                {"name": "get_pod_info", "description": "Get pod information"}
            ]
        }
        
        tools = await llm_manager.determine_mcp_tools(alert_data, runbook_data, available_tools)
        print(f"Tools determined: {len(tools)} tools")
        
        print("✅ LLMManager logging test completed successfully!")
        
    except Exception as e:
        print(f"❌ LLMManager test failed: {e}")
        logger.error(f"LLMManager test failed: {e}")

async def test_langchain_client_logging():
    """Test logging with LangChainLLMClient (new client)."""
    print("\nTesting LangChainLLMClient logging...")
    
    # Load settings
    settings = Settings()
    
    # Initialize LangChain client
    langchain_client = LangChainLLMClient(settings)
    
    # Test alert
    alert = Alert(
        alert="HighMemoryUsage",
        severity="warning",
        environment="production",
        cluster="test-cluster",
        namespace="default",
        pod="test-pod",
        message="Memory usage is above 80%",
        runbook="https://example.com/runbook.md"
    )
    
    runbook_data = {
        "title": "High Memory Usage Runbook",
        "description": "Steps to investigate high memory usage",
        "steps": ["Check memory metrics", "Analyze memory leaks", "Scale if needed"]
    }
    
    system_data = {
        "prometheus": [
            {"metric": "memory_usage", "value": "85%", "timestamp": "2024-01-01T12:00:00Z"}
        ]
    }
    
    try:
        # Test alert analysis
        logger.info("Testing LangChain alert analysis...")
        analysis = await langchain_client.analyze_alert(alert, runbook_data, system_data)
        print(f"Analysis result: {analysis[:100]}...")
        
        # Test next steps determination
        logger.info("Testing next steps determination...")
        available_tools = {
            "prometheus": [
                {"name": "query_metrics", "description": "Query Prometheus metrics"}
            ]
        }
        
        next_steps = await langchain_client.determine_next_steps(
            alert, available_tools, []
        )
        print(f"Next steps: {next_steps}")
        
        print("✅ LangChainLLMClient logging test completed successfully!")
        
    except Exception as e:
        print(f"❌ LangChainLLMClient test failed: {e}")
        logger.error(f"LangChainLLMClient test failed: {e}")

async def main():
    """Run all logging tests."""
    print("🔍 Testing LLM Communication Logging")
    print("=" * 50)
    
    # Test both LLM clients
    await test_llm_manager_logging()
    await test_langchain_client_logging()
    
    print("\n📁 Check the following log files for communication details:")
    print("- logs/llm_communications.log")
    print("- logs/sre_agent.log")
    print("- logs/mcp_communications.log")
    
    print("\n🎉 All logging tests completed!")

if __name__ == "__main__":
    asyncio.run(main()) 