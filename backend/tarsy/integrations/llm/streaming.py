"""
Streaming utilities for LLM responses.

This module provides shared streaming functionality used by both LangChain-based
and native Google SDK clients for publishing LLM response chunks to WebSockets.
"""

from typing import TYPE_CHECKING, Optional

from tarsy.models.constants import StreamingEventType
from tarsy.models.parallel_metadata import ParallelExecutionMetadata
from tarsy.utils.logger import get_module_logger

if TYPE_CHECKING:
    from tarsy.config.settings import Settings

logger = get_module_logger(__name__)


class StreamingPublisher:
    """
    Handles publishing LLM streaming chunks to WebSocket via transient events.
    
    This utility centralizes the streaming logic used by both LLMClient (LangChain)
    and GeminiNativeThinkingClient (Google SDK) to avoid code duplication.
    
    Features:
    - Checks streaming config flag before publishing
    - Warns about SQLite limitations (requires PostgreSQL for real-time)
    - Logs warning only once per instance to avoid spam
    - Gracefully handles publishing failures without breaking LLM calls
    """
    
    def __init__(self, settings: Optional['Settings'] = None):
        """
        Initialize the streaming publisher.
        
        Args:
            settings: Application settings for checking streaming config.
                     If None, streaming will be disabled.
        """
        self.settings = settings
        self._sqlite_warning_logged = False
    
    async def publish_chunk(
        self,
        session_id: str,
        stage_execution_id: Optional[str],
        stream_type: StreamingEventType,
        chunk: str,
        is_complete: bool,
        mcp_event_id: Optional[str] = None,
        llm_interaction_id: Optional[str] = None,
        parallel_metadata: Optional['ParallelExecutionMetadata'] = None
    ) -> None:
        """
        Publish streaming chunk via transient channel for WebSocket delivery.
        
        Args:
            session_id: Session identifier for routing
            stage_execution_id: Stage execution identifier for tracking (child ID for parallel stages)
            stream_type: Type of streaming content (THOUGHT, FINAL_ANSWER, 
                        NATIVE_THINKING, SUMMARIZATION)
            chunk: Content chunk (accumulated tokens)
            is_complete: Whether this is the final chunk
            mcp_event_id: Optional MCP event ID (for summarizations)
            llm_interaction_id: LLM interaction ID for deduplication
            parallel_metadata: Parallel execution metadata for frontend filtering
        """
        # Check if streaming is enabled via config flag
        if self.settings and not self.settings.enable_llm_streaming:
            # Streaming disabled by config - return early without warning (expected behavior)
            return
        
        try:
            from tarsy.database.init_db import get_async_session_factory
            from tarsy.models.event_models import LLMStreamChunkEvent
            from tarsy.services.events.publisher import publish_transient_event
            from tarsy.utils.timestamp import now_us
            
            async_session_factory = get_async_session_factory()
            async with async_session_factory() as session:
                # Check database dialect to warn about SQLite limitations
                db_dialect = session.bind.dialect.name
                
                if db_dialect != "postgresql":
                    # Only log warning once per instance (on first chunk)
                    if not self._sqlite_warning_logged:
                        logger.warning(
                            f"LLM streaming requested but database is {db_dialect}. "
                            "Real-time streaming requires PostgreSQL with NOTIFY support. "
                            "Events will be published but may not be delivered in real time."
                        )
                        self._sqlite_warning_logged = True
                
                # Unpack parallel metadata for JSON serialization
                event = LLMStreamChunkEvent(
                    session_id=session_id,
                    stage_execution_id=stage_execution_id,
                    chunk=chunk,
                    stream_type=stream_type.value,
                    is_complete=is_complete,
                    mcp_event_id=mcp_event_id,
                    llm_interaction_id=llm_interaction_id,
                    # Unpack parallel execution metadata (event model uses individual fields for JSON serialization)
                    parent_stage_execution_id=parallel_metadata.parent_stage_execution_id if parallel_metadata else None,
                    parallel_index=parallel_metadata.parallel_index if parallel_metadata else None,
                    agent_name=parallel_metadata.agent_name if parallel_metadata else None,
                    timestamp_us=now_us()
                )
                
                await publish_transient_event(
                    session=session,
                    channel=f"session:{session_id}",
                    event=event
                )
                
                logger.debug(
                    f"Published streaming chunk ({stream_type.value}, "
                    f"complete={is_complete}, mcp_event={mcp_event_id}, "
                    f"llm_interaction={llm_interaction_id}) for {session_id}"
                )
                
        except Exception as e:
            # Don't fail LLM call if streaming fails
            logger.warning(f"Failed to publish streaming chunk: {e}")

