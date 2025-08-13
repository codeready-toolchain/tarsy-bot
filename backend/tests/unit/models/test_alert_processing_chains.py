"""
Unit tests for AlertProcessingData chain enhancements.

Tests the chain-related methods and functionality added to AlertProcessingData
for supporting sequential agent chains.
"""

import pytest
from tarsy.models.alert_processing import AlertProcessingData


@pytest.mark.unit
class TestAlertProcessingDataChainContext:
    """Test chain context management in AlertProcessingData."""
    
    def test_set_chain_context_basic(self):
        """Test setting basic chain context."""
        alert_data = AlertProcessingData(
            alert_type="kubernetes",
            alert_data={"test": "data"}
        )
        
        alert_data.set_chain_context("test-chain", "analysis")
        
        assert alert_data.chain_id == "test-chain"
        assert alert_data.current_stage_name == "analysis"
    
    def test_set_chain_context_no_stage(self):
        """Test setting chain context without current stage."""
        alert_data = AlertProcessingData(
            alert_type="kubernetes",
            alert_data={"test": "data"}
        )
        
        alert_data.set_chain_context("test-chain")
        
        assert alert_data.chain_id == "test-chain"
        assert alert_data.current_stage_name is None
    
    def test_set_chain_context_update(self):
        """Test updating chain context."""
        alert_data = AlertProcessingData(
            alert_type="kubernetes",
            alert_data={"test": "data"}
        )
        
        # Initial context
        alert_data.set_chain_context("chain1", "stage1")
        assert alert_data.chain_id == "chain1"
        assert alert_data.current_stage_name == "stage1"
        
        # Update context
        alert_data.set_chain_context("chain2", "stage2")
        assert alert_data.chain_id == "chain2"
        assert alert_data.current_stage_name == "stage2"


@pytest.mark.unit
class TestAlertProcessingDataStageResults:
    """Test stage result management in AlertProcessingData."""
    
    def test_add_stage_result_basic(self):
        """Test adding basic stage result."""
        alert_data = AlertProcessingData(
            alert_type="kubernetes",
            alert_data={"test": "data"}
        )
        
        stage_result = {
            "status": "success",
            "analysis": "Test analysis",
            "actions_taken": ["action1", "action2"]
        }
        
        alert_data.add_stage_result("data-collection", stage_result)
        
        assert "data-collection" in alert_data.stage_outputs
        assert alert_data.stage_outputs["data-collection"] == stage_result
    
    def test_add_multiple_stage_results(self):
        """Test adding multiple stage results."""
        alert_data = AlertProcessingData(
            alert_type="kubernetes",
            alert_data={"test": "data"}
        )
        
        # Add first stage result
        stage1_result = {"status": "success", "data": "stage1 data"}
        alert_data.add_stage_result("stage1", stage1_result)
        
        # Add second stage result  
        stage2_result = {"status": "success", "analysis": "stage2 analysis"}
        alert_data.add_stage_result("stage2", stage2_result)
        
        assert len(alert_data.stage_outputs) == 2
        assert alert_data.stage_outputs["stage1"] == stage1_result
        assert alert_data.stage_outputs["stage2"] == stage2_result
    
    def test_get_stage_result_existing(self):
        """Test getting existing stage result."""
        alert_data = AlertProcessingData(
            alert_type="kubernetes",
            alert_data={"test": "data"}
        )
        
        stage_result = {"status": "success", "result": "test"}
        alert_data.add_stage_result("test-stage", stage_result)
        
        retrieved_result = alert_data.get_stage_result("test-stage")
        assert retrieved_result == stage_result
    
    def test_get_stage_result_nonexistent(self):
        """Test getting non-existent stage result."""
        alert_data = AlertProcessingData(
            alert_type="kubernetes",
            alert_data={"test": "data"}
        )
        
        result = alert_data.get_stage_result("nonexistent-stage")
        assert result is None


@pytest.mark.unit
class TestAlertProcessingDataMCPResults:
    """Test MCP result aggregation methods."""
    
    @pytest.fixture
    def alert_with_mcp_results(self):
        """Create alert data with MCP results from multiple stages."""
        alert_data = AlertProcessingData(
            alert_type="kubernetes",
            alert_data={"test": "data"}
        )
        
        # Stage 1: Data collection with k8s server results
        stage1_result = {
            "status": "success",
            "mcp_results": {
                "kubernetes-server": [
                    {"type": "pods", "data": {"pod1": "data"}},
                    {"type": "events", "data": {"event1": "data"}}
                ]
            }
        }
        alert_data.add_stage_result("data-collection", stage1_result)
        
        # Stage 2: Analysis with monitoring server results
        stage2_result = {
            "status": "success", 
            "analysis": "test analysis",
            "mcp_results": {
                "monitoring-server": [
                    {"type": "metrics", "data": {"cpu": "90%"}}
                ],
                "kubernetes-server": [
                    {"type": "logs", "data": {"log1": "error"}}
                ]
            }
        }
        alert_data.add_stage_result("analysis", stage2_result)
        
        # Stage 3: No MCP results
        stage3_result = {
            "status": "success",
            "recommendations": ["fix this", "fix that"]
        }
        alert_data.add_stage_result("recommendations", stage3_result)
        
        return alert_data
    
    def test_get_all_mcp_results_merged(self, alert_with_mcp_results):
        """Test merging MCP results from all stages."""
        merged = alert_with_mcp_results.get_all_mcp_results()
        
        # Should have both servers
        assert "kubernetes-server" in merged
        assert "monitoring-server" in merged
        
        # kubernetes-server should have results from both stages
        k8s_results = merged["kubernetes-server"]
        assert len(k8s_results) == 3  # 2 from stage1 + 1 from stage2
        
        # monitoring-server should have results from stage2 only
        monitoring_results = merged["monitoring-server"]
        assert len(monitoring_results) == 1
    
    def test_get_stage_attributed_mcp_results(self, alert_with_mcp_results):
        """Test getting MCP results with stage attribution."""
        attributed = alert_with_mcp_results.get_stage_attributed_mcp_results()
        
        # Should have results from stages that had MCP data
        assert "data-collection" in attributed
        assert "analysis" in attributed
        assert "recommendations" not in attributed  # No MCP results
        
        # Verify structure preservation
        assert "kubernetes-server" in attributed["data-collection"]
        assert "kubernetes-server" in attributed["analysis"]
        assert "monitoring-server" in attributed["analysis"]
        
        # Verify data integrity
        stage1_k8s = attributed["data-collection"]["kubernetes-server"]
        assert len(stage1_k8s) == 2
        assert any(result["type"] == "pods" for result in stage1_k8s)
    
    def test_get_all_mcp_results_empty_stages(self):
        """Test MCP result merging with no MCP data."""
        alert_data = AlertProcessingData(
            alert_type="kubernetes",
            alert_data={"test": "data"}
        )
        
        # Add stage without MCP results
        alert_data.add_stage_result("stage1", {"status": "success", "analysis": "test"})
        
        merged = alert_data.get_all_mcp_results()
        attributed = alert_data.get_stage_attributed_mcp_results()
        
        assert merged == {}
        assert attributed == {}
    
    def test_get_all_mcp_results_non_list_data(self):
        """Test MCP result merging with non-list server data."""
        alert_data = AlertProcessingData(
            alert_type="kubernetes", 
            alert_data={"test": "data"}
        )
        
        # Add stage with non-list MCP data (edge case)
        stage_result = {
            "status": "success",
            "mcp_results": {
                "test-server": {"type": "single", "data": "not a list"}
            }
        }
        alert_data.add_stage_result("test-stage", stage_result)
        
        # Should handle gracefully by wrapping non-list data in a list
        merged = alert_data.get_all_mcp_results()
        
        # Non-list data should be wrapped in a list
        assert "test-server" in merged
        assert len(merged["test-server"]) == 1
        assert merged["test-server"][0] == {"type": "single", "data": "not a list"}


@pytest.mark.unit
class TestAlertProcessingDataChainIntegration:
    """Test integration of chain features with existing AlertProcessingData functionality."""
    
    def test_chain_processing_with_runbook(self):
        """Test chain processing combined with runbook functionality."""
        alert_data = AlertProcessingData(
            alert_type="kubernetes",
            alert_data={"test": "data"},
            runbook_url="https://example.com/runbook.md"
        )
        
        # Set runbook content (simulates runbook download)
        alert_data.set_runbook_content("# Kubernetes Runbook\nSteps to resolve...")
        
        # Set chain context
        alert_data.set_chain_context("kubernetes-chain", "data-collection")
        
        # Add stage results
        stage_result = {
            "status": "success",
            "runbook_used": True,
            "mcp_results": {"kubernetes-server": [{"type": "pods", "data": {}}]}
        }
        alert_data.add_stage_result("data-collection", stage_result)
        
        # Verify all functionality works together
        assert alert_data.get_runbook_content() == "# Kubernetes Runbook\nSteps to resolve..."
        assert alert_data.chain_id == "kubernetes-chain"
        assert alert_data.current_stage_name == "data-collection"
        assert alert_data.get_stage_result("data-collection")["runbook_used"] is True
        
        # Verify MCP results accessible
        mcp_results = alert_data.get_all_mcp_results()
        assert "kubernetes-server" in mcp_results
    
    def test_chain_stage_progression(self):
        """Test progressive stage execution simulation."""
        alert_data = AlertProcessingData(
            alert_type="kubernetes",
            alert_data={"severity": "high", "environment": "production"}
        )
        
        # Stage 1: Data collection
        alert_data.set_chain_context("troubleshooting-chain", "data-collection")
        stage1_result = {
            "status": "success",
            "collected_data": ["pods", "events", "logs"],
            "mcp_results": {"kubernetes-server": [{"pods": []}]}
        }
        alert_data.add_stage_result("data-collection", stage1_result)
        
        # Stage 2: Analysis (uses data from stage 1)
        alert_data.set_chain_context("troubleshooting-chain", "analysis")
        stage2_result = {
            "status": "success",
            "root_cause": "Resource exhaustion",
            "confidence": 0.95,
            "used_previous_data": len(stage1_result["collected_data"])
        }
        alert_data.add_stage_result("analysis", stage2_result)
        
        # Stage 3: Remediation
        alert_data.set_chain_context("troubleshooting-chain", "remediation")
        stage3_result = {
            "status": "success", 
            "remediation_plan": ["scale up", "optimize resources"],
            "based_on_analysis": stage2_result["root_cause"]
        }
        alert_data.add_stage_result("remediation", stage3_result)
        
        # Verify complete chain execution state
        assert alert_data.chain_id == "troubleshooting-chain"
        assert alert_data.current_stage_name == "remediation"
        assert len(alert_data.stage_outputs) == 3
        
        # Verify data flow between stages
        analysis_result = alert_data.get_stage_result("analysis")
        assert analysis_result["used_previous_data"] == 3  # Used data from stage 1
        
        remediation_result = alert_data.get_stage_result("remediation") 
        assert remediation_result["based_on_analysis"] == "Resource exhaustion"
        
        # Verify MCP results still accessible
        mcp_results = alert_data.get_all_mcp_results()
        assert "kubernetes-server" in mcp_results
    
    def test_existing_helpers_with_chains(self):
        """Test that existing helper methods work with chain processing."""
        alert_data = AlertProcessingData(
            alert_type="kubernetes",
            alert_data={
                "severity": "critical",
                "environment": "staging",
                "runbook": "https://example.com/k8s.md"
            }
        )
        
        # Set chain context
        alert_data.set_chain_context("test-chain", "test-stage")
        
        # Add stage results
        alert_data.add_stage_result("test-stage", {"status": "success"})
        
        # Verify existing helpers still work
        assert alert_data.get_severity() == "critical"
        assert alert_data.get_environment() == "staging"
        assert alert_data.get_runbook_url() == "https://example.com/k8s.md"
        assert len(alert_data.get_original_alert_data()) == 3
        
        # Verify chain-specific functionality
        assert alert_data.chain_id == "test-chain"
        assert len(alert_data.stage_outputs) == 1
