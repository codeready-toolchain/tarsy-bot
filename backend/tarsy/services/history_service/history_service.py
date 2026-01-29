"""History Service - Main Facade."""

from typing import Any, Dict, List, Optional, Tuple

from tarsy.models.agent_config import ChainConfigModel
from tarsy.models.db_models import AlertSession, Chat, ChatUserMessage, StageExecution
from tarsy.models.history_models import (
    DetailedSession,
    FilterOptions,
    LLMConversationHistory,
    PaginatedSessions,
    SessionStats,
)
from tarsy.models.processing_context import ChainContext
from tarsy.models.unified_interactions import LLMInteraction, MCPInteraction
from tarsy.services.history_service.base_infrastructure import BaseHistoryInfra
from tarsy.services.history_service.chat_operations import ChatOperations
from tarsy.services.history_service.conversation_operations import ConversationOperations
from tarsy.services.history_service.interaction_operations import InteractionOperations
from tarsy.services.history_service.maintenance_operations import MaintenanceOperations
from tarsy.services.history_service.query_operations import QueryOperations
from tarsy.services.history_service.queue_operations import QueueOperations
from tarsy.services.history_service.session_operations import SessionOperations
from tarsy.services.history_service.stage_operations import StageOperations
from tarsy.services.history_service.tracking_operations import TrackingOperations


class HistoryService:
    """Manages session data and audit trails via composed operations."""
    
    def __init__(self) -> None:
        self._infra = BaseHistoryInfra()
        self._sessions = SessionOperations(self._infra)
        self._stages = StageOperations(self._infra)
        self._interactions = InteractionOperations(self._infra)
        self._queries = QueryOperations(self._infra)
        self._maintenance = MaintenanceOperations(self._infra)
        self._chats = ChatOperations(self._infra)
        self._conversations = ConversationOperations(self._infra)
        self._tracking = TrackingOperations(self._infra)
        self._queue = QueueOperations(self._infra)
    
    # Infrastructure
    def initialize(self) -> bool:
        """Initialize database connection."""
        return self._infra.initialize()
    
    def get_repository(self):  # type: ignore[no-untyped-def]
        """Get repository context manager (delegates to _infra)."""
        return self._infra.get_repository()
    
    # Session lifecycle
    def create_session(self, chain_context: ChainContext, chain_definition: ChainConfigModel) -> bool:
        """Create a new alert processing session."""
        return self._sessions.create_session(chain_context, chain_definition)
    
    def update_session_status(
        self,
        session_id: str,
        status: str,
        error_message: Optional[str] = None,
        final_analysis: Optional[str] = None,
        final_analysis_summary: Optional[str] = None,
        executive_summary_error: Optional[str] = None,
        pause_metadata: Optional[dict] = None
    ) -> bool:
        """Update session processing status."""
        return self._sessions.update_session_status(
            session_id, status, error_message, final_analysis,
            final_analysis_summary, executive_summary_error, pause_metadata
        )
    
    def get_session(self, session_id: str) -> Optional[AlertSession]:
        """Get session by ID."""
        return self._sessions.get_session(session_id)
    
    def update_session_to_canceling(self, session_id: str) -> tuple[bool, str]:
        """Atomically update session to CANCELING if not already terminal."""
        return self._sessions.update_session_to_canceling(session_id)
    
    # Stage execution
    async def create_stage_execution(self, stage_execution: StageExecution) -> str:
        """Create a new stage execution record."""
        return await self._stages.create_stage_execution(stage_execution)
    
    async def update_stage_execution(self, stage_execution: StageExecution) -> bool:
        """Update an existing stage execution record."""
        return await self._stages.update_stage_execution(stage_execution)
    
    async def update_session_current_stage(self, session_id: str, current_stage_index: int, current_stage_id: str) -> bool:
        """Update the current stage information for a session."""
        return await self._stages.update_session_current_stage(session_id, current_stage_index, current_stage_id)

    async def get_session_summary(self, session_id: str) -> Optional[SessionStats]:
        """Get summary statistics for a session."""
        return await self._stages.get_session_summary(session_id)
    
    async def get_stage_execution(self, execution_id: str) -> Optional[StageExecution]:
        """Get a single stage execution by ID."""
        return await self._stages.get_stage_execution(execution_id)
    
    async def get_stage_executions(self, session_id: str) -> List[StageExecution]:
        """Get all stage executions for a session."""
        return await self._stages.get_stage_executions(session_id)
    
    async def get_parallel_stage_children(self, parent_execution_id: str) -> List[StageExecution]:
        """Get all child stage executions for a parallel stage parent."""
        return await self._stages.get_parallel_stage_children(parent_execution_id)
    
    async def get_paused_stages(self, session_id: str) -> List[StageExecution]:
        """Get all paused stage executions for a session."""
        return await self._stages.get_paused_stages(session_id)
    
    async def cancel_all_paused_stages(self, session_id: str) -> int:
        """Cancel all paused stages for a session."""
        return await self._stages.cancel_all_paused_stages(session_id)
    
    # Interaction logging
    def store_llm_interaction(self, interaction: LLMInteraction) -> bool:
        """Store an LLM interaction to the database."""
        return self._interactions.store_llm_interaction(interaction)
    
    def store_mcp_interaction(self, interaction: MCPInteraction) -> bool:
        """Store an MCP interaction to the database."""
        return self._interactions.store_mcp_interaction(interaction)
    
    # Query operations
    def get_sessions_list(
        self,
        filters: Optional[Dict[str, Any]] = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: Optional[str] = None,
        sort_order: Optional[str] = None
    ) -> Optional[PaginatedSessions]:
        """Retrieve alert sessions with filtering and pagination."""
        return self._queries.get_sessions_list(filters, page, page_size, sort_by, sort_order)

    def test_database_connection(self) -> bool:
        """Test database connectivity."""
        return self._queries.test_database_connection()

    def get_session_details(self, session_id: str) -> Optional[DetailedSession]:
        """Get complete session details including timeline and interactions."""
        return self._queries.get_session_details(session_id)
    
    def get_active_sessions(self) -> List[AlertSession]:
        """Get all currently active sessions."""
        return self._queries.get_active_sessions()

    def get_filter_options(self) -> FilterOptions:
        """Get available filter options for the dashboard."""
        return self._queries.get_filter_options()
    
    # Maintenance operations
    def cleanup_orphaned_sessions(self, timeout_minutes: int = 30) -> int:
        """Find and mark orphaned sessions as failed based on inactivity timeout."""
        return self._maintenance.cleanup_orphaned_sessions(timeout_minutes)
    
    async def mark_pod_sessions_interrupted(self, pod_id: str) -> int:
        """Mark sessions being processed by a pod as failed during graceful shutdown."""
        return await self._maintenance.mark_pod_sessions_interrupted(pod_id)
    
    async def start_session_processing(self, session_id: str, pod_id: str) -> bool:
        """Mark session as being processed by a specific pod."""
        return await self._maintenance.start_session_processing(session_id, pod_id)
    
    def record_session_interaction(self, session_id: str) -> bool:
        """Update session last_interaction_at timestamp."""
        return self._maintenance.record_session_interaction(session_id)
    
    # Chat operations
    async def create_chat(self, chat: Chat) -> Chat:
        """Create a new chat record."""
        return await self._chats.create_chat(chat)
    
    async def get_chat_by_id(self, chat_id: str) -> Optional[Chat]:
        """Get chat by ID."""
        return await self._chats.get_chat_by_id(chat_id)
    
    async def get_chat_by_session(self, session_id: str) -> Optional[Chat]:
        """Get chat for a session (if exists)."""
        return await self._chats.get_chat_by_session(session_id)
    
    async def create_chat_user_message(self, message: ChatUserMessage) -> ChatUserMessage:
        """Create a new chat user message."""
        return await self._chats.create_chat_user_message(message)
    
    async def get_stage_executions_for_chat(self, chat_id: str) -> List[StageExecution]:
        """Get all stage executions for a chat."""
        return await self._chats.get_stage_executions_for_chat(chat_id)
    
    async def has_llm_interactions(self, session_id: str) -> bool:
        """Check if session has any LLM interactions."""
        return await self._chats.has_llm_interactions(session_id)
    
    async def get_llm_interactions_for_session(self, session_id: str) -> List[LLMInteraction]:
        """Get all LLM interactions for a session."""
        return await self._chats.get_llm_interactions_for_session(session_id)
    
    async def get_llm_interactions_for_stage(self, stage_execution_id: str) -> List[LLMInteraction]:
        """Get all LLM interactions for a stage execution."""
        return await self._chats.get_llm_interactions_for_stage(stage_execution_id)
    
    async def get_chat_user_message_count(self, chat_id: str) -> int:
        """Get total user message count for a chat."""
        return await self._chats.get_chat_user_message_count(chat_id)
    
    async def get_chat_user_messages(self, chat_id: str, limit: int = 50, offset: int = 0) -> List[ChatUserMessage]:
        """Get user messages for a chat with pagination."""
        return await self._chats.get_chat_user_messages(chat_id, limit, offset)
    
    # Conversation operations
    def get_session_conversation_history(
        self,
        session_id: str,
        include_chat: bool = False
    ) -> Tuple[Optional[LLMConversationHistory], Optional[LLMConversationHistory]]:
        """Get LLM conversation history for a session and optionally its chat."""
        return self._conversations.get_session_conversation_history(session_id, include_chat)
    
    def get_formatted_session_conversation(
        self,
        session_id: str,
        exclude_chat_stages: bool = True,
        include_thinking: bool = False
    ) -> str:
        """Get formatted conversation text for any session."""
        return self._conversations.get_formatted_session_conversation(
            session_id, exclude_chat_stages, include_thinking
        )
    
    def build_comprehensive_session_history(
        self,
        session_id: str,
        include_separate_alert_section: bool = True,
        include_thinking: bool = False
    ) -> str:
        """Build comprehensive session history for external analysis."""
        return self._conversations.build_comprehensive_session_history(
            session_id, include_separate_alert_section, include_thinking
        )
    
    # Tracking operations
    async def start_chat_message_processing(self, chat_id: str, pod_id: str) -> bool:
        """Mark chat as processing a message on a specific pod."""
        return await self._tracking.start_chat_message_processing(chat_id, pod_id)
    
    def record_chat_interaction(self, chat_id: str) -> bool:
        """Update chat last_interaction_at timestamp."""
        return self._tracking.record_chat_interaction(chat_id)
    
    def cleanup_orphaned_chats(self, timeout_minutes: int = 30) -> int:
        """Find and clear stale processing markers from orphaned chats."""
        return self._tracking.cleanup_orphaned_chats(timeout_minutes)
    
    async def mark_pod_chats_interrupted(self, pod_id: str) -> int:
        """Clear processing markers for chats on a shutting-down pod."""
        return await self._tracking.mark_pod_chats_interrupted(pod_id)
    
    # Queue management
    def count_sessions_by_status(self, status: str) -> int:
        """Count sessions with given status across all pods."""
        return self._queue.count_sessions_by_status(status)
    
    def count_pending_sessions(self) -> int:
        """Count sessions in PENDING state."""
        return self._queue.count_pending_sessions()
    
    def claim_next_pending_session(self, pod_id: str) -> Optional[AlertSession]:
        """Atomically claim next PENDING session for this pod."""
        return self._queue.claim_next_pending_session(pod_id)
