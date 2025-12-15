"""
Unit tests for AlertService pause/resume functionality.

Tests the core business logic of pausing and resuming sessions,
including state reconstruction and execution continuation.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tarsy.models.api_models import ChainExecutionResult
from tarsy.models.constants import AlertSessionStatus, ChainStatus, StageStatus
from tarsy.models.db_models import AlertSession, StageExecution
from tarsy.services.alert_service import AlertService


@pytest.mark.unit
class TestAlertServiceResumePausedSession:
    """Test suite for AlertService.resume_paused_session()."""
    
    @pytest.mark.asyncio
    async def test_resume_paused_session_success(self) -> None:
        """Test successfully resuming a paused session."""
        session_id = "test-session-123"
        
        # Create mock session
        mock_session = MagicMock(spec=AlertSession)
        mock_session.session_id = session_id
        mock_session.status = AlertSessionStatus.PAUSED.value
        mock_session.alert_type = "kubernetes"
        mock_session.alert_data = {"severity": "warning", "message": "Test alert"}
        mock_session.started_at_us = 1000000
        mock_session.runbook_url = None
        mock_session.mcp_selection = None
        mock_session.author = None
        mock_session.chain_config = MagicMock()
        mock_session.chain_config.chain_id = "test-chain"
        
        # Create mock paused stage
        mock_paused_stage = MagicMock(spec=StageExecution)
        mock_paused_stage.status = StageStatus.PAUSED.value
        mock_paused_stage.stage_name = "initial-analysis"
        mock_paused_stage.current_iteration = 30
        mock_paused_stage.stage_output = None
        
        # Create mock history service
        mock_history_service = MagicMock()
        mock_history_service.get_session.return_value = mock_session
        mock_history_service.get_stage_executions = AsyncMock(return_value=[mock_paused_stage])
        
        # Create mock settings
        mock_settings = MagicMock()
        mock_settings.agent_config_path = None
        
        # Create alert service
        with patch('tarsy.services.alert_service.RunbookService'):
            alert_service = AlertService(settings=mock_settings)
        
        alert_service.history_service = mock_history_service
        alert_service.runbook_service = MagicMock()
        alert_service.runbook_service.download_runbook = AsyncMock(return_value="# Default runbook")
        
        # Mock final_analysis_summarizer
        mock_summarizer = AsyncMock()
        mock_summarizer.generate_executive_summary = AsyncMock(return_value="Executive summary of resumed analysis")
        alert_service.final_analysis_summarizer = mock_summarizer
        
        # Mock session_manager.update_session_status and _execute_chain_stages
        alert_service.session_manager.update_session_status = MagicMock()
        alert_service._execute_chain_stages = AsyncMock(
            return_value=ChainExecutionResult(
                status=ChainStatus.COMPLETED,
                timestamp_us=1234567890,
                final_analysis="Analysis completed after resume"
            )
        )
        
        # Mock MCP client factory
        with patch.object(alert_service, 'mcp_client_factory') as mock_mcp_factory:
            mock_mcp_factory.create_client = AsyncMock()
            
            # Mock event publishing
            with patch('tarsy.services.events.event_helpers.publish_session_resumed', new=AsyncMock()) as mock_resume_event, \
                 patch('tarsy.services.events.event_helpers.publish_session_completed', new=AsyncMock()) as mock_complete_event, \
                 patch('tarsy.hooks.hook_context.stage_execution_context'):
                
                # Call resume
                result = await alert_service.resume_paused_session(session_id)
        
        # Verify result is formatted as a Markdown report
        assert "# Alert Analysis Report" in result
        assert "Analysis completed after resume" in result
        assert "**Processing Chain:** test-chain" in result
        
        # Verify session status updated to IN_PROGRESS
        assert alert_service.session_manager.update_session_status.call_count >= 1
        first_call = alert_service.session_manager.update_session_status.call_args_list[0]
        # Handle both positional and keyword argument styles
        first_session_id = first_call.kwargs.get("session_id") or (first_call.args[0] if len(first_call.args) > 0 else None)
        first_status = first_call.kwargs.get("status") or (first_call.args[1] if len(first_call.args) > 1 else None)
        assert first_session_id == session_id
        assert first_status == AlertSessionStatus.IN_PROGRESS.value
        
        # Verify resume and completion events published
        mock_resume_event.assert_called_once_with(session_id)
        mock_complete_event.assert_called_once_with(session_id)
        
        # Verify session was eventually marked COMPLETED with summary
        completed_call = None
        for call_args in alert_service.session_manager.update_session_status.call_args_list:
            # Handle both positional and keyword argument styles
            if "status" in call_args.kwargs:
                status = call_args.kwargs["status"]
            else:
                status = call_args.args[1] if len(call_args.args) > 1 else None
            if status == AlertSessionStatus.COMPLETED.value:
                completed_call = call_args
                break
        
        assert completed_call is not None, "Session was not marked as COMPLETED"
        # Verify final_analysis_summary was passed (handle both positional and keyword arguments)
        final_analysis_summary = completed_call.kwargs.get('final_analysis_summary') or (
            completed_call.args[4] if len(completed_call.args) > 4 else None
        )
        assert final_analysis_summary == "Executive summary of resumed analysis", \
            "Executive summary not generated for resumed session"
        
        # Verify chain execution called
        alert_service._execute_chain_stages.assert_called_once()
        
        # Verify executive summary was generated with correct content and session_id
        mock_summarizer.generate_executive_summary.assert_called_once()
        call_kwargs = mock_summarizer.generate_executive_summary.call_args.kwargs
        assert call_kwargs["content"] == "Analysis completed after resume"
        assert call_kwargs["session_id"] == session_id
    
    @pytest.mark.asyncio
    async def test_resume_session_not_found(self) -> None:
        """Test resuming a non-existent session raises error."""
        session_id = "non-existent"
        
        mock_history_service = MagicMock()
        mock_history_service.get_session.return_value = None
        
        mock_settings = MagicMock()
        mock_settings.agent_config_path = None
        
        with patch('tarsy.services.alert_service.RunbookService'):
            alert_service = AlertService(settings=mock_settings)
        
        alert_service.history_service = mock_history_service
        
        with pytest.raises(Exception, match="Session .* not found"):
            await alert_service.resume_paused_session(session_id)
    
    @pytest.mark.asyncio
    async def test_resume_session_not_paused(self) -> None:
        """Test resuming a non-paused session raises error."""
        session_id = "test-session"
        
        mock_session = MagicMock(spec=AlertSession)
        mock_session.status = AlertSessionStatus.COMPLETED.value
        
        mock_history_service = MagicMock()
        mock_history_service.get_session.return_value = mock_session
        
        mock_settings = MagicMock()
        mock_settings.agent_config_path = None
        
        with patch('tarsy.services.alert_service.RunbookService'):
            alert_service = AlertService(settings=mock_settings)
        
        alert_service.history_service = mock_history_service
        
        with pytest.raises(Exception, match="is not paused"):
            await alert_service.resume_paused_session(session_id)
    
    @pytest.mark.asyncio
    async def test_resume_no_paused_stage_found(self) -> None:
        """Test resuming when no paused stage exists raises error."""
        session_id = "test-session"
        
        mock_session = MagicMock(spec=AlertSession)
        mock_session.status = AlertSessionStatus.PAUSED.value
        
        # No paused stages
        mock_completed_stage = MagicMock(spec=StageExecution)
        mock_completed_stage.status = StageStatus.COMPLETED.value
        
        mock_history_service = MagicMock()
        mock_history_service.get_session.return_value = mock_session
        mock_history_service.get_stage_executions = AsyncMock(return_value=[mock_completed_stage])
        
        mock_settings = MagicMock()
        mock_settings.agent_config_path = None
        
        with patch('tarsy.services.alert_service.RunbookService'):
            alert_service = AlertService(settings=mock_settings)
        
        alert_service.history_service = mock_history_service
        
        with pytest.raises(Exception, match="No paused stage found"):
            await alert_service.resume_paused_session(session_id)
    
    @pytest.mark.asyncio
    async def test_resume_restores_conversation_history(self) -> None:
        """Test that resume restores conversation history from paused stage."""
        session_id = "test-session"
        execution_id = "test-execution-123"
        
        # Create paused stage with conversation history
        conversation_state = {
            "messages": [
                {"role": "user", "content": "Question"},
                {"role": "assistant", "content": "Thought: Analyzing..."}
            ]
        }
        
        mock_paused_stage = MagicMock(spec=StageExecution)
        mock_paused_stage.status = StageStatus.PAUSED.value
        mock_paused_stage.stage_name = "analysis"
        mock_paused_stage.execution_id = execution_id
        mock_paused_stage.current_iteration = 30
        mock_paused_stage.parallel_type = None  # Non-parallel stage
        mock_paused_stage.stage_output = {
            "status": "paused",
            "agent_name": "TestAgent",
            "stage_name": "analysis",
            "timestamp_us": 1234567890,
            "result_summary": "Paused analysis",
            "paused_conversation_state": conversation_state
        }
        
        mock_session = MagicMock(spec=AlertSession)
        mock_session.status = AlertSessionStatus.PAUSED.value
        mock_session.alert_type = "kubernetes"
        mock_session.alert_data = {}
        mock_session.started_at_us = 1000000
        mock_session.runbook_url = None
        mock_session.mcp_selection = None
        mock_session.author = None
        mock_session.chain_config = MagicMock()
        mock_session.chain_config.chain_id = "test-chain"
        
        mock_history_service = MagicMock()
        mock_history_service.get_session.return_value = mock_session
        mock_history_service.get_stage_executions = AsyncMock(return_value=[mock_paused_stage])
        
        mock_settings = MagicMock()
        mock_settings.agent_config_path = None
        
        with patch('tarsy.services.alert_service.RunbookService'):
            alert_service = AlertService(settings=mock_settings)
        
        alert_service.history_service = mock_history_service
        alert_service.session_manager.update_session_status = MagicMock()
        
        # Mock final_analysis_summarizer (not used in this test, but needs to exist)
        mock_summarizer = AsyncMock()
        alert_service.final_analysis_summarizer = mock_summarizer
        
        alert_service._execute_chain_stages = AsyncMock(
            return_value=ChainExecutionResult(
                status=ChainStatus.COMPLETED,
                timestamp_us=1234567890
            )
        )
        
        with patch.object(alert_service, 'mcp_client_factory') as mock_mcp_factory:
            mock_mcp_factory.create_client = AsyncMock()
            
            with patch('tarsy.services.events.event_helpers.publish_session_resumed', new=AsyncMock()), \
                 patch('tarsy.services.events.event_helpers.publish_session_completed', new=AsyncMock()), \
                 patch('tarsy.hooks.hook_context.stage_execution_context'):
                
                await alert_service.resume_paused_session(session_id)
        
        # Verify _execute_chain_stages was called with a ChainContext that has
        # the paused conversation state restored for the analysis stage
        alert_service._execute_chain_stages.assert_called_once()
        call_args = alert_service._execute_chain_stages.call_args[0]
        chain_definition_arg = call_args[0]
        chain_context_arg = call_args[1]
        
        # Verify chain definition
        assert chain_definition_arg.chain_id == "test-chain"
        
        # Verify the paused stage output was reconstructed in ChainContext
        # Note: Paused non-parallel stages are now stored by execution_id (for lookup consistency)
        assert execution_id in chain_context_arg.stage_outputs
        paused_result = chain_context_arg.stage_outputs[execution_id]
        assert paused_result.paused_conversation_state == conversation_state
    
    @pytest.mark.asyncio
    async def test_resume_handles_re_pause(self) -> None:
        """Test that resume handles session pausing again correctly."""
        session_id = "test-session"
        
        mock_session = MagicMock(spec=AlertSession)
        mock_session.status = AlertSessionStatus.PAUSED.value
        mock_session.alert_type = "kubernetes"
        mock_session.alert_data = {}
        mock_session.started_at_us = 1000000
        mock_session.runbook_url = None
        mock_session.mcp_selection = None
        mock_session.author = None
        mock_session.chain_config = MagicMock()
        mock_session.chain_config.chain_id = "test-chain"
        
        mock_paused_stage = MagicMock(spec=StageExecution)
        mock_paused_stage.status = StageStatus.PAUSED.value
        mock_paused_stage.stage_name = "analysis"
        mock_paused_stage.current_iteration = 30
        mock_paused_stage.stage_output = None
        
        mock_history_service = MagicMock()
        mock_history_service.get_session.return_value = mock_session
        mock_history_service.get_stage_executions = AsyncMock(return_value=[mock_paused_stage])
        
        mock_settings = MagicMock()
        mock_settings.agent_config_path = None
        
        with patch('tarsy.services.alert_service.RunbookService'):
            alert_service = AlertService(settings=mock_settings)
        
        alert_service.history_service = mock_history_service
        alert_service.session_manager.update_session_status = MagicMock()
        
        # Mock final_analysis_summarizer (not used for PAUSED status)
        mock_summarizer = AsyncMock()
        alert_service.final_analysis_summarizer = mock_summarizer
        
        # Chain execution returns PAUSED again
        alert_service._execute_chain_stages = AsyncMock(
            return_value=ChainExecutionResult(
                status=ChainStatus.PAUSED,
                timestamp_us=1234567890,
                final_analysis="Session paused again"
            )
        )
        
        with patch.object(alert_service, 'mcp_client_factory') as mock_mcp_factory:
            mock_mcp_factory.create_client = AsyncMock()
            
            with patch('tarsy.services.events.event_helpers.publish_session_resumed', new=AsyncMock()), \
                 patch('tarsy.hooks.hook_context.stage_execution_context'):
                
                result = await alert_service.resume_paused_session(session_id)
        
        # Verify returns formatted pause message in Markdown report
        assert "# Alert Analysis Report" in result
        assert "paused again" in result.lower()
        assert "**Processing Chain:** test-chain" in result
        
        # Verify no COMPLETED status was set (should stay PAUSED)
        # Handle both positional and keyword argument styles
        status_calls = [
            call.kwargs.get("status") or (call.args[1] if len(call.args) > 1 else None)
            for call in alert_service.session_manager.update_session_status.call_args_list
        ]
        assert AlertSessionStatus.COMPLETED.value not in status_calls
    
    @pytest.mark.asyncio
    async def test_resume_handles_none_final_analysis(self) -> None:
        """Test that resume handles None final_analysis gracefully when session pauses again."""
        session_id = "test-session"
        
        mock_session = MagicMock(spec=AlertSession)
        mock_session.status = AlertSessionStatus.PAUSED.value
        mock_session.alert_type = "kubernetes"
        mock_session.alert_data = {}
        mock_session.started_at_us = 1000000
        mock_session.runbook_url = None
        mock_session.mcp_selection = None
        mock_session.author = None
        mock_session.chain_config = MagicMock()
        mock_session.chain_config.chain_id = "test-chain"
        
        mock_paused_stage = MagicMock(spec=StageExecution)
        mock_paused_stage.status = StageStatus.PAUSED.value
        mock_paused_stage.stage_name = "analysis"
        mock_paused_stage.current_iteration = 30
        mock_paused_stage.stage_output = None
        
        mock_history_service = MagicMock()
        mock_history_service.get_session.return_value = mock_session
        mock_history_service.get_stage_executions = AsyncMock(return_value=[mock_paused_stage])
        
        mock_settings = MagicMock()
        mock_settings.agent_config_path = None
        
        with patch('tarsy.services.alert_service.RunbookService'):
            alert_service = AlertService(settings=mock_settings)
        
        alert_service.history_service = mock_history_service
        alert_service.session_manager.update_session_status = MagicMock()
        
        # Mock final_analysis_summarizer (not used for PAUSED status)
        mock_summarizer = AsyncMock()
        alert_service.final_analysis_summarizer = mock_summarizer
        
        # Chain execution returns PAUSED with None final_analysis (the bug case)
        alert_service._execute_chain_stages = AsyncMock(
            return_value=ChainExecutionResult(
                status=ChainStatus.PAUSED,
                timestamp_us=1234567890,
                final_analysis=None  # This was causing the bug
            )
        )
        
        with patch.object(alert_service, 'mcp_client_factory') as mock_mcp_factory:
            mock_mcp_factory.create_client = AsyncMock()
            
            with patch('tarsy.services.events.event_helpers.publish_session_resumed', new=AsyncMock()), \
                 patch('tarsy.hooks.hook_context.stage_execution_context'):
                
                result = await alert_service.resume_paused_session(session_id)
        
        # Verify returns formatted response with default pause message
        assert "# Alert Analysis Report" in result
        assert "Session paused again - waiting for user to resume" in result
        assert "**Processing Chain:** test-chain" in result
        
        # Verify no COMPLETED status was set (should stay PAUSED)
        status_calls = [
            call.kwargs.get("status") or (call.args[1] if len(call.args) > 1 else None)
            for call in alert_service.session_manager.update_session_status.call_args_list
        ]
        assert AlertSessionStatus.COMPLETED.value not in status_calls
    
    @pytest.mark.asyncio
    async def test_resume_history_service_not_available(self) -> None:
        """Test resume fails gracefully when history service unavailable."""
        mock_settings = MagicMock()
        mock_settings.agent_config_path = None
        
        with patch('tarsy.services.alert_service.RunbookService'):
            alert_service = AlertService(settings=mock_settings)
        
        alert_service.history_service = None
        
        with pytest.raises(Exception, match="History service not available"):
            await alert_service.resume_paused_session("test-session")
    
    @pytest.mark.asyncio
    async def test_resume_handles_chain_execution_failure(self) -> None:
        """Test that resume returns formatted error response when chain execution fails."""
        session_id = "test-session"
        
        mock_session = MagicMock(spec=AlertSession)
        mock_session.status = AlertSessionStatus.PAUSED.value
        mock_session.alert_type = "kubernetes"
        mock_session.alert_data = {"severity": "critical", "environment": "production"}
        mock_session.started_at_us = 1000000
        mock_session.runbook_url = None
        mock_session.mcp_selection = None
        mock_session.author = None
        mock_session.chain_config = MagicMock()
        mock_session.chain_config.chain_id = "test-chain"
        mock_session.chain_config.stages = []
        
        mock_paused_stage = MagicMock(spec=StageExecution)
        mock_paused_stage.status = StageStatus.PAUSED.value
        mock_paused_stage.stage_name = "analysis"
        mock_paused_stage.current_iteration = 30
        mock_paused_stage.stage_output = None
        
        mock_history_service = MagicMock()
        mock_history_service.get_session.return_value = mock_session
        mock_history_service.get_stage_executions = AsyncMock(return_value=[mock_paused_stage])
        
        mock_settings = MagicMock()
        mock_settings.agent_config_path = None
        
        with patch('tarsy.services.alert_service.RunbookService'):
            alert_service = AlertService(settings=mock_settings)
        
        alert_service.history_service = mock_history_service
        alert_service.runbook_service = MagicMock()
        alert_service.runbook_service.download_runbook = AsyncMock(return_value="# Default runbook")
        alert_service.session_manager.update_session_status = MagicMock()
        
        # Mock final_analysis_summarizer (not used for FAILED status)
        mock_summarizer = AsyncMock()
        alert_service.final_analysis_summarizer = mock_summarizer
        
        # Chain execution returns FAILED status
        alert_service._execute_chain_stages = AsyncMock(
            return_value=ChainExecutionResult(
                status=ChainStatus.FAILED,
                timestamp_us=1234567890,
                error="Stage 'analysis' failed: Database connection timeout"
            )
        )
        
        with patch.object(alert_service, 'mcp_client_factory') as mock_mcp_factory:
            mock_mcp_factory.create_client = AsyncMock()
            
            with patch('tarsy.services.events.event_helpers.publish_session_resumed', new=AsyncMock()), \
                 patch('tarsy.services.events.event_helpers.publish_session_failed', new=AsyncMock()) as mock_failed_event, \
                 patch('tarsy.hooks.hook_context.stage_execution_context'):
                
                result = await alert_service.resume_paused_session(session_id)
        
        # Verify returns formatted error response (Markdown format)
        assert "# Alert Processing Error" in result
        assert "**Alert Type:** kubernetes" in result
        assert "Database connection timeout" in result
        assert "## Troubleshooting" in result
        
        # Verify session status updated to FAILED
        # Handle both positional and keyword argument styles
        status_calls = [
            call.kwargs.get("status") or (call.args[1] if len(call.args) > 1 else None)
            for call in alert_service.session_manager.update_session_status.call_args_list
        ]
        assert AlertSessionStatus.FAILED.value in status_calls
        
        # Verify failed event was published
        mock_failed_event.assert_called_once_with(session_id)

