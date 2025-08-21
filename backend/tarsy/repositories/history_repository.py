"""
Repository for Alert Processing History database operations.

Provides database access layer for alert processing history with SQLModel,
supporting comprehensive audit trails, chronological timeline reconstruction,
and advanced querying capabilities using Unix timestamps for optimal performance.
"""

from typing import Dict, List, Optional, Union
from collections import defaultdict

from sqlmodel import Session, asc, desc, func, select, and_, or_

from tarsy.models.constants import AlertSessionStatus, StageStatus
from tarsy.models.db_models import AlertSession, StageExecution
from tarsy.models.history_models import (
    PaginatedSessions, DetailedSession, FilterOptions, TimeRangeOption, PaginationInfo,
    SessionOverview, DetailedStage, LLMTimelineEvent, MCPTimelineEvent, 
    LLMEventDetails, MCPEventDetails, LLMMessage
)
from tarsy.models.unified_interactions import LLMInteraction, MCPInteraction
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
    
    def get_stage_execution(self, execution_id: str) -> Optional['StageExecution']:
        """Get a single stage execution by ID."""
        try:
            stmt = select(StageExecution).where(StageExecution.execution_id == execution_id)
            stage_execution = self.session.exec(stmt).first()
            return stage_execution
        except Exception as e:
            logger.error(f"Failed to get stage execution {execution_id}: {str(e)}")
            raise

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
    ) -> Optional[PaginatedSessions]:
        """
        Retrieve alert sessions with filtering and pagination.
        """
        try:
            # Defensively handle pagination parameters to prevent negative DB offsets
            page = max(1, int(page)) if page is not None else 1
            page_size = max(1, int(page_size)) if page_size is not None else 20
            # Build the base query (same logic as dict version but builds models directly)
            statement = select(AlertSession)
            conditions = []
            
            # Apply filters using AND logic
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
                search_conditions.append(func.lower(AlertSession.error_message).like(search_term))
                # Search in final_analysis field
                search_conditions.append(func.lower(AlertSession.final_analysis).like(search_term))
                # Search in alert_type field
                search_conditions.append(func.lower(AlertSession.alert_type).like(search_term))
                # Search in agent_type field
                search_conditions.append(func.lower(AlertSession.agent_type).like(search_term))
                # Search in JSON alert_data fields
                search_conditions.append(func.lower(func.json_extract(AlertSession.alert_data, '$.message')).like(search_term))
                search_conditions.append(func.lower(func.json_extract(AlertSession.alert_data, '$.context')).like(search_term))
                search_conditions.append(func.lower(func.json_extract(AlertSession.alert_data, '$.namespace')).like(search_term))
                search_conditions.append(func.lower(func.json_extract(AlertSession.alert_data, '$.pod')).like(search_term))
                search_conditions.append(func.lower(func.json_extract(AlertSession.alert_data, '$.cluster')).like(search_term))
                search_conditions.append(func.lower(func.json_extract(AlertSession.alert_data, '$.severity')).like(search_term))
                search_conditions.append(func.lower(func.json_extract(AlertSession.alert_data, '$.environment')).like(search_term))
                search_conditions.append(func.lower(func.json_extract(AlertSession.alert_data, '$.runbook')).like(search_term))
                search_conditions.append(func.lower(func.json_extract(AlertSession.alert_data, '$.id')).like(search_term))
                search_conditions.append(func.lower(func.json_extract(AlertSession.session_metadata, '$')).like(search_term))
                
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
            
            # Execute query to get AlertSession objects
            alert_sessions = self.session.exec(statement).all()
            
            # Get interaction counts for sessions
            interaction_counts = {}
            if alert_sessions:
                session_ids = [s.session_id for s in alert_sessions]
                
                # Count LLM interactions for each session
                llm_count_query = select(
                    LLMInteraction.session_id,
                    func.count(LLMInteraction.interaction_id).label('count')
                ).where(LLMInteraction.session_id.in_(session_ids)).group_by(LLMInteraction.session_id)
                llm_results = self.session.exec(llm_count_query).all()
                llm_counts = {result.session_id: result.count for result in llm_results}
                
                # Count MCP communications for each session
                mcp_count_query = select(
                    MCPInteraction.session_id,
                    func.count(MCPInteraction.communication_id).label('count')
                ).where(MCPInteraction.session_id.in_(session_ids)).group_by(MCPInteraction.session_id)
                mcp_results = self.session.exec(mcp_count_query).all()
                mcp_counts = {result.session_id: result.count for result in mcp_results}
                
                # Combine counts for each session
                for session_id in session_ids:
                    interaction_counts[session_id] = {
                        'llm_interactions': llm_counts.get(session_id, 0),
                        'mcp_communications': mcp_counts.get(session_id, 0)
                    }
            
            session_overviews = []
            for alert_session in alert_sessions:
                session_counts = interaction_counts.get(alert_session.session_id, {})
                llm_count = session_counts.get('llm_interactions', 0)
                mcp_count = session_counts.get('mcp_communications', 0)
                
                overview = SessionOverview(
                    # Core identification
                    session_id=alert_session.session_id,
                    alert_id=alert_session.alert_id,
                    alert_type=alert_session.alert_type,
                    agent_type=alert_session.agent_type,
                    status=AlertSessionStatus(alert_session.status),
                    
                    # Timing info
                    started_at_us=alert_session.started_at_us,
                    completed_at_us=alert_session.completed_at_us,
                    
                    # Basic status info
                    error_message=alert_session.error_message,
                    
                    # Summary counts (merged from interaction_counts)
                    llm_interaction_count=llm_count,
                    mcp_communication_count=mcp_count,
                    total_interactions=llm_count + mcp_count,
                    
                    # Chain progress info
                    chain_id=alert_session.chain_id,
                    current_stage_index=alert_session.current_stage_index,
                    
                    # Optional fields that may need calculation elsewhere (defaults from SessionOverview)
                    total_stages=None,
                    completed_stages=None,
                    failed_stages=0
                )
                session_overviews.append(overview)
            
            # Calculate pagination info
            total_pages = (total_items + page_size - 1) // page_size
            
            # Build PaginationInfo model
            pagination_info = PaginationInfo(
                page=page,
                page_size=page_size,
                total_pages=total_pages,
                total_items=total_items
            )
            
            # Return type-safe PaginatedSessions model
            return PaginatedSessions(
                sessions=session_overviews,
                pagination=pagination_info,
                filters_applied={
                    'status': status,
                    'agent_type': agent_type,
                    'alert_type': alert_type,
                    'search': search,
                    'start_date_us': start_date_us,
                    'end_date_us': end_date_us
                }
            )
            
        except Exception as e:
            logger.error(f"Failed to get alert sessions: {str(e)}")
            # Return empty result on error
            return PaginatedSessions(
                sessions=[],
                pagination=PaginationInfo(page=page, page_size=page_size, total_pages=0, total_items=0),
                filters_applied={}
            )

    def get_session_details(self, session_id: str) -> Optional[DetailedSession]:
        """
        Get complete session details including chronological timeline, stages, and all interactions.
        """
        try:
            # Get the session
            session = self.get_alert_session(session_id)
            if not session:
                return None
            
            # Get all interactions and communications
            llm_interactions_db = self.get_llm_interactions_for_session(session_id)
            mcp_communications_db = self.get_mcp_communications_for_session(session_id)
            
            # Get stage executions
            stages_stmt = (
                select(StageExecution)
                .where(StageExecution.session_id == session_id)
                .order_by(StageExecution.stage_index)
            )
            stage_executions_db = self.session.exec(stages_stmt).all()
            
            # Group interactions by stage_execution_id
            interactions_by_stage = defaultdict(list)
            
            # Convert LLM interactions to type-safe models
            for llm_db in llm_interactions_db:
                # Convert request messages if available  
                messages = []
                if llm_db.request_json and isinstance(llm_db.request_json, dict):
                    for msg in llm_db.request_json.get('messages', []):
                        if isinstance(msg, dict) and 'role' in msg and 'content' in msg:
                            messages.append(LLMMessage(role=msg['role'], content=msg['content']))
                
                # Add assistant response from response_json if available
                if llm_db.response_json and isinstance(llm_db.response_json, dict):
                    choices = llm_db.response_json.get('choices', [])
                    if choices and len(choices) > 0:
                        first_choice = choices[0]
                        if isinstance(first_choice, dict) and 'message' in first_choice:
                            assistant_msg = first_choice['message']
                            if isinstance(assistant_msg, dict) and 'content' in assistant_msg:
                                messages.append(LLMMessage(role="assistant", content=assistant_msg['content']))
                
                # Extract token usage
                tokens_used = llm_db.token_usage or {}
                
                llm_details = LLMEventDetails(
                    messages=messages,
                    model_name=llm_db.model_name,
                    temperature=llm_db.request_json.get('temperature') if llm_db.request_json else None,
                    success=llm_db.success,
                    error_message=llm_db.error_message,
                    input_tokens=tokens_used.get('prompt_tokens'),
                    output_tokens=tokens_used.get('completion_tokens'),
                    total_tokens=tokens_used.get('total_tokens'),
                    tool_calls=llm_db.tool_calls,
                    tool_results=llm_db.tool_results
                )
                
                llm_interaction = LLMTimelineEvent(
                    id=llm_db.interaction_id,
                    event_id=llm_db.interaction_id,
                    timestamp_us=llm_db.timestamp_us,
                    step_description=llm_db.step_description,
                    duration_ms=llm_db.duration_ms,
                    stage_execution_id=llm_db.stage_execution_id or 'unknown',
                    details=llm_details
                )
                
                stage_id = llm_db.stage_execution_id or 'unknown'
                interactions_by_stage[stage_id].append(llm_interaction)
            
            # Convert MCP communications to type-safe models
            for mcp_db in mcp_communications_db:
                mcp_details = MCPEventDetails(
                    tool_name=mcp_db.tool_name or '',
                    server_name=mcp_db.server_name,
                    communication_type=mcp_db.communication_type,
                    parameters=mcp_db.tool_arguments or {},
                    result=mcp_db.tool_result or {},
                    available_tools=mcp_db.available_tools or {},
                    success=mcp_db.success
                )
                
                mcp_interaction = MCPTimelineEvent(
                    id=mcp_db.communication_id,
                    event_id=mcp_db.communication_id,
                    timestamp_us=mcp_db.timestamp_us,
                    step_description=mcp_db.step_description,
                    duration_ms=mcp_db.duration_ms,
                    stage_execution_id=mcp_db.stage_execution_id or 'unknown',
                    details=mcp_details
                )
                
                stage_id = mcp_db.stage_execution_id or 'unknown'
                interactions_by_stage[stage_id].append(mcp_interaction)
            
            # Build DetailedStage objects
            detailed_stages = []
            for stage_db in stage_executions_db:
                stage_interactions = interactions_by_stage.get(stage_db.execution_id, [])
                
                # Separate LLM and MCP interactions and sort chronologically
                llm_stage_interactions = sorted(
                    [i for i in stage_interactions if isinstance(i, LLMTimelineEvent)],
                    key=lambda x: x.timestamp_us
                )
                mcp_stage_interactions = sorted(
                    [i for i in stage_interactions if isinstance(i, MCPTimelineEvent)], 
                    key=lambda x: x.timestamp_us
                )
                
                detailed_stage = DetailedStage(
                    execution_id=stage_db.execution_id,
                    session_id=stage_db.session_id,
                    stage_id=stage_db.stage_id,
                    stage_index=stage_db.stage_index,
                    stage_name=stage_db.stage_name,
                    agent=stage_db.agent,
                    status=StageStatus(stage_db.status),
                    started_at_us=stage_db.started_at_us,
                    completed_at_us=stage_db.completed_at_us,
                    duration_ms=stage_db.duration_ms,
                    stage_output=stage_db.stage_output,
                    error_message=stage_db.error_message,
                    llm_interactions=llm_stage_interactions,
                    mcp_communications=mcp_stage_interactions,
                    llm_interaction_count=len(llm_stage_interactions),
                    mcp_communication_count=len(mcp_stage_interactions),
                    total_interactions=len(llm_stage_interactions) + len(mcp_stage_interactions)
                )
                detailed_stages.append(detailed_stage)
            
            # Calculate total interaction counts
            total_llm = len(llm_interactions_db)
            total_mcp = len(mcp_communications_db)
            
            # Create DetailedSession
            return DetailedSession(
                # Core session data
                session_id=session.session_id,
                alert_id=session.alert_id,
                alert_type=session.alert_type,
                agent_type=session.agent_type,
                status=AlertSessionStatus(session.status),
                started_at_us=session.started_at_us,
                completed_at_us=session.completed_at_us,
                error_message=session.error_message,
                
                # Full session details
                alert_data=session.alert_data,
                final_analysis=session.final_analysis,
                session_metadata=session.session_metadata,
                
                # Chain execution details
                chain_id=session.chain_id,
                chain_definition=session.chain_definition or {},
                current_stage_index=session.current_stage_index,
                current_stage_id=session.current_stage_id,
                
                # Interaction counts
                total_interactions=total_llm + total_mcp,
                llm_interaction_count=total_llm,
                mcp_communication_count=total_mcp,
                
                # Complete stage executions with interactions
                stages=detailed_stages
            )
            
        except Exception as e:
            logger.error(f"Failed to get detailed session {session_id}: {str(e)}")
            return None

    def get_filter_options(self) -> FilterOptions:
        """
        Get dynamic filter options based on actual data in the database.
        """
        try:
            # Get distinct agent types as a flat list of strings
            agent_types = self.session.scalars(
                select(AlertSession.agent_type)
                    .distinct()
                    .where(AlertSession.agent_type.is_not(None))
            ).all()
            
            # Get distinct alert types as a flat list of strings
            alert_types = self.session.scalars(
                select(AlertSession.alert_type)
                    .distinct()
                    .where(AlertSession.alert_type.is_not(None))
            ).all()
            
            # Always return all possible status options for consistent filtering
            status_options = AlertSessionStatus.values()
            
            # Create TimeRangeOption objects
            time_ranges = [
                TimeRangeOption(label="Last Hour", value="1h"),
                TimeRangeOption(label="Last 4 Hours", value="4h"),
                TimeRangeOption(label="Today", value="today"),
                TimeRangeOption(label="This Week", value="week"),
                TimeRangeOption(label="This Month", value="month")
            ]
            
            return FilterOptions(
                agent_types=sorted(list(agent_types)) if agent_types else [],
                alert_types=sorted(list(alert_types)) if alert_types else [],
                status_options=status_options,
                time_ranges=time_ranges
            )
            
        except Exception as e:
            logger.error(f"Failed to get filter options: {str(e)}")
            # Return empty options on error
            return FilterOptions(
                agent_types=[],
                alert_types=[],
                status_options=AlertSessionStatus.values(),
                time_ranges=[
                    TimeRangeOption(label="Last Hour", value="1h"),
                    TimeRangeOption(label="Last 4 Hours", value="4h"),
                    TimeRangeOption(label="Today", value="today"),
                    TimeRangeOption(label="This Week", value="week"),
                    TimeRangeOption(label="This Month", value="month")
                ]
            )

    def get_session_overview(self, session_id: str) -> Optional[SessionOverview]:
        """
        Get session overview with stage counts (lightweight version for summaries).
        """
        try:
            # Get the session
            session = self.get_alert_session(session_id)
            if not session:
                return None
            
            # Get stage executions for counting (without loading full interactions for performance)
            stages_stmt = (
                select(StageExecution)
                .where(StageExecution.session_id == session_id)
                .order_by(StageExecution.stage_index)
            )
            stage_executions_db = self.session.exec(stages_stmt).all()
            
            # Get interaction counts for all stages (needed for summary calculations)
            stage_execution_ids = [stage.execution_id for stage in stage_executions_db]
            stage_interaction_counts = self.get_stage_interaction_counts(stage_execution_ids)
            
            # Calculate total interaction counts and stage statistics
            total_llm = sum(counts.get('llm_interactions', 0) for counts in stage_interaction_counts.values())
            total_mcp = sum(counts.get('mcp_communications', 0) for counts in stage_interaction_counts.values())
            
            # Calculate stage statistics
            completed_stages = len([stage for stage in stage_executions_db if stage.status == StageStatus.COMPLETED.value])
            failed_stages = len([stage for stage in stage_executions_db if stage.status == StageStatus.FAILED.value])
            
            # Create SessionOverview (lighter weight model for summaries)
            return SessionOverview(
                # Core identification
                session_id=session.session_id,
                alert_id=session.alert_id,
                alert_type=session.alert_type,
                agent_type=session.agent_type,
                status=AlertSessionStatus(session.status),
                
                # Timing info
                started_at_us=session.started_at_us,
                completed_at_us=session.completed_at_us,
                
                # Basic status info
                error_message=session.error_message,
                
                # Summary counts (for dashboard display)
                llm_interaction_count=total_llm,
                mcp_communication_count=total_mcp,
                total_interactions=total_llm + total_mcp,
                
                # Chain progress info (for dashboard filtering/display)
                chain_id=session.chain_id,
                total_stages=len(stage_executions_db),
                completed_stages=completed_stages,
                failed_stages=failed_stages,
                current_stage_index=session.current_stage_index
            )
            
        except Exception as e:
            logger.error(f"Failed to build session with stages for session {session_id}: {str(e)}")
            return None