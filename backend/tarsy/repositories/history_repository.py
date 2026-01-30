"""
Repository for Alert Processing History database operations.

Provides database access layer for alert processing history with SQLModel,
supporting comprehensive audit trails, chronological timeline reconstruction,
and advanced querying capabilities using Unix timestamps for optimal performance.
"""

from collections import defaultdict
from typing import Dict, List, Optional, Union

from sqlmodel import Session, and_, asc, case, desc, func, or_, select

from tarsy.models.constants import AlertSessionStatus, ParallelType, StageStatus
from tarsy.models.db_models import AlertSession, Chat, ChatUserMessage, StageExecution
from tarsy.models.history_models import (
    ChatUserMessageData,
    DetailedSession,
    DetailedStage,
    FilterOptions,
    LLMTimelineEvent,
    MCPEventDetails,
    MCPTimelineEvent,
    PaginatedSessions,
    PaginationInfo,
    SessionOverview,
    TimeRangeOption,
)
from tarsy.models.unified_interactions import LLMInteraction, MCPInteraction
from tarsy.repositories.base_repository import BaseRepository
from tarsy.utils.logger import get_logger
from tarsy.utils.timestamp import now_us

logger = get_logger(__name__)

# Constant for session-level interactions (not associated with any specific stage)
SESSION_LEVEL_STAGE_ID = 'unknown'


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
            
        Note:
            With UUID4-based session_ids, duplicate constraint violations should never occur.
        """
        try:
            # Check for existing session (defensive programming - should never match with UUID4)
            existing_session = self.session.exec(
                select(AlertSession).where(AlertSession.session_id == alert_session.session_id)
            ).first()
            
            if existing_session:
                logger.warning(
                    f"Alert session already exists for session_id {alert_session.session_id}. "
                    f"This should not happen with UUID4 - investigate potential bug."
                )
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
    
    def has_llm_interactions(self, session_id: str) -> bool:
        """
        Check if session has any LLM interactions (lightweight existence check).
        
        Uses LIMIT 1 for optimal performance - avoids loading full interaction history.
        
        Args:
            session_id: The session identifier
            
        Returns:
            True if session has at least one LLM interaction, False otherwise
        """
        try:
            statement = select(LLMInteraction).where(
                LLMInteraction.session_id == session_id
            ).limit(1)
            
            result = self.session.exec(statement).first()
            return result is not None
        except Exception as e:
            logger.error(f"Failed to check LLM interactions for session {session_id}: {str(e)}")
            raise
    
    def get_llm_interactions_for_session(
        self, 
        session_id: str,
        exclude_chat_stages: bool = False
    ) -> List[LLMInteraction]:
        """
        Get all LLM interactions for a session ordered by timestamp.
        
        Args:
            session_id: The session identifier
            exclude_chat_stages: If True, exclude interactions from chat stages
            
        Returns:
            List of LLMInteraction instances ordered by timestamp
        """
        try:
            statement = select(LLMInteraction).where(
                LLMInteraction.session_id == session_id
            )
            
            # Exclude chat stage interactions if requested
            if exclude_chat_stages:
                # Join with stage_executions to filter out chat stages
                statement = statement.outerjoin(
                    StageExecution,
                    LLMInteraction.stage_execution_id == StageExecution.execution_id
                ).where(
                    # Include interactions with no stage (shouldn't happen in practice)
                    # or interactions from stages without a chat_id
                    (LLMInteraction.stage_execution_id.is_(None)) | 
                    (StageExecution.chat_id.is_(None))
                )
            
            statement = statement.order_by(asc(LLMInteraction.timestamp_us))
            
            return self.session.exec(statement).all()
        except Exception as e:
            logger.error(
                f"Failed to get LLM interactions for session {session_id}: {str(e)}"
            )
            raise
    
    def get_llm_interactions_for_stage(self, stage_execution_id: str) -> List[LLMInteraction]:
        """
        Get all LLM interactions for a stage execution ordered by timestamp.
        
        Args:
            stage_execution_id: The stage execution identifier
            
        Returns:
            List of LLMInteraction instances ordered by timestamp
        """
        try:
            statement = select(LLMInteraction).where(
                LLMInteraction.stage_execution_id == stage_execution_id
            ).order_by(asc(LLMInteraction.timestamp_us))
            
            return self.session.exec(statement).all()
        except Exception as e:
            logger.error(f"Failed to get LLM interactions for stage {stage_execution_id}: {str(e)}")
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
    
    def get_stage_executions_for_session(self, session_id: str) -> List['StageExecution']:
        """Get all stage executions for a session with parent-child relationships.
        
        Returns parent stages with child executions embedded for parallel stages.
        
        Ordering:
        1. Regular stages (chat_id IS NULL) first, sorted by stage_index
        2. Chat stages (chat_id IS NOT NULL) last, sorted by started_at_us
        
        For parallel stages, children are grouped under their parent with parallel_executions attribute.
        """
        try:
            # Get all stages (both parents and children)
            stmt = (
                select(StageExecution)
                .where(StageExecution.session_id == session_id)
                .order_by(
                    # Chat stages (has chat_id) sort to the end
                    case((StageExecution.chat_id.isnot(None), 1), else_=0),
                    # Then by stage_index (for regular stages)
                    asc(StageExecution.stage_index),
                    # Then by parallel_index (for parallel children)
                    asc(StageExecution.parallel_index),
                    # Then by timestamp (for chat stages with same stage_index)
                    asc(StageExecution.started_at_us)
                )
            )
            all_stages = self.session.exec(stmt).all()
            
            # Group children under parents
            result = []
            
            for stage in all_stages:
                if stage.parent_stage_execution_id is None:
                    # Top-level stage (parent or single)
                    # Attach children if parallel type
                    if stage.parallel_type in ParallelType.parallel_values():
                        # Find and attach children
                        children = [
                            s for s in all_stages 
                            if s.parent_stage_execution_id == stage.execution_id
                        ]
                        # Add parallel_executions as a dynamic attribute (bypass Pydantic validation)
                        object.__setattr__(stage, 'parallel_executions', children)
                    result.append(stage)
            
            return result
        except Exception as e:
            logger.error(f"Failed to get stage executions for session {session_id}: {str(e)}")
            raise
    
    def get_parallel_stage_children(self, parent_execution_id: str) -> List[StageExecution]:
        """Get all child executions for a parallel stage parent.
        
        Args:
            parent_execution_id: Parent stage execution ID
            
        Returns:
            List of child StageExecution instances ordered by parallel_index
        """
        try:
            stmt = (
                select(StageExecution)
                .where(StageExecution.parent_stage_execution_id == parent_execution_id)
                .order_by(asc(StageExecution.parallel_index))
            )
            return list(self.session.exec(stmt).all())
        except Exception as e:
            logger.error(f"Failed to get parallel stage children for parent {parent_execution_id}: {str(e)}")
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
        page_size: int = 20,
        sort_by: Optional[str] = None,
        sort_order: Optional[str] = None
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
            
            # Apply sorting
            # Map frontend field names to database columns
            # Note: Only including actual database columns, not computed fields
            sort_field_map = {
                'started_at_us': AlertSession.started_at_us,
                'status': AlertSession.status,
                'alert_type': AlertSession.alert_type,
                'agent_type': AlertSession.agent_type,
                'author': AlertSession.author,
                'completed_at_us': AlertSession.completed_at_us,
            }
            
            # Default sorting: started_at_us descending (most recent first)
            sort_column = AlertSession.started_at_us
            sort_direction = 'desc'
            
            # Apply custom sorting if provided and valid
            if sort_by and sort_by in sort_field_map:
                sort_column = sort_field_map[sort_by]
                if sort_order and sort_order.lower() in ('asc', 'desc'):
                    sort_direction = sort_order.lower()
            elif sort_by == 'duration_ms':
                # Special handling for duration - compute as SQL expression
                # duration_ms = (completed_at_us - started_at_us) / 1000
                # For in-progress sessions (completed_at_us=NULL), use current runtime.
                # Note: In practice, the UI filters these out (shown in separate active panel),
                # but API consumers might query mixed statuses.
                current_time_us = now_us()
                duration_expr = case(
                    (AlertSession.completed_at_us.is_not(None), 
                     (AlertSession.completed_at_us - AlertSession.started_at_us) / 1000),
                    else_=((current_time_us - AlertSession.started_at_us) / 1000)
                )
                sort_column = duration_expr
                if sort_order and sort_order.lower() in ('asc', 'desc'):
                    sort_direction = sort_order.lower()
            # Note: session_total_tokens sorting not implemented as it requires complex aggregation
            # Frontend should disable sorting for this column
            
            # Apply the sorting direction
            if sort_direction == 'asc':
                statement = statement.order_by(asc(sort_column))
            else:
                statement = statement.order_by(desc(sort_column))
            
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
                
                # Calculate token usage aggregations for each session (EP-0009)
                token_query = select(
                    LLMInteraction.session_id,
                    func.sum(LLMInteraction.input_tokens).label('input_tokens'),
                    func.sum(LLMInteraction.output_tokens).label('output_tokens'),
                    func.sum(LLMInteraction.total_tokens).label('total_tokens')
                ).where(LLMInteraction.session_id.in_(session_ids)).group_by(LLMInteraction.session_id)
                token_results = self.session.exec(token_query).all()
                token_sums = {
                    result.session_id: {
                        'input_tokens': result.input_tokens,
                        'output_tokens': result.output_tokens, 
                        'total_tokens': result.total_tokens
                    } for result in token_results
                }
                
                # Count chat user messages for sessions with chats
                chat_message_counts = {}
                try:
                    from tarsy.models.db_models import Chat, ChatUserMessage
                    
                    # First get chat IDs for these sessions
                    chat_query = select(Chat.session_id, Chat.chat_id).where(
                        Chat.session_id.in_(session_ids)
                    )
                    chat_results = self.session.exec(chat_query).all()
                    chat_ids_by_session = {result.session_id: result.chat_id for result in chat_results}
                    
                    if chat_ids_by_session:
                        # Count messages for each chat
                        message_count_query = select(
                            ChatUserMessage.chat_id,
                            func.count(ChatUserMessage.message_id).label('count')
                        ).where(
                            ChatUserMessage.chat_id.in_(list(chat_ids_by_session.values()))
                        ).group_by(ChatUserMessage.chat_id)
                        message_results = self.session.exec(message_count_query).all()
                        message_counts_by_chat = {result.chat_id: result.count for result in message_results}
                        
                        # Map back to session IDs
                        for session_id, chat_id in chat_ids_by_session.items():
                            count = message_counts_by_chat.get(chat_id, 0)
                            if count > 0:
                                chat_message_counts[session_id] = count
                except Exception as e:
                    # Don't fail entire query if chat counting fails
                    logger.error(f"Failed to count chat messages for sessions: {e}")
                
                # Check for parallel stages in sessions
                parallel_stages_flags = {}
                try:
                    # Query for sessions that have at least one stage with parallel executions
                    # A stage has parallel executions if it has children (parent_stage_execution_id points to it)
                    # OR if its parallel_type is not 'single'
                    parallel_stages_query = select(StageExecution.session_id).where(
                        and_(
                            StageExecution.session_id.in_(session_ids),
                            or_(
                                StageExecution.parallel_type != ParallelType.SINGLE.value,
                                StageExecution.parent_stage_execution_id.is_not(None)
                            )
                        )
                    ).distinct()
                    parallel_results = self.session.exec(parallel_stages_query).all()
                    parallel_stages_flags = {session_id: True for session_id in parallel_results}
                except Exception as e:
                    # Don't fail entire query if parallel stages check fails
                    logger.error(f"Failed to check for parallel stages: {e}")
                
                # Combine counts for each session
                for session_id in session_ids:
                    tokens = token_sums.get(session_id, {})
                    interaction_counts[session_id] = {
                        'llm_interactions': llm_counts.get(session_id, 0),
                        'mcp_communications': mcp_counts.get(session_id, 0),
                        'input_tokens': tokens.get('input_tokens'),
                        'output_tokens': tokens.get('output_tokens'),
                        'total_tokens': tokens.get('total_tokens'),
                        'chat_message_count': chat_message_counts.get(session_id),
                        'has_parallel_stages': parallel_stages_flags.get(session_id, False)
                    }
            
            session_overviews = []
            for alert_session in alert_sessions:
                session_counts = interaction_counts.get(alert_session.session_id, {})
                llm_count = session_counts.get('llm_interactions', 0)
                mcp_count = session_counts.get('mcp_communications', 0)
                
                overview = SessionOverview(
                    # Core identification
                    session_id=alert_session.session_id,
                    alert_type=alert_session.alert_type,
                    agent_type=alert_session.agent_type,
                    status=AlertSessionStatus(alert_session.status),
                    author=alert_session.author,
                    
                    # Timing info
                    started_at_us=alert_session.started_at_us,
                    completed_at_us=alert_session.completed_at_us,
                    
                    # Basic status info
                    error_message=alert_session.error_message,
                    pause_metadata=alert_session.pause_metadata,
                    
                    # Summary counts (merged from interaction_counts)
                    llm_interaction_count=llm_count,
                    mcp_communication_count=mcp_count,
                    total_interactions=llm_count + mcp_count,
                    
                    # Token usage aggregations (EP-0009)
                    session_input_tokens=session_counts.get('input_tokens'),
                    session_output_tokens=session_counts.get('output_tokens'),
                    session_total_tokens=session_counts.get('total_tokens'),
                    
                    # Chain progress info
                    chain_id=alert_session.chain_id,
                    current_stage_index=alert_session.current_stage_index,
                    has_parallel_stages=session_counts.get('has_parallel_stages', False),
                    
                    # MCP configuration override
                    mcp_selection=alert_session.mcp_selection,
                    
                    # Slack integration
                    slack_message_fingerprint=alert_session.slack_message_fingerprint,
                    
                    chat_message_count=session_counts.get('chat_message_count'),
                    
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
            # Force fresh read from database to avoid stale cache issues
            # This is critical for SQLite WAL mode where recent writes might not be visible
            # in the current session snapshot until objects are expired
            if self.session.bind.dialect.name == 'sqlite':
                self.session.expire_all()
            
            # Get the session
            session = self.get_alert_session(session_id)
            if not session:
                return None
            
            # Get all interactions and communications
            llm_interactions_db = self.get_llm_interactions_for_session(session_id)
            mcp_communications_db = self.get_mcp_communications_for_session(session_id)
            
            # Get stage executions
            stage_executions_db = self.get_stage_executions_for_session(session_id)
            
            # Collect all chat user message IDs from stages
            message_ids = [
                stage.chat_user_message_id 
                for stage in stage_executions_db 
                if stage.chat_user_message_id
            ]
            
            # Fetch all user messages in bulk if there are any
            user_messages_map: Dict[str, ChatUserMessage] = {}
            if message_ids:
                messages_stmt = select(ChatUserMessage).where(
                    ChatUserMessage.message_id.in_(message_ids)
                )
                user_messages = self.session.exec(messages_stmt).all()
                user_messages_map = {msg.message_id: msg for msg in user_messages}
            
            # Group interactions by stage_execution_id
            interactions_by_stage = defaultdict(list)
            
            # Convert LLM DB interaction models to timeline events using LLMInteraction directly
            for llm_db in llm_interactions_db:
                llm_event = LLMTimelineEvent(
                    id=llm_db.interaction_id,
                    event_id=llm_db.interaction_id,
                    timestamp_us=llm_db.timestamp_us,
                    duration_ms=llm_db.duration_ms,
                    stage_execution_id=llm_db.stage_execution_id or SESSION_LEVEL_STAGE_ID,
                    step_description=f"LLM analysis using {llm_db.model_name}",
                    details=llm_db
                )
                
                stage_id = llm_db.stage_execution_id or SESSION_LEVEL_STAGE_ID
                interactions_by_stage[stage_id].append(llm_event)
            
            # Convert MCP communications to type-safe models
            for mcp_db in mcp_communications_db:
                mcp_details = MCPEventDetails(
                    tool_name=mcp_db.tool_name or '',
                    server_name=mcp_db.server_name,
                    communication_type=mcp_db.communication_type,
                    tool_arguments=mcp_db.tool_arguments or {},
                    tool_result=mcp_db.tool_result or {},
                    available_tools=mcp_db.available_tools or {},
                    success=mcp_db.success,
                    error_message=mcp_db.error_message,
                    duration_ms=mcp_db.duration_ms
                )
                
                mcp_interaction = MCPTimelineEvent(
                    id=mcp_db.communication_id,
                    event_id=mcp_db.communication_id,
                    timestamp_us=mcp_db.timestamp_us,
                    step_description=mcp_db.step_description,
                    duration_ms=mcp_db.duration_ms,
                    stage_execution_id=mcp_db.stage_execution_id or SESSION_LEVEL_STAGE_ID,
                    details=mcp_details
                )
                
                stage_id = mcp_db.stage_execution_id or SESSION_LEVEL_STAGE_ID
                interactions_by_stage[stage_id].append(mcp_interaction)
            
            # Helper function to convert StageExecution to DetailedStage
            def convert_stage_to_detailed(stage_db: StageExecution) -> DetailedStage:
                """Convert a StageExecution DB model to DetailedStage API model."""
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
                
                # Get user message data if this stage has a chat message
                chat_user_message_data = None
                if stage_db.chat_user_message_id and stage_db.chat_user_message_id in user_messages_map:
                    user_msg = user_messages_map[stage_db.chat_user_message_id]
                    chat_user_message_data = ChatUserMessageData(
                        message_id=user_msg.message_id,
                        content=user_msg.content,
                        author=user_msg.author,
                        created_at_us=user_msg.created_at_us
                    )
                
                # Convert nested children if they exist
                parallel_executions_detailed = None
                if hasattr(stage_db, 'parallel_executions') and stage_db.parallel_executions:
                    parallel_executions_detailed = [
                        convert_stage_to_detailed(child) for child in stage_db.parallel_executions
                    ]
                
                return DetailedStage(
                    execution_id=stage_db.execution_id,
                    session_id=stage_db.session_id,
                    stage_id=stage_db.stage_id,
                    stage_index=stage_db.stage_index,
                    stage_name=stage_db.stage_name,
                    agent=stage_db.agent,
                    iteration_strategy=stage_db.iteration_strategy,
                    status=StageStatus(stage_db.status),
                    started_at_us=stage_db.started_at_us,
                    completed_at_us=stage_db.completed_at_us,
                    duration_ms=stage_db.duration_ms,
                    stage_output=stage_db.stage_output,
                    error_message=stage_db.error_message,
                    chat_id=stage_db.chat_id,
                    chat_user_message_id=stage_db.chat_user_message_id,
                    chat_user_message=chat_user_message_data,
                    parent_stage_execution_id=stage_db.parent_stage_execution_id,
                    parallel_index=stage_db.parallel_index,
                    parallel_type=stage_db.parallel_type,
                    parallel_executions=parallel_executions_detailed,  # Nested children already converted
                    llm_interactions=llm_stage_interactions,
                    mcp_communications=mcp_stage_interactions,
                    llm_interaction_count=len(llm_stage_interactions),
                    mcp_communication_count=len(mcp_stage_interactions),
                    total_interactions=len(llm_stage_interactions) + len(mcp_stage_interactions)
                )
            
            # Build DetailedStage objects (stage_executions_db already has children nested)
            detailed_stages = [convert_stage_to_detailed(stage_db) for stage_db in stage_executions_db]
            
            # Extract session-level interactions (not associated with any stage)
            session_level_interactions = interactions_by_stage.get(SESSION_LEVEL_STAGE_ID, [])
            # Sort chronologically by timestamp
            session_level_interactions = sorted(session_level_interactions, key=lambda x: x.timestamp_us)
            
            # Calculate total interaction counts
            total_llm = len(llm_interactions_db)
            total_mcp = len(mcp_communications_db)
            
            # Calculate session-level token aggregations from stages
            session_input_tokens = 0
            session_output_tokens = 0
            session_total_tokens = 0
            
            for stage in detailed_stages:
                if stage.stage_input_tokens:
                    session_input_tokens += stage.stage_input_tokens
                if stage.stage_output_tokens: 
                    session_output_tokens += stage.stage_output_tokens
                if stage.stage_total_tokens:
                    session_total_tokens += stage.stage_total_tokens
            
            # Add session-level interaction tokens (e.g., executive summary)
            for interaction in session_level_interactions:
                if interaction.type == "llm" and interaction.details:
                    if interaction.details.input_tokens:
                        session_input_tokens += interaction.details.input_tokens
                    if interaction.details.output_tokens:
                        session_output_tokens += interaction.details.output_tokens
                    if interaction.details.total_tokens:
                        session_total_tokens += interaction.details.total_tokens
            
            # Use None instead of 0 for cleaner display
            session_input_tokens = session_input_tokens if session_input_tokens > 0 else None
            session_output_tokens = session_output_tokens if session_output_tokens > 0 else None  
            session_total_tokens = session_total_tokens if session_total_tokens > 0 else None
            
            # Create DetailedSession
            return DetailedSession(
                # Core session data
                session_id=session.session_id,
                alert_type=session.alert_type,
                agent_type=session.agent_type,
                status=AlertSessionStatus(session.status),
                author=session.author,
                runbook_url=session.runbook_url,
                mcp_selection=session.mcp_selection,
                started_at_us=session.started_at_us,
                completed_at_us=session.completed_at_us,
                error_message=session.error_message,
                
                # Full session details
                alert_data=session.alert_data,
                final_analysis=session.final_analysis,
                final_analysis_summary=session.final_analysis_summary,
                executive_summary_error=session.executive_summary_error,
                session_metadata=session.session_metadata,
                pause_metadata=session.pause_metadata,
                
                # Chain execution details
                chain_id=session.chain_id,
                chain_definition=session.chain_definition or {},
                current_stage_index=session.current_stage_index,
                current_stage_id=session.current_stage_id,
                
                # Slack integration
                slack_message_fingerprint=session.slack_message_fingerprint,
                
                # Interaction counts
                total_interactions=total_llm + total_mcp,
                llm_interaction_count=total_llm,
                mcp_communication_count=total_mcp,
                
                # Token usage aggregations
                session_input_tokens=session_input_tokens,
                session_output_tokens=session_output_tokens,
                session_total_tokens=session_total_tokens,
                
                # Complete stage executions with interactions
                stages=detailed_stages,
                
                # Session-level interactions (not associated with any specific stage)
                session_level_interactions=session_level_interactions
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
            stage_executions_db = self.get_stage_executions_for_session(session_id)
            
            # Get interaction counts for all stages (needed for summary calculations)
            stage_execution_ids = [stage.execution_id for stage in stage_executions_db]
            stage_interaction_counts = self.get_stage_interaction_counts(stage_execution_ids)
            
            # Calculate total interaction counts and stage statistics
            total_llm = sum(counts.get('llm_interactions', 0) for counts in stage_interaction_counts.values())
            total_mcp = sum(counts.get('mcp_communications', 0) for counts in stage_interaction_counts.values())
            
            # Calculate token usage aggregations for this session (EP-0009)
            token_query = select(
                func.sum(LLMInteraction.input_tokens).label('input_tokens'),
                func.sum(LLMInteraction.output_tokens).label('output_tokens'),
                func.sum(LLMInteraction.total_tokens).label('total_tokens')
            ).where(LLMInteraction.session_id == session_id)
            token_result = self.session.exec(token_query).first()
            
            session_input_tokens = token_result.input_tokens if token_result else None
            session_output_tokens = token_result.output_tokens if token_result else None
            session_total_tokens = token_result.total_tokens if token_result else None
            
            # Calculate stage statistics
            completed_stages = len([stage for stage in stage_executions_db if stage.status == StageStatus.COMPLETED.value])
            failed_stages = len([stage for stage in stage_executions_db if stage.status == StageStatus.FAILED.value])
            
            # Get chat message count if a chat exists
            chat_message_count = None
            try:
                from tarsy.models.db_models import Chat
                chat_stmt = select(Chat).where(Chat.session_id == session_id)
                chat = self.session.exec(chat_stmt).first()
                if chat:
                    chat_message_count = self.get_chat_user_message_count(chat.chat_id)
            except Exception as e:
                # Don't fail the query if chat counting fails
                logger.warning(f"Failed to get chat message count for session {session_id}: {e}")
            
            # Create SessionOverview (lighter weight model for summaries)
            return SessionOverview(
                # Core identification
                session_id=session.session_id,
                alert_type=session.alert_type,
                agent_type=session.agent_type,
                status=AlertSessionStatus(session.status),
                author=session.author,
                
                # Timing info
                started_at_us=session.started_at_us,
                completed_at_us=session.completed_at_us,
                
                # Basic status info
                error_message=session.error_message,
                pause_metadata=session.pause_metadata,
                
                # Summary counts (for dashboard display)
                llm_interaction_count=total_llm,
                mcp_communication_count=total_mcp,
                total_interactions=total_llm + total_mcp,
                
                # Token usage aggregations
                session_input_tokens=session_input_tokens,
                session_output_tokens=session_output_tokens,
                session_total_tokens=session_total_tokens,
                
                # Chain progress info (for dashboard filtering/display)
                chain_id=session.chain_id,
                total_stages=len(stage_executions_db),
                completed_stages=completed_stages,
                failed_stages=failed_stages,
                current_stage_index=session.current_stage_index,
                
                # MCP configuration override
                mcp_selection=session.mcp_selection,
                
                # Slack integration
                slack_message_fingerprint=session.slack_message_fingerprint,
                
                chat_message_count=chat_message_count
            )
            
        except Exception as e:
            logger.error(f"Failed to build session with stages for session {session_id}: {str(e)}")
            return None
    
    # Pod tracking and orphan detection methods
    def find_orphaned_sessions(self, timeout_threshold_us: int) -> List[AlertSession]:
        """
        Find sessions that appear orphaned based on last interaction time.
        
        Only returns sessions that are:
        1. IN_PROGRESS status (not completed, failed, or pending)
        2. Have a non-NULL last_interaction_at timestamp
        3. Have last_interaction_at older than the timeout threshold
        
        Args:
            timeout_threshold_us: Timestamp threshold (microseconds) - sessions with
                                 last_interaction_at older than this are considered orphaned
        
        Returns:
            List of AlertSession records that appear orphaned
        """
        try:
            statement = select(AlertSession).where(
                AlertSession.status == AlertSessionStatus.IN_PROGRESS.value,
                AlertSession.last_interaction_at.isnot(None),  # Explicit NULL check
                AlertSession.last_interaction_at < timeout_threshold_us
            )
            return self.session.exec(statement).all()
        except Exception as e:
            logger.error(f"Failed to find orphaned sessions: {str(e)}")
            raise
    
    def find_sessions_by_pod(
        self,
        pod_id: str,
        status: str = AlertSessionStatus.IN_PROGRESS.value
    ) -> List[AlertSession]:
        """
        Find sessions being processed by a specific pod.
        
        Args:
            pod_id: Kubernetes pod identifier
            status: Session status to filter by (default: IN_PROGRESS)
        
        Returns:
            List of AlertSession records for the specified pod
        """
        try:
            statement = select(AlertSession).where(
                AlertSession.status == status,
                AlertSession.pod_id == pod_id
            )
            return self.session.exec(statement).all()
        except Exception as e:
            logger.error(f"Failed to find sessions for pod {pod_id}: {str(e)}")
            raise
    
    def update_session_pod_tracking(
        self,
        session_id: str,
        pod_id: str,
        status: str = AlertSessionStatus.IN_PROGRESS.value
    ) -> bool:
        """
        Update session with pod tracking information.
        
        Args:
            session_id: Session identifier
            pod_id: Pod identifier to assign
            status: Session status to set (default: IN_PROGRESS)
        
        Returns:
            True if update was successful, False otherwise
        """
        try:
            from tarsy.utils.timestamp import now_us
            
            session = self.get_alert_session(session_id)
            if not session:
                return False
            
            session.status = status
            session.pod_id = pod_id
            session.last_interaction_at = now_us()
            return self.update_alert_session(session)
        except Exception as e:
            logger.error(f"Failed to update pod tracking for session {session_id}: {str(e)}")
            return False
    
    # Queue Management Methods
    
    def count_sessions_by_status(self, status: str) -> int:
        """
        Count sessions with given status across all pods.
        
        Args:
            status: Session status to count (e.g., AlertSessionStatus.IN_PROGRESS.value)
            
        Returns:
            Count of sessions with the given status
        """
        try:
            statement = select(func.count(AlertSession.session_id)).where(
                AlertSession.status == status
            )
            result = self.session.exec(statement).first()
            return int(result) if result else 0
        except Exception as e:
            logger.error(f"Failed to count sessions by status {status}: {str(e)}")
            raise
    
    def count_pending_sessions(self) -> int:
        """
        Count sessions in PENDING state (for queue size check).
        
        Returns:
            Count of pending sessions
        """
        return self.count_sessions_by_status(AlertSessionStatus.PENDING.value)
    
    def claim_next_pending_session(self, pod_id: str) -> Optional[AlertSession]:
        """
        Atomically claim next PENDING session for this pod.
        
        Uses FOR UPDATE SKIP LOCKED on PostgreSQL for efficient lock-free claiming.
        Uses status transition on SQLite with retry logic (less efficient but acceptable for dev).
        
        Args:
            pod_id: Pod identifier claiming the session
            
        Returns:
            Claimed AlertSession if available, None otherwise
        """
        try:
            from tarsy.utils.timestamp import now_us
            
            # Detect database dialect
            dialect = self.session.bind.dialect.name
            
            if dialect == 'postgresql':
                # PostgreSQL: Use FOR UPDATE SKIP LOCKED for efficient claiming
                statement = (
                    select(AlertSession)
                    .where(AlertSession.status == AlertSessionStatus.PENDING.value)
                    .order_by(asc(AlertSession.started_at_us))
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
                
                session = self.session.exec(statement).first()
                if session:
                    # Update session with pod_id and IN_PROGRESS status
                    session.status = AlertSessionStatus.IN_PROGRESS.value
                    session.pod_id = pod_id
                    session.last_interaction_at = now_us()
                    self.session.add(session)
                    self.session.commit()
                    self.session.refresh(session)
                    logger.debug(f"Pod {pod_id} claimed session {session.session_id} (PostgreSQL)")
                    return session
                return None
                
            elif dialect == 'sqlite':
                # SQLite: Status-based claiming with optimistic locking
                # Find oldest PENDING session
                statement = (
                    select(AlertSession)
                    .where(AlertSession.status == AlertSessionStatus.PENDING.value)
                    .order_by(asc(AlertSession.started_at_us))
                    .limit(1)
                )
                
                session = self.session.exec(statement).first()
                if not session:
                    return None
                
                # Try to claim by updating status
                # SQLite acquires a write lock on commit; concurrent claims may
                # fail with a database locked error, handled by the except block
                try:
                    session.status = AlertSessionStatus.IN_PROGRESS.value
                    session.pod_id = pod_id
                    session.last_interaction_at = now_us()
                    self.session.add(session)
                    self.session.commit()
                    self.session.refresh(session)
                    logger.debug(f"Pod {pod_id} claimed session {session.session_id} (SQLite)")
                    return session
                except Exception as e:
                    # Race condition: another pod claimed it first
                    self.session.rollback()
                    logger.debug(f"Pod {pod_id} failed to claim session {session.session_id}: {e}")
                    return None
            else:
                logger.error(f"Unsupported database dialect for queue: {dialect}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to claim next pending session: {str(e)}")
            self.session.rollback()
            raise
    
    def delete_sessions_older_than(self, cutoff_timestamp_us: int) -> int:
        """
        Delete alert sessions older than cutoff timestamp.
        
        Deletes sessions where started_at_us < cutoff_timestamp_us, regardless of status.
        Related records (stage_executions, llm_interactions, mcp_communications) are
        automatically deleted via CASCADE foreign key constraints.
        
        Args:
            cutoff_timestamp_us: Cutoff timestamp (microseconds since epoch).
                                Sessions started before this are deleted.
        
        Returns:
            Number of sessions deleted
        """
        try:
            # Find sessions to delete
            statement = select(AlertSession).where(
                AlertSession.started_at_us < cutoff_timestamp_us
            )
            sessions_to_delete = self.session.exec(statement).all()
            
            if not sessions_to_delete:
                return 0
            
            # Delete sessions (CASCADE will handle related records)
            for session in sessions_to_delete:
                self.session.delete(session)
            
            self.session.commit()
            
            deleted_count = len(sessions_to_delete)
            logger.info(f"Deleted {deleted_count} alert session(s) older than timestamp {cutoff_timestamp_us}")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Failed to delete old sessions: {str(e)}")
            self.session.rollback()
            raise
    
    # ===== CHAT OPERATIONS =====
    
    def create_chat(self, chat: Chat) -> Optional[Chat]:
        """Create new chat record."""
        try:
            existing = self.session.exec(
                select(Chat).where(Chat.session_id == chat.session_id)
            ).first()
            if existing:
                logger.warning(f"Chat already exists for session {chat.session_id}")
                return existing
            self.session.add(chat)
            self.session.commit()
            self.session.refresh(chat)
            return chat
        except Exception as e:
            logger.error(f"Failed to create chat: {str(e)}")
            self.session.rollback()
            return None
    
    def get_chat_by_id(self, chat_id: str) -> Optional[Chat]:
        """Get chat by ID."""
        return self.session.exec(
            select(Chat).where(Chat.chat_id == chat_id)
        ).first()
    
    def get_chat_by_session(self, session_id: str) -> Optional[Chat]:
        """Get chat for a session (if exists)."""
        return self.session.exec(
            select(Chat).where(Chat.session_id == session_id)
        ).first()
    
    def update_chat(self, chat: Chat) -> bool:
        """Update existing chat record."""
        try:
            self.session.add(chat)
            self.session.commit()
            self.session.refresh(chat)
            return True
        except Exception as e:
            logger.error(f"Failed to update chat {chat.chat_id}: {str(e)}")
            self.session.rollback()
            return False
    
    def create_chat_user_message(self, message: ChatUserMessage) -> Optional[ChatUserMessage]:
        """Create new chat user message."""
        try:
            self.session.add(message)
            self.session.commit()
            self.session.refresh(message)
            return message
        except Exception as e:
            logger.error(f"Failed to create chat message: {str(e)}")
            self.session.rollback()
            return None
    
    def get_stage_executions_for_chat(self, chat_id: str) -> List[StageExecution]:
        """Get all stage executions for a chat, ordered by timestamp."""
        statement = select(StageExecution).where(
            StageExecution.chat_id == chat_id
        ).order_by(asc(StageExecution.started_at_us))
        return self.session.exec(statement).all()
    
    def get_chat_user_message_count(self, chat_id: str) -> int:
        """Count user messages in a chat."""
        try:
            statement = select(func.count(ChatUserMessage.message_id)).where(
                ChatUserMessage.chat_id == chat_id
            )
            result = self.session.exec(statement).one()
            # When selecting a single scalar value like func.count(), .one() returns a tuple
            # Extract the first element and cast to int
            if isinstance(result, tuple):
                return int(result[0])
            # In some cases, the result is already a scalar
            return int(result)
        except Exception as e:
            logger.error(f"Failed to count messages for chat {chat_id}: {str(e)}")
            return 0
    
    def get_chat_user_messages(
        self,
        chat_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[ChatUserMessage]:
        """Get user messages for a chat with pagination."""
        try:
            statement = select(ChatUserMessage).where(
                ChatUserMessage.chat_id == chat_id
            ).order_by(
                asc(ChatUserMessage.created_at_us)
            ).offset(offset).limit(limit)
            
            return list(self.session.exec(statement).all())
        except Exception as e:
            logger.error(f"Failed to get messages for chat {chat_id}: {str(e)}")
            return []
    
    # Pod Tracking & Orphan Detection
    
    def update_chat_pod_tracking(self, chat_id: str, pod_id: str) -> bool:
        """Update chat with pod tracking information."""
        try:
            chat = self.get_chat_by_id(chat_id)
            if not chat:
                return False
            chat.pod_id = pod_id
            chat.last_interaction_at = now_us()
            return self.update_chat(chat)
        except Exception as e:
            logger.error(f"Failed to update chat pod tracking: {str(e)}")
            return False
    
    def find_chats_by_pod(self, pod_id: str) -> List[Chat]:
        """Find chats being processed by a specific pod."""
        statement = select(Chat).where(
            Chat.pod_id == pod_id,
            Chat.last_interaction_at.isnot(None)
        )
        return self.session.exec(statement).all()
    
    def find_orphaned_chats(self, timeout_threshold_us: int) -> List[Chat]:
        """Find chats with stale last_interaction_at (orphaned processing)."""
        try:
            statement = select(Chat).where(
                Chat.last_interaction_at.isnot(None),
                Chat.last_interaction_at < timeout_threshold_us
            )
            return self.session.exec(statement).all()
        except Exception as e:
            logger.error(f"Failed to find orphaned chats: {str(e)}")
            raise
    
    # ===== CONVERSATION HISTORY OPERATIONS =====
    
    def get_last_llm_interaction_with_conversation(
        self,
        session_id: str,
        prefer_final_analysis: bool = True,
        chat_id: Optional[str] = None
    ) -> Optional[LLMInteraction]:
        """
        Get the last LLM interaction with conversation data for a session or chat.
        
        Strategy:
        1. If prefer_final_analysis=True, try to get the last 'final_analysis' type interaction
        2. Fall back to the last LLM interaction by timestamp if no final_analysis found
        
        Args:
            session_id: Session identifier
            prefer_final_analysis: If True, prefer final_analysis type interactions
            chat_id: If provided, only get interactions from chat stages (for chat conversation)
            
        Returns:
            LLMInteraction with conversation data, or None if not found
        """
        from tarsy.models.constants import LLMInteractionType
        
        try:
            # Build base conditions
            base_conditions = [LLMInteraction.session_id == session_id]
            
            # If chat_id is provided, filter to only chat stage interactions
            if chat_id:
                # Get stage execution IDs for this chat
                chat_stage_ids = select(StageExecution.execution_id).where(
                    StageExecution.chat_id == chat_id
                )
                base_conditions.append(LLMInteraction.stage_execution_id.in_(chat_stage_ids))
            else:
                # For main session conversation, exclude chat stages
                # Get chat for this session (if exists)
                chat = self.get_chat_by_session(session_id)
                if chat:
                    # Exclude chat stage interactions
                    chat_stage_ids = select(StageExecution.execution_id).where(
                        StageExecution.chat_id == chat.chat_id
                    )
                    base_conditions.append(
                        LLMInteraction.stage_execution_id.notin_(chat_stage_ids)
                    )
            
            if prefer_final_analysis:
                # Try to get the last final_analysis type interaction first
                statement = select(LLMInteraction).where(
                    and_(
                        *base_conditions,
                        LLMInteraction.interaction_type == LLMInteractionType.FINAL_ANALYSIS.value,
                        LLMInteraction.conversation.isnot(None)
                    )
                ).order_by(desc(LLMInteraction.timestamp_us)).limit(1)
                
                result = self.session.exec(statement).first()
                if result:
                    return result
            
            # Fall back to the last LLM interaction by timestamp
            statement = select(LLMInteraction).where(
                and_(
                    *base_conditions,
                    LLMInteraction.conversation.isnot(None)
                )
            ).order_by(desc(LLMInteraction.timestamp_us)).limit(1)
            
            return self.session.exec(statement).first()
            
        except Exception as e:
            logger.error(f"Failed to get last LLM interaction for session {session_id}: {str(e)}")
            return None