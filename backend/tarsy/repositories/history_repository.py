"""
Repository for Alert Processing History database operations.

Provides database access layer for alert processing history with SQLModel,
supporting comprehensive audit trails, chronological timeline reconstruction,
and advanced querying capabilities using Unix timestamps for optimal performance.
"""

from typing import Any, Dict, List, Optional, Union

from sqlmodel import Session, asc, desc, func, select, and_, or_

from tarsy.models.constants import AlertSessionStatus
from tarsy.models.history import AlertSession, LLMInteraction, MCPCommunication
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
        self.mcp_communication_repo = BaseRepository(session, MCPCommunication)
        
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
                    MCPCommunication.session_id,
                    func.count(MCPCommunication.communication_id).label('count')
                ).where(
                    MCPCommunication.session_id.in_(session_ids)
                ).group_by(MCPCommunication.session_id)
                
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
    def create_mcp_communication(self, mcp_communication: MCPCommunication) -> MCPCommunication:
        """
        Create a new MCP communication record.
        
        Args:
            mcp_communication: MCPCommunication instance to create
            
        Returns:
            The created MCPCommunication with database-generated fields
        """
        return self.mcp_communication_repo.create(mcp_communication)
    
    def get_mcp_communications_for_session(self, session_id: str) -> List[MCPCommunication]:
        """
        Get all MCP communications for a session ordered by timestamp.
        
        Args:
            session_id: The session identifier
            
        Returns:
            List of MCPCommunication instances ordered by timestamp
        """
        try:
            statement = select(MCPCommunication).where(
                MCPCommunication.session_id == session_id
            ).order_by(asc(MCPCommunication.timestamp_us))
            
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
                    "details": {
                        "request_json": interaction.request_json,
                        "response_json": interaction.response_json,
                        "model_name": interaction.model_used,
                        "tokens_used": interaction.token_usage,
                        "temperature": interaction.request_json.get('temperature') if interaction.request_json else None
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
                    "details": {
                        "tool_name": communication.tool_name,
                        "server_name": communication.server_name,
                        "communication_type": communication.communication_type,
                        "parameters": communication.tool_arguments or {},
                        "result": communication.tool_result or {},
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
                    "total_interactions": len(llm_interactions) + len(mcp_communications)
                },
                "chronological_timeline": timeline_events,
                "llm_interactions": [
                    {
                        "interaction_id": interaction.interaction_id,
                        "timestamp_us": interaction.timestamp_us,
                        "step_description": interaction.step_description,
                        "model_used": interaction.model_used,
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
                AlertSession.status.in_(AlertSessionStatus.ACTIVE_STATUSES)
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
                "status_options": AlertSessionStatus.ALL_STATUSES,
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