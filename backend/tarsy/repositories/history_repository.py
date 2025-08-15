"""
Repository for Alert Processing History database operations.

Provides database access layer for alert processing history with SQLModel,
supporting comprehensive audit trails, chronological timeline reconstruction,
and advanced querying capabilities using Unix timestamps for optimal performance.
"""

from typing import Any, Dict, List, Optional, Union

from sqlmodel import Session, asc, desc, func, select, and_, or_

from tarsy.models.constants import AlertSessionStatus
from tarsy.models.history import AlertSession, StageExecution
from tarsy.models.unified_interactions import LLMInteraction, MCPInteraction
from tarsy.models.domain_models import (
    InteractionData,
    SessionData,
    SessionTimelineData,
    StageData,
    PaginatedSessionsData,
    SessionSummaryData,
    StageInteractionCounts
)
from tarsy.models.api_models import InteractionSummary
from tarsy.repositories.base_repository import BaseRepository
from tarsy.utils.logger import get_logger

logger = get_logger(__name__)


class HistoryRepository:
    """
    Repository for alert processing history data operations.
    
    Provides comprehensive database operations for alert sessions and their
    associated interactions with filtering, pagination, and timeline support.
    """
    
    def __init__(self, session: Session):
        """
        Initialize history repository with database session.
        
        Args:
            session: SQLModel database session
        """
        self.session = session
        self.alert_session_repo = BaseRepository(session, AlertSession)
        self.llm_interaction_repo = BaseRepository(session, LLMInteraction)
        self.mcp_communication_repo = BaseRepository(session, MCPInteraction)
        
    # AlertSession operations
    def create_alert_session(self, alert_session: AlertSession) -> Optional[AlertSession]:
        """
        Create a new alert processing session.
        
        Args:
            alert_session: AlertSession instance to create
            
        Returns:
            The created AlertSession with database-generated fields, or None if creation failed
        """
        try:
            # Check for existing session with the same alert_id to prevent duplicates
            existing_session = self.session.exec(
                select(AlertSession).where(AlertSession.alert_id == alert_session.alert_id)
            ).first()
            
            if existing_session:
                logger.warning(f"Alert session already exists for alert_id {alert_session.alert_id}, skipping duplicate creation")
                return existing_session
            
            return self.alert_session_repo.create(alert_session)
        except Exception as e:
            logger.error(f"Failed to create alert session {alert_session.session_id}: {str(e)}")
            return None
    
    def get_alert_session(self, session_id: str) -> Optional[AlertSession]:
        """
        Retrieve an alert session by ID.
        
        Args:
            session_id: The session identifier
            
        Returns:
            AlertSession instance if found, None otherwise
        """
        return self.alert_session_repo.get_by_id(session_id)
    
    def update_alert_session(self, alert_session: AlertSession) -> bool:
        """
        Update an existing alert session.
        
        Args:
            alert_session: AlertSession instance to update
            
        Returns:
            True if update was successful, False otherwise
        """
        try:
            self.alert_session_repo.update(alert_session)
            return True
        except Exception as e:
            logger.error(f"Failed to update alert session {alert_session.session_id}: {str(e)}")
            return False
    
    def get_alert_sessions(
        self,
        status: Optional[Union[str, List[str]]] = None,
        agent_type: Optional[str] = None,
        alert_type: Optional[str] = None,
        search: Optional[str] = None,
        start_date_us: Optional[int] = None,
        end_date_us: Optional[int] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """
        Retrieve alert sessions with filtering and pagination.
        
        Supports complex filter combinations using AND logic as specified
        in the design document. Search functionality uses OR logic across
        multiple text fields.
        
        Args:
            status: Filter by processing status (single value or list of values)
            agent_type: Filter by agent type
            alert_type: Filter by alert type
            search: Text search across error messages, analysis, and alert content
            start_date_us: Filter sessions started after this Unix timestamp (microseconds)
            end_date_us: Filter sessions started before this Unix timestamp (microseconds)
            page: Page number for pagination
            page_size: Number of results per page
            
        Returns:
            Dictionary containing sessions list and pagination info
        """
        try:
            # Build the base query
            statement = select(AlertSession)
            conditions = []
            
            # Apply filters using AND logic (multiple filters narrow results)
            if status:
                if isinstance(status, list):
                    conditions.append(AlertSession.status.in_(status))
                else:
                    conditions.append(AlertSession.status == status)
            if agent_type:
                conditions.append(AlertSession.agent_type == agent_type)
            if alert_type:
                conditions.append(AlertSession.alert_type == alert_type)
            
            # Search functionality using OR logic across multiple text fields
            if search:
                search_term = f"%{search.lower()}%"
                search_conditions = []
                
                # Search in error_message field
                search_conditions.append(
                    func.lower(AlertSession.error_message).like(search_term)
                )
                
                # Search in final_analysis field
                search_conditions.append(
                    func.lower(AlertSession.final_analysis).like(search_term)
                )
                
                # Search in alert_type field (NamespaceTerminating, UnidledPods, etc.)
                search_conditions.append(
                    func.lower(AlertSession.alert_type).like(search_term)
                )
                
                # Search in agent_type field (kubernetes, base, etc.)
                search_conditions.append(
                    func.lower(AlertSession.agent_type).like(search_term)
                )
                
                # Search in JSON alert_data fields (SQLite JSON support)
                # Search alert message
                search_conditions.append(
                    func.lower(func.json_extract(AlertSession.alert_data, '$.message')).like(search_term)
                )
                
                # Search alert context 
                search_conditions.append(
                    func.lower(func.json_extract(AlertSession.alert_data, '$.context')).like(search_term)
                )
                
                # Search namespace, pod, cluster for Kubernetes alerts
                search_conditions.append(
                    func.lower(func.json_extract(AlertSession.alert_data, '$.namespace')).like(search_term)
                )
                search_conditions.append(
                    func.lower(func.json_extract(AlertSession.alert_data, '$.pod')).like(search_term)
                )
                search_conditions.append(
                    func.lower(func.json_extract(AlertSession.alert_data, '$.cluster')).like(search_term)
                )
                
                # Search severity (high, critical, medium, low)
                search_conditions.append(
                    func.lower(func.json_extract(AlertSession.alert_data, '$.severity')).like(search_term)
                )
                
                # Search environment (production, staging, development)
                search_conditions.append(
                    func.lower(func.json_extract(AlertSession.alert_data, '$.environment')).like(search_term)
                )
                
                # Search runbook URL (might contain useful keywords)
                search_conditions.append(
                    func.lower(func.json_extract(AlertSession.alert_data, '$.runbook')).like(search_term)
                )
                
                # Search external alert ID
                search_conditions.append(
                    func.lower(func.json_extract(AlertSession.alert_data, '$.id')).like(search_term)
                )
                
                # Search session metadata (additional context)
                search_conditions.append(
                    func.lower(func.json_extract(AlertSession.session_metadata, '$')).like(search_term)
                )
                
                # Combine all search conditions with OR logic
                conditions.append(or_(*search_conditions))
            
            if start_date_us:
                conditions.append(AlertSession.started_at_us >= start_date_us)
            if end_date_us:
                conditions.append(AlertSession.started_at_us <= end_date_us)
            
            # Apply all conditions with AND logic
            if conditions:
                statement = statement.where(and_(*conditions))
            
            # Order by started_at descending (most recent first)
            statement = statement.order_by(desc(AlertSession.started_at_us))
            
            # Count total results for pagination
            count_statement = select(func.count(AlertSession.session_id))
            if conditions:
                count_statement = count_statement.where(and_(*conditions))
            total_items = self.session.exec(count_statement).first() or 0
            
            # Apply pagination
            offset = (page - 1) * page_size
            statement = statement.offset(offset).limit(page_size)
            
            # Execute query
            sessions = self.session.exec(statement).all()
            
            # Get interaction counts for each session to avoid lazy loading issues
            # Create subqueries for efficient counting
            interaction_counts = {}
            
            if sessions:
                session_ids = [s.session_id for s in sessions]
                
                # Count LLM interactions for each session
                llm_count_query = select(
                    LLMInteraction.session_id,
                    func.count(LLMInteraction.interaction_id).label('count')
                ).where(
                    LLMInteraction.session_id.in_(session_ids)
                ).group_by(LLMInteraction.session_id)
                
                llm_results = self.session.exec(llm_count_query).all()
                llm_counts = {result.session_id: result.count for result in llm_results}
                
                # Count MCP communications for each session
                mcp_count_query = select(
                    MCPInteraction.session_id,
                    func.count(MCPInteraction.communication_id).label('count')
                ).where(
                    MCPInteraction.session_id.in_(session_ids)
                ).group_by(MCPInteraction.session_id)
                
                mcp_results = self.session.exec(mcp_count_query).all()
                mcp_counts = {result.session_id: result.count for result in mcp_results}
                
                # Combine counts for each session
                for session_id in session_ids:
                    interaction_counts[session_id] = {
                        'llm_interactions': llm_counts.get(session_id, 0),
                        'mcp_communications': mcp_counts.get(session_id, 0)
                    }
            
            # Calculate pagination info
            total_pages = (total_items + page_size - 1) // page_size
            
            return {
                "sessions": sessions,
                "interaction_counts": interaction_counts,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total_pages": total_pages,
                    "total_items": total_items
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to get alert sessions: {str(e)}")
            return {
                "sessions": [],
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total_pages": 0,
                    "total_items": 0
                }
            }

    def get_stage_interaction_counts(self, execution_ids: List[str]) -> Dict[str, Dict[str, int]]:
        """
        Get interaction counts grouped by stage execution ID using SQL aggregation.
        
        Args:
            execution_ids: List of stage execution IDs to get counts for
            
        Returns:
            Dictionary mapping execution_id to {'llm_interactions': count, 'mcp_communications': count}
        """
        if not execution_ids:
            return {}
            
        try:
            interaction_counts = {}
            
            # Count LLM interactions for each stage
            llm_count_query = select(
                LLMInteraction.stage_execution_id,
                func.count(LLMInteraction.interaction_id).label('count')
            ).where(
                LLMInteraction.stage_execution_id.in_(execution_ids)
            ).group_by(LLMInteraction.stage_execution_id)
            
            llm_results = self.session.exec(llm_count_query).all()
            llm_counts = {result.stage_execution_id: result.count for result in llm_results}
            
            # Count MCP communications for each stage
            mcp_count_query = select(
                MCPInteraction.stage_execution_id,
                func.count(MCPInteraction.communication_id).label('count')
            ).where(
                MCPInteraction.stage_execution_id.in_(execution_ids)
            ).group_by(MCPInteraction.stage_execution_id)
            
            mcp_results = self.session.exec(mcp_count_query).all()
            mcp_counts = {result.stage_execution_id: result.count for result in mcp_results}
            
            # Combine counts for each stage
            for execution_id in execution_ids:
                interaction_counts[execution_id] = {
                    'llm_interactions': llm_counts.get(execution_id, 0),
                    'mcp_communications': mcp_counts.get(execution_id, 0)
                }
                
            return interaction_counts
            
        except Exception as e:
            logger.error(f"Error retrieving stage interaction counts: {str(e)}")
            raise
    
    # LLMInteraction operations
    def create_llm_interaction(self, llm_interaction: LLMInteraction) -> LLMInteraction:
        """
        Create a new LLM interaction record.
        
        Args:
            llm_interaction: LLMInteraction instance to create
            
        Returns:
            The created LLMInteraction with database-generated fields
        """
        return self.llm_interaction_repo.create(llm_interaction)
    
    def get_llm_interactions_for_session(self, session_id: str) -> List[LLMInteraction]:
        """
        Get all LLM interactions for a session ordered by timestamp.
        
        Args:
            session_id: The session identifier
            
        Returns:
            List of LLMInteraction instances ordered by timestamp
        """
        try:
            statement = select(LLMInteraction).where(
                LLMInteraction.session_id == session_id
            ).order_by(asc(LLMInteraction.timestamp_us))
            
            return self.session.exec(statement).all()
        except Exception as e:
            logger.error(f"Failed to get LLM interactions for session {session_id}: {str(e)}")
            raise


    # MCPCommunication operations
    def create_mcp_communication(self, mcp_communication: MCPInteraction) -> MCPInteraction:
        """
        Create a new MCP communication record.
        
        Args:
            mcp_communication: MCPInteraction instance to create
            
        Returns:
            The created MCPInteraction with database-generated fields
        """
        return self.mcp_communication_repo.create(mcp_communication)
    
    def get_mcp_communications_for_session(self, session_id: str) -> List[MCPInteraction]:
        """
        Get all MCP communications for a session ordered by timestamp.
        
        Args:
            session_id: The session identifier
            
        Returns:
            List of MCPInteraction instances ordered by timestamp
        """
        try:
            statement = select(MCPInteraction).where(
                MCPInteraction.session_id == session_id
            ).order_by(asc(MCPInteraction.timestamp_us))
            
            return self.session.exec(statement).all()
        except Exception as e:
            logger.error(f"Failed to get MCP communications for session {session_id}: {str(e)}")
            raise


    # Timeline reconstruction operations
    def get_session_timeline(self, session_id: str) -> Dict[str, Any]:
        """
        Reconstruct chronological timeline for a session.
        
        Combines LLM interactions and MCP communications in chronological order
        using microsecond-precision Unix timestamps for exact ordering.
        
        Args:
            session_id: The session identifier
            
        Returns:
            Dictionary containing session details and chronological timeline with raw Unix timestamps
        """
        try:
            # Get the session
            session = self.get_alert_session(session_id)
            if not session:
                return {}
            
            # Get all interactions and communications
            llm_interactions = self.get_llm_interactions_for_session(session_id)
            mcp_communications = self.get_mcp_communications_for_session(session_id)
            
            # Build chronological timeline
            timeline_events = []
            
            # Add LLM interactions to timeline
            for interaction in llm_interactions:
                timeline_events.append({
                    "id": interaction.interaction_id,
                    "event_id": interaction.interaction_id,
                    "timestamp_us": interaction.timestamp_us,
                    "type": "llm",
                    "step_description": interaction.step_description,
                    "duration_ms": interaction.duration_ms,
                    "stage_execution_id": interaction.stage_execution_id,  # Chain context for stage association
                    "details": {
                        "request_json": interaction.request_json,
                        "response_json": interaction.response_json,
                        "model_name": interaction.model_name,
                        "tokens_used": interaction.token_usage,
                        "temperature": interaction.request_json.get('temperature') if interaction.request_json else None,
                        "success": interaction.success,
                        "error_message": interaction.error_message
                    }
                })
            
            # Add MCP communications to timeline
            for communication in mcp_communications:
                timeline_events.append({
                    "id": communication.communication_id,
                    "event_id": communication.communication_id,
                    "timestamp_us": communication.timestamp_us,
                    "type": "mcp",
                    "step_description": communication.step_description,
                    "duration_ms": communication.duration_ms,
                    "stage_execution_id": communication.stage_execution_id,  # Chain context for stage association
                    "details": {
                        "tool_name": communication.tool_name,
                        "server_name": communication.server_name,
                        "communication_type": communication.communication_type,
                        "parameters": communication.tool_arguments or {},
                        "result": communication.tool_result or {},
                        "available_tools": communication.available_tools or {},
                        "success": communication.success
                    }
                })
            
            # Sort all events by timestamp_us for exact chronological ordering
            timeline_events.sort(key=lambda x: x["timestamp_us"])
            
            return {
                "session": {
                    "session_id": session.session_id,
                    "alert_id": session.alert_id,
                    "alert_data": session.alert_data,
                    "agent_type": session.agent_type,
                    "alert_type": session.alert_type,
                    "status": session.status,
                    "started_at_us": session.started_at_us,
                    "completed_at_us": session.completed_at_us,
                    "error_message": session.error_message,
                    "final_analysis": session.final_analysis,
                    "session_metadata": session.session_metadata,
                    "total_interactions": len(llm_interactions) + len(mcp_communications),
                    # Pre-calculated interaction counts (consistent with session list)
                    "llm_interaction_count": len(llm_interactions),
                    "mcp_communication_count": len(mcp_communications),
                    # Chain-related fields
                    "chain_id": session.chain_id,
                    "chain_definition": session.chain_definition,
                    "current_stage_index": session.current_stage_index,
                    "current_stage_id": session.current_stage_id
                },
                "chronological_timeline": timeline_events,
                "llm_interactions": [
                    {
                        "interaction_id": interaction.interaction_id,
                        "timestamp_us": interaction.timestamp_us,
                        "step_description": interaction.step_description,
                        "model_name": interaction.model_name,
                        "duration_ms": interaction.duration_ms
                    }
                    for interaction in llm_interactions
                ],
                "mcp_communications": [
                    {
                        "communication_id": communication.communication_id,
                        "timestamp_us": communication.timestamp_us,
                        "step_description": communication.step_description,
                        "server_name": communication.server_name,
                        "tool_name": communication.tool_name,
                        "success": communication.success,
                        "duration_ms": communication.duration_ms
                    }
                    for communication in mcp_communications
                ]
            }
            
        except Exception as e:
            logger.error(f"Failed to reconstruct timeline for session {session_id}: {str(e)}")
            return None
    
    # Utility operations
    def get_active_sessions(self) -> List[AlertSession]:
        """
        Get all currently active (in_progress or pending) sessions.
        
        Returns:
            List of AlertSession instances that are currently active
        """
        try:
            statement = select(AlertSession).where(
                AlertSession.status.in_(AlertSessionStatus.active_values())
            ).order_by(desc(AlertSession.started_at_us))
            
            return self.session.exec(statement).all()
        except Exception as e:
            logger.error(f"Failed to get active sessions: {str(e)}")
            raise
    
    def get_filter_options(self) -> Dict[str, Any]:
        """
        Get dynamic filter options based on actual data in the database.
        
        Returns:
            Dictionary containing available filter options
        """
        try:
            # Get distinct agent types from the database
            agent_types = self.session.exec(
                select(AlertSession.agent_type).distinct()
                .where(AlertSession.agent_type.is_not(None))
            ).all()
            
            # Get distinct alert types from the database
            alert_types = self.session.exec(
                select(AlertSession.alert_type).distinct()
                .where(AlertSession.alert_type.is_not(None))
            ).all()
            
            # Always return all possible status options for consistent filtering,
            # even if some statuses don't currently exist in the database
            from tarsy.models.constants import AlertSessionStatus
            
            return {
                "agent_types": sorted(list(agent_types)) if agent_types else [],
                "alert_types": sorted(list(alert_types)) if alert_types else [],
                "status_options": AlertSessionStatus.values(),
                "time_ranges": [
                    {"label": "Last Hour", "value": "1h"},
                    {"label": "Last 4 Hours", "value": "4h"},
                    {"label": "Today", "value": "today"},
                    {"label": "This Week", "value": "week"},
                    {"label": "This Month", "value": "month"}
                ]
            }
            
        except Exception as e:
            logger.error(f"Failed to get filter options: {str(e)}")
            raise

    # Stage Execution Methods for Chain Processing
    def create_stage_execution(self, stage_execution: StageExecution) -> str:
        """Create a new stage execution record."""
        try:
            self.session.add(stage_execution)
            self.session.commit()
            self.session.refresh(stage_execution)
            return stage_execution.execution_id
        except Exception as e:
            logger.error(f"Failed to create stage execution: {str(e)}")
            raise

    def update_stage_execution(self, stage_execution: StageExecution) -> bool:
        """Update an existing stage execution record."""
        try:
            # Fetch the existing record by primary key
            existing_execution = self.session.get(StageExecution, stage_execution.execution_id)
            if existing_execution is None:
                logger.error(f"Stage execution with id {stage_execution.execution_id} not found")
                raise ValueError(f"Stage execution with id {stage_execution.execution_id} not found")
            
            # Update only the fields that can change during execution
            existing_execution.status = stage_execution.status
            existing_execution.started_at_us = stage_execution.started_at_us
            existing_execution.completed_at_us = stage_execution.completed_at_us
            existing_execution.duration_ms = stage_execution.duration_ms
            existing_execution.stage_output = stage_execution.stage_output
            existing_execution.error_message = stage_execution.error_message
            
            self.session.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to update stage execution: {str(e)}")
            raise

    def update_session_current_stage(
        self, 
        session_id: str, 
        current_stage_index: int, 
        current_stage_id: str
    ) -> bool:
        """Update the current stage information for a session."""
        try:
            statement = select(AlertSession).where(AlertSession.session_id == session_id)
            session = self.session.exec(statement).first()
            if session:
                session.current_stage_index = current_stage_index
                session.current_stage_id = current_stage_id
                self.session.add(session)
                self.session.commit()
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to update session current stage: {str(e)}")
            raise

    def get_session_with_stages(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session with all stage execution details."""
        try:
            # Get session
            session_stmt = select(AlertSession).where(AlertSession.session_id == session_id)
            alert_session = self.session.exec(session_stmt).first()
            
            if not alert_session:
                return None
            
            # Get stage executions
            stages_stmt = (
                select(StageExecution)
                .where(StageExecution.session_id == session_id)
                .order_by(StageExecution.stage_index)
            )
            stage_executions = self.session.exec(stages_stmt).all()
            
            return {
                "session": alert_session.model_dump(),
                "stages": [stage.model_dump() for stage in stage_executions]
            }
        except Exception as e:
            logger.error(f"Failed to get session with stages: {str(e)}")
            raise
    
    def get_stage_execution(self, execution_id: str) -> Optional['StageExecution']:
        """Get a single stage execution by ID."""
        try:
            stmt = select(StageExecution).where(StageExecution.execution_id == execution_id)
            stage_execution = self.session.exec(stmt).first()
            return stage_execution
        except Exception as e:
            logger.error(f"Failed to get stage execution {execution_id}: {str(e)}")
            raise
    
    # NEW TYPED METHODS - Replacing Dict[str, Any] with proper domain models
    
    def get_session_data(self, session_id: str) -> Optional[SessionData]:
        """
        Get complete session data with type safety.
        
        Args:
            session_id: The session identifier
            
        Returns:
            SessionData instance with complete session information, or None if not found
        """
        try:
            # Get the session
            session = self.get_alert_session(session_id)
            if not session:
                return None
            
            # Get interaction counts
            llm_interactions = self.get_llm_interactions_for_session(session_id)
            mcp_communications = self.get_mcp_communications_for_session(session_id)
            
            # Get stages if this is a chain execution
            stages = []
            if session.chain_id:
                stage_data = self.get_session_with_stages(session_id)
                if stage_data:
                    stage_executions = [StageExecution(**stage) for stage in stage_data.get('stages', [])]
                    for stage_exec in stage_executions:
                        stage_interactions = self._get_interactions_for_stage(stage_exec.execution_id)
                        interaction_summary = self._calculate_stage_interaction_summary(stage_interactions)
                        stages.append(StageData(
                            stage_execution=stage_exec,
                            interactions=stage_interactions,
                            interaction_summary=interaction_summary
                        ))
            
            return SessionData(
                session=session,
                llm_interaction_count=len(llm_interactions),
                mcp_communication_count=len(mcp_communications),
                total_interaction_count=len(llm_interactions) + len(mcp_communications),
                stages=stages
            )
            
        except Exception as e:
            logger.error(f"Failed to get session data for {session_id}: {str(e)}")
            raise
    
    def get_session_timeline_data(self, session_id: str) -> Optional[SessionTimelineData]:
        """
        Get complete session timeline with type safety.
        
        Args:
            session_id: The session identifier
            
        Returns:
            SessionTimelineData instance with chronological timeline, or None if not found
        """
        try:
            # Get session data
            session_data = self.get_session_data(session_id)
            if not session_data:
                return None
            
            # Get all interactions and convert to InteractionData
            llm_interactions = self.get_llm_interactions_for_session(session_id)
            mcp_communications = self.get_mcp_communications_for_session(session_id)
            
            # Convert to unified InteractionData and sort chronologically
            chronological_timeline = []
            
            for llm in llm_interactions:
                chronological_timeline.append(InteractionData.from_llm_interaction(llm))
            
            for mcp in mcp_communications:
                chronological_timeline.append(InteractionData.from_mcp_interaction(mcp))
            
            # Sort by timestamp
            chronological_timeline.sort(key=lambda x: x.timestamp_us)
            
            return SessionTimelineData(
                session_data=session_data,
                chronological_timeline=chronological_timeline
            )
            
        except Exception as e:
            logger.error(f"Failed to get session timeline data for {session_id}: {str(e)}")
            raise
    
    def get_sessions_paginated(
        self,
        status: Optional[Union[str, List[str]]] = None,
        agent_type: Optional[str] = None,
        alert_type: Optional[str] = None,
        search: Optional[str] = None,
        start_date_us: Optional[int] = None,
        end_date_us: Optional[int] = None,
        page: int = 1,
        page_size: int = 20
    ) -> PaginatedSessionsData:
        """
        Get paginated sessions with type safety.
        
        Returns:
            PaginatedSessionsData with sessions and interaction counts
        """
        try:
            # Use existing method to get data
            result = self.get_alert_sessions(
                status=status,
                agent_type=agent_type,
                alert_type=alert_type,
                search=search,
                start_date_us=start_date_us,
                end_date_us=end_date_us,
                page=page,
                page_size=page_size
            )
            
            return PaginatedSessionsData(
                sessions=result.get('sessions', []),
                interaction_counts=result.get('interaction_counts', {}),
                total_items=result.get('pagination', {}).get('total_items', 0)
            )
            
        except Exception as e:
            logger.error(f"Failed to get paginated sessions: {str(e)}")
            raise
    
    def _get_interactions_for_stage(self, execution_id: str) -> List[InteractionData]:
        """
        Get all interactions for a specific stage execution.
        
        Args:
            execution_id: Stage execution identifier
            
        Returns:
            List of InteractionData for the stage
        """
        try:
            interactions = []
            
            # Get LLM interactions for this stage
            llm_stmt = select(LLMInteraction).where(
                LLMInteraction.stage_execution_id == execution_id
            ).order_by(LLMInteraction.timestamp_us)
            llm_interactions = self.session.exec(llm_stmt).all()
            
            for llm in llm_interactions:
                interactions.append(InteractionData.from_llm_interaction(llm))
            
            # Get MCP interactions for this stage
            mcp_stmt = select(MCPInteraction).where(
                MCPInteraction.stage_execution_id == execution_id
            ).order_by(MCPInteraction.timestamp_us)
            mcp_communications = self.session.exec(mcp_stmt).all()
            
            for mcp in mcp_communications:
                interactions.append(InteractionData.from_mcp_interaction(mcp))
            
            # Sort chronologically
            interactions.sort(key=lambda x: x.timestamp_us)
            return interactions
            
        except Exception as e:
            logger.error(f"Failed to get interactions for stage {execution_id}: {str(e)}")
            raise
    
    def _calculate_stage_interaction_summary(self, interactions: List[InteractionData]) -> InteractionSummary:
        """
        Calculate interaction summary for a stage.
        
        Args:
            interactions: List of interactions for the stage
            
        Returns:
            InteractionSummary with counts and duration
        """
        llm_count = len([i for i in interactions if i.interaction_type == 'llm'])
        mcp_count = len([i for i in interactions if i.interaction_type == 'mcp'])
        total_duration_ms = sum(i.duration_ms or 0 for i in interactions)
        
        return InteractionSummary(
            llm_count=llm_count,
            mcp_count=mcp_count,
            total_count=llm_count + mcp_count,
            duration_ms=total_duration_ms if total_duration_ms > 0 else None
        )