"""
Timeline conversion utilities.

Provides converters for transforming flat timeline structures from repository 
get_session_timeline() into the nested stage-based DetailedSession model.
This handles the major format difference between current dict-based timeline
and the new type-safe nested structure.
"""

from typing import Dict, List, Any, Optional
from collections import defaultdict

from tarsy.models.history_models import (
    DetailedSession, DetailedStage, 
    LLMInteraction, MCPInteraction,
    LLMEventDetails, MCPEventDetails,
    LLMInteractionSummary, MCPCommunicationSummary
)
from tarsy.models.constants import AlertSessionStatus, StageStatus
from tarsy.models.unified_interactions import LLMMessage
from tarsy.utils.logger import get_logger

logger = get_logger(__name__)


def _convert_timeline_event_to_interaction(event: Dict[str, Any]) -> Optional[LLMInteraction | MCPInteraction]:
    """
    Convert a single timeline event dict to typed interaction model.
    
    Args:
        event: Timeline event from chronological_timeline array
        
    Returns:
        LLMInteraction or MCPInteraction instance, or None if conversion fails
    """
    try:
        if event.get('type') == 'llm':
            # Extract LLM event details
            details_dict = event.get('details', {})
            
            # Convert request messages if available  
            messages = []
            request_json = details_dict.get('request_json', {})
            if request_json and isinstance(request_json, dict):
                for msg in request_json.get('messages', []):
                    if isinstance(msg, dict) and 'role' in msg and 'content' in msg:
                        messages.append(LLMMessage(role=msg['role'], content=msg['content']))
            
            # Extract token usage
            tokens_used = details_dict.get('tokens_used', {})
            input_tokens = tokens_used.get('prompt_tokens') if tokens_used else None
            output_tokens = tokens_used.get('completion_tokens') if tokens_used else None  
            total_tokens = tokens_used.get('total_tokens') if tokens_used else None
            
            llm_details = LLMEventDetails(
                messages=messages,
                model_name=details_dict.get('model_name', ''),
                temperature=details_dict.get('temperature'),
                success=details_dict.get('success', True),
                error_message=details_dict.get('error_message'),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                tool_calls=details_dict.get('tool_calls'),
                tool_results=details_dict.get('tool_results')
            )
            
            return LLMInteraction(
                id=event.get('id', event.get('event_id', '')),
                event_id=event.get('event_id', ''),
                timestamp_us=event.get('timestamp_us', 0),
                step_description=event.get('step_description', ''),
                duration_ms=event.get('duration_ms'),
                stage_execution_id=event.get('stage_execution_id', ''),
                details=llm_details
            )
            
        elif event.get('type') == 'mcp':
            # Extract MCP event details
            details_dict = event.get('details', {})
            
            mcp_details = MCPEventDetails(
                tool_name=details_dict.get('tool_name', ''),
                server_name=details_dict.get('server_name', ''),
                communication_type=details_dict.get('communication_type', ''),
                parameters=details_dict.get('parameters', {}),
                result=details_dict.get('result', {}),
                available_tools=details_dict.get('available_tools', {}),
                success=details_dict.get('success', True)
            )
            
            return MCPInteraction(
                id=event.get('id', event.get('event_id', '')),
                event_id=event.get('event_id', ''),
                timestamp_us=event.get('timestamp_us', 0),
                step_description=event.get('step_description', ''),
                duration_ms=event.get('duration_ms'),
                stage_execution_id=event.get('stage_execution_id', ''),
                details=mcp_details
            )
    
    except Exception as e:
        # Log conversion error but don't fail entire conversion
        logger.warning(f"Failed to convert timeline event: {e}")
    
    return None


def session_timeline_to_detailed_session(
    timeline_response: Dict[str, Any],
    stages_data: Optional[List[Dict[str, Any]]] = None
) -> DetailedSession:
    """
    Convert repository get_session_timeline() response to DetailedSession.
    
    Transforms flat timeline structure into nested stage-based structure with
    interactions grouped by stage_execution_id.
    
    Args:
        timeline_response: Dict from repository get_session_timeline() with:
            - session: Dict with session data
            - chronological_timeline: List of event dicts  
            - llm_interactions: List of summary dicts (optional)
            - mcp_communications: List of summary dicts (optional)
        stages_data: Optional stage execution data from get_session_with_stages()
    
    Returns:
        DetailedSession instance with nested stage structure
    """
    session_data = timeline_response.get('session', {})
    timeline_events = timeline_response.get('chronological_timeline', [])
    
    # Group timeline events by stage_execution_id
    events_by_stage: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for event in timeline_events:
        stage_id = event.get('stage_execution_id', 'unknown')
        events_by_stage[stage_id].append(event)
    
    # Convert events to typed interactions by stage
    stages = []
    
    # If we have stage execution data, use it to create proper DetailedStage objects
    if stages_data:
        for stage_dict in stages_data:
            stage_execution_id = stage_dict.get('execution_id', '')
            stage_events = events_by_stage.get(stage_execution_id, [])
            
            # Convert events to interactions
            llm_interactions = []
            mcp_communications = []
            
            for event in stage_events:
                interaction = _convert_timeline_event_to_interaction(event)
                if isinstance(interaction, LLMInteraction):
                    llm_interactions.append(interaction)
                elif isinstance(interaction, MCPInteraction):
                    mcp_communications.append(interaction)
            
            # Create DetailedStage
            detailed_stage = DetailedStage(
                execution_id=stage_dict.get('execution_id', ''),
                session_id=stage_dict.get('session_id', session_data.get('session_id', '')),
                stage_id=stage_dict.get('stage_id', ''),
                stage_index=stage_dict.get('stage_index', 0),
                stage_name=stage_dict.get('stage_name', ''),
                agent=stage_dict.get('agent', ''),
                status=StageStatus(stage_dict.get('status', 'pending')),
                started_at_us=stage_dict.get('started_at_us'),
                completed_at_us=stage_dict.get('completed_at_us'), 
                duration_ms=stage_dict.get('duration_ms'),
                stage_output=stage_dict.get('stage_output'),
                error_message=stage_dict.get('error_message'),
                llm_interactions=llm_interactions,
                mcp_communications=mcp_communications,
                llm_interaction_count=len(llm_interactions),
                mcp_communication_count=len(mcp_communications),
                total_interactions=len(llm_interactions) + len(mcp_communications)
            )
            stages.append(detailed_stage)
    else:
        # Fallback: create stages based on unique stage_execution_ids in timeline
        for stage_execution_id, stage_events in events_by_stage.items():
            if stage_execution_id == 'unknown':
                continue
                
            # Convert events to interactions
            llm_interactions = []
            mcp_communications = []
            
            for event in stage_events:
                interaction = _convert_timeline_event_to_interaction(event)
                if isinstance(interaction, LLMInteraction):
                    llm_interactions.append(interaction)
                elif isinstance(interaction, MCPInteraction):
                    mcp_communications.append(interaction)
            
            # Create minimal DetailedStage (missing some stage metadata)
            detailed_stage = DetailedStage(
                execution_id=stage_execution_id,
                session_id=session_data.get('session_id', ''),
                stage_id=f"stage_{stage_execution_id}",
                stage_index=0,  # Can't determine without stage data
                stage_name=f"Stage {stage_execution_id}",
                agent="unknown",  # Can't determine without stage data
                status=StageStatus.COMPLETED,  # Assume completed if events exist
                llm_interactions=llm_interactions,
                mcp_communications=mcp_communications,
                llm_interaction_count=len(llm_interactions),
                mcp_communication_count=len(mcp_communications),
                total_interactions=len(llm_interactions) + len(mcp_communications)
            )
            stages.append(detailed_stage)
    
    # Create DetailedSession
    return DetailedSession(
        # Core session data
        session_id=session_data.get('session_id', ''),
        alert_id=session_data.get('alert_id', ''),
        alert_type=session_data.get('alert_type'),
        agent_type=session_data.get('agent_type', ''),
        status=AlertSessionStatus(session_data.get('status', 'pending')),
        started_at_us=session_data.get('started_at_us', 0),
        completed_at_us=session_data.get('completed_at_us'),
        error_message=session_data.get('error_message'),
        
        # Full session details
        alert_data=session_data.get('alert_data', {}),
        final_analysis=session_data.get('final_analysis'),
        session_metadata=session_data.get('session_metadata'),
        
        # Chain execution details
        chain_id=session_data.get('chain_id', ''),
        chain_definition=session_data.get('chain_definition', {}),
        current_stage_index=session_data.get('current_stage_index'),
        current_stage_id=session_data.get('current_stage_id'),
        
        # Interaction counts (from original session data)
        total_interactions=session_data.get('total_interactions', len(timeline_events)),
        llm_interaction_count=session_data.get('llm_interaction_count', 0),
        mcp_communication_count=session_data.get('mcp_communication_count', 0),
        
        # Complete stage executions with interactions
        stages=stages
    )
