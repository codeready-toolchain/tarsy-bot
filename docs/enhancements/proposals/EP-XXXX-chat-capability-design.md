# EP-XXXX: Follow-up Chat Capability for TARSy Sessions

**Status:** Proposed  
**Created:** 2025-11-06  
**Author:** Design Discussion  

---

## Overview

Add chat-like follow-up conversation capability to TARSy, allowing users to continue investigating after a session completes. Users can ask clarifying questions, request deeper analysis, or explore different aspects of the original alert - all while preserving full context and tool execution capabilities.

## Key Architectural Decisions

1. **Data Model:** Two new tables (`Chat` with typed context fields + pod tracking, `ChatUserMessage`) + chat tracking fields in existing `StageExecution` table
2. **Observability:** Reuse existing `LLMInteraction` and `MCPInteraction` tables - full audit trail with zero new interaction tracking code
3. **Agent:** Built-in `ChatAgent` with ReAct loop, dynamically receives MCP servers from chat context
4. **WebSocket:** Reuse existing `session:{session_id}` channel - no changes to streaming infrastructure
5. **StageExecution Pattern:** Each chat response creates a `StageExecution` (with `chat_id` + `chat_user_message_id`), enabling all existing tooling to work automatically
6. **Events:** Reuse existing stage execution events via hooks - no new chat-specific events needed!
7. **Service Patterns:** ChatService mirrors AlertService patterns (pod tracking, timeouts, MCP cleanup, lifecycle management) for consistency and reliability
8. **Pod Tracking & Graceful Shutdown:** Chat extends session-level mechanisms with `Chat.pod_id` and `Chat.last_interaction_at` for multi-replica support
9. **Orphan Detection:** Periodic cleanup clears stale processing markers from abandoned chat messages (mirrors session orphan detection)
10. **Configuration:** Simple `chat_enabled: true/false` per chain in `agents.yaml`
11. **Multi-User:** All users can participate, message attribution preserved

## Goals

1. **Extend Investigation Capabilities** - Enable follow-up questions that can trigger new tool executions and analysis loops
2. **Preserve Context** - Maintain complete session context including alert data, stage outputs, and tool results
3. **Multi-User Collaboration** - Support multiple SREs participating in the same chat conversation
4. **Minimal Disruption** - Keep original sessions immutable, add chat as an optional extension
5. **Per-Chain Configuration** - Allow enabling/disabling chat capability per agent chain

## Non-Goals (Phase 1)

- Chat history search/filtering
- Export chat transcripts
- Private vs. group chat modes
- Chat analytics and insights
- Scheduled/automated follow-ups

---

## Use Cases

### Primary Use Cases

1. **Clarification Questions**
   ```
   User: "Can you explain the memory spike in simpler terms?"
   Agent: [Explains using existing context, no tools needed]
   ```

2. **Extended Investigation**
   ```
   User: "Check the pod logs from 2 hours before the crash"
   Agent: [Uses kubectl to fetch historical logs, analyzes them]
   ```

3. **Lateral Investigation**
   ```
   User: "What about the database? Was it affected?"
   Agent: [Uses database MCP tools to investigate impact]
   ```

4. **Hypothesis Testing**
   ```
   User: "Could this be related to the deployment at 14:00?"
   Agent: [Checks deployment history, correlates timing]
   ```

5. **Team Collaboration**
   ```
   Alice: "I see the OOM issue. What about network connectivity?"
   Agent: [Investigates network]
   Bob: "Can you check if other pods in the namespace are affected?"
   Agent: [Checks namespace-wide pod status]
   ```

---

## Architecture Design

### High-Level Flow

```
┌─────────────────────────────────────────────────┐
│ 1. Alert Processing (Normal Flow)               │
│    Alert → Chain Execution → Session Complete   │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│ 2. User Starts Chat (Optional)                  │
│    Click "Start Follow-up Chat" button          │
│    → Create Chat entity linked to session       │
│    → Capture session context                    │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│ 3. Chat Loop (Repeatable)                       │
│    User Question → Chat Agent → ReAct Loop →    │
│    Tool Executions → Assistant Response         │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│ 4. Multi-User Participation                     │
│    Multiple users can send messages             │
│    All see unified conversation                 │
│    Message attribution preserved                │
└─────────────────────────────────────────────────┘
```

### Detailed Technical Flow

**When User Sends Chat Message:**

```
1. User sends message "Check the pod logs from 2 hours ago"
   ↓
2. Create ChatUserMessage record
   → chat_id, message_id, content, author, timestamp
   ↓
3. Build chat context
   → Get last LLM interaction (from session or previous chat)
   → Extract conversation history as formatted text
   → Combine with user question
   ↓
4. Create StageExecution for AI response
   → stage_id="chat-response", agent="ChatAgent"
   → chat_id=<chat_id>, chat_user_message_id=<message_id>
   ↓
5. Invoke ChatAgent with ChatReActController
   → Controller prepends conversation_history to user message
   → Has access to same MCP servers as original session
   ↓
6. ChatAgent processes (ReAct iterations)
   → Thinks, calls tools (kubectl, db, etc.)
   → Each LLM call creates LLMInteraction (linked to stage_execution_id)
   → Each tool call creates MCPInteraction (linked to stage_execution_id)
   → Streaming events flow via session:{session_id} channel
   ↓
7. Dashboard receives streaming events in real-time
   → Groups by stage_execution_id
   → Renders thoughts, tool calls, final answer
   ↓
8. Complete StageExecution
   → status="completed", duration calculated
   ↓
9. Full audit trail available
   → Query: SELECT * FROM llm_interactions WHERE stage_execution_id = <exec_id>
   → Query: SELECT * FROM mcp_interactions WHERE stage_execution_id = <exec_id>
```

**Key Insights:** 

1. **Text-based context from LLM interactions:** Instead of building complex JSON structures, we extract the complete conversation history from existing `LLMInteraction.conversation` fields and format as readable text. This is simpler, more robust, and preserves all original context including tools list.

2. **Cumulative context:** Each LLM interaction contains full conversation history passed to it. For subsequent chat messages, we just need the last interaction - it already has everything.

3. **StageExecution pattern:** By creating StageExecution for each chat response, ALL existing infrastructure works automatically:
   - ✅ LLM streaming via existing `_publish_stream_chunk`
   - ✅ Tool execution tracking via existing MCPInteraction
   - ✅ LLM conversation tracking via existing LLMInteraction
   - ✅ Token usage tracking via existing fields
   - ✅ Dashboard rendering via existing components
   - ✅ Audit trail via existing queries

### Data Model

#### New Database Tables

```python
class Chat(SQLModel, table=True):
    """Chat metadata and context snapshot from completed session."""
    
    __tablename__ = "chats"
    
    __table_args__ = (
        Index('ix_chats_session_id', 'session_id'),
        Index('ix_chats_created_at', 'created_at_us'),
        # Composite index for efficient chat orphan detection
        Index('ix_chats_pod_last_interaction', 'pod_id', 'last_interaction_at'),
    )
    
    # Identity
    chat_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        primary_key=True,
        description="Unique chat identifier"
    )
    
    # Linked session
    session_id: str = Field(
        sa_column=Column(String, ForeignKey("alert_sessions.session_id"), index=True),
        description="Original session this chat extends"
    )
    
    # Timestamps
    created_at_us: int = Field(
        default_factory=now_us,
        sa_column=Column(BIGINT),
        description="Chat creation timestamp"
    )
    
    # Creator (first user who started the chat)
    created_by: Optional[str] = Field(
        default=None,
        description="User who initiated the chat"
    )
    
    # Session Context Snapshot - Typed Fields
    conversation_history: str = Field(
        description="Formatted text of complete session investigation (from LLM interactions)"
    )
    
    chain_id: str = Field(
        description="Chain ID from original session (denormalized for convenience)"
    )
    
    mcp_selection: Optional[dict] = Field(
        default=None,
        sa_column=Column(JSON),
        description="MCP server/tool selection used in original session (MCPSelectionConfig structure)"
    )
    
    context_captured_at_us: int = Field(
        sa_column=Column(BIGINT),
        description="Timestamp when context was captured from session"
    )
    
    # Pod Tracking for Multi-Replica Support (mirrors AlertSession pattern)
    pod_id: Optional[str] = Field(
        default=None,
        description="Kubernetes pod identifier for multi-replica chat message tracking"
    )
    
    last_interaction_at: Optional[int] = Field(
        default=None,
        sa_column=Column(BIGINT),
        description="Last interaction timestamp (microseconds) for orphan detection during chat message processing"
    )


class ChatUserMessage(SQLModel, table=True):
    """User questions in a chat conversation.
    
    Note: AI responses are tracked via StageExecution → LLMInteraction/MCPInteraction.
    This provides full observability using existing audit trail infrastructure.
    """
    
    __tablename__ = "chat_user_messages"
    
    __table_args__ = (
        Index('ix_chat_user_messages_chat_id', 'chat_id'),
        Index('ix_chat_user_messages_created_at', 'created_at_us'),
    )
    
    # Identity
    message_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        primary_key=True,
        description="Unique message identifier"
    )
    
    # Chat relationship
    chat_id: str = Field(
        sa_column=Column(String, ForeignKey("chats.chat_id", ondelete="CASCADE"), index=True),
        description="Parent chat"
    )
    
    # Message content
    content: str = Field(
        description="User's question text"
    )
    
    # Attribution
    author: str = Field(
        description="User email/ID who sent the message"
    )
    
    # Timestamp
    created_at_us: int = Field(
        default_factory=now_us,
        sa_column=Column(BIGINT),
        description="Message creation timestamp"
    )
```

#### Modified Models

**StageExecution** - Add chat context tracking:
```python
class StageExecution(SQLModel, table=True):
    """Represents the execution of a single stage within a chain processing session."""
    
    # ... existing fields ...
    
    # NEW: Chat context tracking
    chat_id: Optional[str] = Field(
        default=None,
        description="Chat ID if this execution is a chat response"
    )
    chat_user_message_id: Optional[str] = Field(
        default=None,
        description="User message ID this execution is responding to"
    )
```

**Note:** `LLMInteraction` and `MCPInteraction` do NOT need modification! They already link to `stage_execution_id`, which now includes chat context. This provides full observability using existing infrastructure.

**ChainConfigModel** - Add chat configuration:
```python
class ChainConfigModel(BaseModel):
    """Configuration model for a single chain."""
    
    # ... existing fields ...
    
    # NEW: Chat capability
    chat_enabled: bool = Field(
        default=True,
        description="Enable follow-up chat for sessions using this chain"
    )
```

**StageExecution** - Already updated above in Data Model section (adds `chat_id` and `chat_user_message_id` fields).

**Note:** This modification enables full observability for chat responses by linking StageExecution → LLMInteraction/MCPInteraction through existing `stage_execution_id` relationships.

**ChainContext** - Add optional chat context field:
```python
class ChainContext(BaseModel):
    """Context for entire chain processing session."""
    
    # ... existing fields ...
    
    # NEW: Chat-specific context (only present for chat executions)
    chat_context: Optional[dict] = None
    # Contains: conversation_history, user_question, chat_id
```

**Note:** Chat uses the same `ChainContext` → `StageContext` flow as regular sessions, ensuring compatibility with existing agent infrastructure.

---

## Component Design

### 1. Chat Agent (Built-in)

New built-in agent specifically for handling chat conversations:

```python
class ChatAgent(BaseAgent):
    """
    Built-in agent for handling follow-up chat conversations.
    
    Uses ReAct iteration strategy with full tool access to answer
    follow-up questions while preserving session context.
    
    Note: ChatAgent doesn't override mcp_servers(). Instead, it relies on
    ChainContext.mcp (MCPSelectionConfig) which is passed to _get_available_tools()
    during processing. This allows dynamic server/tool selection per chat execution.
    """
    
    def __init__(
        self,
        llm_client: LLMClient,
        mcp_client: MCPClient,
        mcp_registry: MCPServerRegistry,
        iteration_strategy: IterationStrategy = IterationStrategy.REACT
    ):
        super().__init__(llm_client, mcp_client, mcp_registry, iteration_strategy)
        # max_iterations inherited from BaseAgent (uses get_settings().max_llm_mcp_iterations)
        # Defaults: max_iterations=30, llm_iteration_timeout=180s
        # Same limits as regular stage agents!
    
    def agent_name(self) -> str:
        return "ChatAgent"
    
    def mcp_servers(self) -> List[str]:
        """
        Return empty list - ChatAgent has no default servers.
        
        Unlike regular agents (which define default MCP servers), ChatAgent ALWAYS
        uses the MCP configuration from the parent session via ChainContext.mcp.
        
        This ensures chat has access to the EXACT same servers/tools that were
        available during the original investigation - whether those came from:
        - Custom MCP selection in the alert request, OR
        - Default servers from the chain/stage configuration
        """
        return []
    
    def custom_instructions(self) -> str:
        """
        Generate instructions for chat agent.
        
        Note: The conversation history is NOT included here - it's added
        to the first user message by the chat-specific ReAct controller.
        """
        return '''You are an AI SRE assistant helping with follow-up questions about an alert investigation.

The user has reviewed a completed investigation and has a follow-up question.

Guidelines:
1. Reference the investigation history when relevant
2. Use tools to gather fresh data if needed  
3. Be concise but thorough in your responses
4. If the question is ambiguous, ask for clarification in your Final Answer
5. Maintain the same professional SRE communication style

Use the ReAct format:
- Thought: Reason about what information you need
- Action: Specify which tool to use (if needed)
- Action Input: Tool parameters  
- Observation: Tool results (will be provided)
- ... (repeat as needed)
- Final Answer: Your complete response to the user
'''
```

### 2. Context Helper Functions

Helper functions for formatting conversation history from LLM interactions:

```python
def format_conversation_history_as_text(conversation: LLMConversation) -> str:
    """
    Format LLM conversation as readable investigation history.
    
    Extracts user/assistant messages (skips system instructions) and formats
    with clear section markers to distinguish historical context from current
    chat instructions.
    
    The formatted history includes:
    - Initial investigation request (alert data, runbook, available tools)
    - All ReAct reasoning (Thought/Action cycles)
    - Tool observations (results)
    - Final analysis
    
    Args:
        conversation: LLMConversation from LLMInteraction.conversation field
        
    Returns:
        Formatted string with clear section markers
        
    Note: The tools list from the original investigation is preserved as context.
    This shows what tools were available during the investigation. The ChatAgent
    will receive its own current tools list in the system message.
    """
    sections = []
    sections.append("=" * 80)
    sections.append("ORIGINAL ALERT INVESTIGATION HISTORY")
    sections.append("=" * 80)
    sections.append("")
    
    for i, msg in enumerate(conversation.messages):
        # Skip system messages - those are instructions we'll re-add for chat
        if msg.role == MessageRole.SYSTEM:
            continue
        
        # Format each message with clear headers
        if msg.role == MessageRole.USER:
            # User messages in investigation are either:
            # - Initial prompt (tools + alert + runbook + task)
            # - Observations (tool results)
            if i == 1:  # First user message after system
                sections.append("### Initial Investigation Request")
                sections.append("")
                sections.append(msg.content)
                sections.append("")
            else:
                # Tool result observation
                sections.append("**Observation:**")
                sections.append("")
                sections.append(msg.content)
                sections.append("")
        
        elif msg.role == MessageRole.ASSISTANT:
            # Assistant messages contain Thought/Action/Final Answer
            sections.append("**Agent Response:**")
            sections.append("")
            sections.append(msg.content)
            sections.append("")
    
    sections.append("=" * 80)
    sections.append("END OF INVESTIGATION HISTORY")
    sections.append("=" * 80)
    sections.append("")
    
    return "\n".join(sections)
```

### 3. Chat Service

New service for managing chat lifecycle and message processing.

**Design Note:** ChatService follows the same patterns as AlertService for consistency and reliability:
- Pod ownership tracking (graceful shutdown)
- Session interaction recording (orphan detection, EP-0024)
- **Chat interaction recording** - Updates chat's `last_interaction_at` timestamp to keep processing marker fresh
- Timeout handling (600s like sessions)
- MCP client cleanup in finally blocks
- Stage execution lifecycle management
- Event publishing via stage execution hooks (no new events needed!)

**Note on Interaction Recording:**
- `record_session_interaction(session_id)` - Updates parent session timestamp (existing behavior)
- `record_chat_interaction(chat_id)` - Updates chat's own timestamp (new for chats)
- Both should be called during ReAct loop (via hooks during LLM/MCP interactions)
- Keeps both session and chat marked as active for orphan detection

The code is duplicated rather than abstracted because:
1. ✅ Makes code easier to read and understand
2. ✅ Allows independent evolution of alert vs chat flows
3. ✅ Avoids premature abstraction (YAGNI principle)
4. ✅ Maintains clear responsibility boundaries

If we see 3+ similar services emerge, we can extract common patterns then.

```python
from dataclasses import dataclass

@dataclass
class SessionContextData:
    """Typed container for captured session context."""
    conversation_history: str
    chain_id: str
    captured_at_us: int


class ChatService:
    """Service for managing follow-up chat conversations."""
    
    def __init__(
        self,
        history_service: HistoryService,
        agent_factory: AgentFactory,
        mcp_manager: MCPManager,
        llm_provider_manager: LLMProviderManager
    ):
        self.history_service = history_service
        self.agent_factory = agent_factory
        self.mcp_manager = mcp_manager
        self.llm_provider_manager = llm_provider_manager
    
    async def create_chat(
        self, 
        session_id: str,
        created_by: str
    ) -> Chat:
        """
        Create a new chat for a completed session.
        
        Steps:
        1. Validate session exists and is completed
        2. Check if chat already exists
        3. Validate chain has chat_enabled=true
        4. Capture session context (using _capture_session_context)
        5. Determine MCP servers (chain config + session custom)
        6. Create Chat record with initial_context
        
        Returns:
            Created Chat object
        """
        # Get session and validate
        session = await self.history_service.get_alert_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        if session.status != "completed":
            raise ValueError("Can only create chat for completed sessions")
        
        # Check if chat already exists
        existing_chat = await self.chat_repository.get_chat_by_session(session_id)
        if existing_chat:
            return existing_chat
        
        # Validate chain has chat enabled (implementation detail)
        # ...
        
        # Capture session context from LLM interactions (returns typed dataclass)
        context = await self._capture_session_context(session_id)
        
        # Determine MCP selection for chat
        # This captures which servers/tools were used in the original session
        mcp_selection = self._determine_mcp_selection_from_session(session)
        
        # Create chat record with typed fields (type-safe!)
        chat = Chat(
            session_id=session_id,
            created_by=created_by,
            conversation_history=context.conversation_history,
            chain_id=context.chain_id,
            mcp_selection=mcp_selection.model_dump() if mcp_selection else None,
            context_captured_at_us=context.captured_at_us
        )
        
        return await self.chat_repository.create_chat(chat)
    
    async def send_message(
        self,
        chat_id: str,
        user_question: str,
        author: str
    ) -> str:
        """
        Process a user message and generate assistant response.
        
        Follows the same patterns as AlertService.process_alert() for consistency:
        - Pod ownership tracking (graceful shutdown support)
        - Session interaction recording (orphan detection)
        - Timeout handling (600s like sessions)
        - MCP client cleanup in finally block
        - Stage execution lifecycle management
        - Event publishing via stage execution hooks (reuses existing events)
        
        Returns:
            Stage execution ID for this chat response
            
        Raises:
            ValueError: If chat not found or validation fails
            asyncio.TimeoutError: If execution exceeds timeout
            Exception: Other processing errors
        """
        chat_mcp_client = None
        execution_id = None
        
        try:
            # 1. Get chat and validate
            chat = await self.chat_repository.get_chat_by_id(chat_id)
            if not chat:
                raise ValueError(f"Chat {chat_id} not found")
            
            # 2. Create user message record
            user_msg = ChatUserMessage(
                chat_id=chat_id,
                content=user_question,
                author=author
            )
            await self.chat_repository.create_user_message(user_msg)
            
            # 3. Build context (initial context OR cumulative from last execution)
            message_context = await self._build_message_context(chat, user_question)
            
            # 4. Create stage execution for this response
            # Uses stage execution context manager (like AlertService)
            stage_execution = StageExecution(
                session_id=chat.session_id,
                stage_id=f"chat-response-{user_msg.message_id}",
                stage_index=0,  # Chat messages don't have meaningful stage index
                stage_name="Chat Response",
                agent="ChatAgent",
                status=StageStatus.PENDING.value,
                chat_id=chat_id,
                chat_user_message_id=user_msg.message_id
            )
            
            # Trigger stage execution hooks (creates DB record, publishes events)
            from tarsy.hooks.hook_context import stage_execution_context
            async with stage_execution_context(chat.session_id, stage_execution) as ctx:
                pass
            
            execution_id = stage_execution.execution_id
            logger.info(f"Created chat message execution {execution_id} for chat {chat_id}")
            
            # 5. Track pod ownership for graceful shutdown (mirrors AlertService)
            from tarsy.main import get_pod_id
            pod_id = get_pod_id()
            
            if pod_id == "unknown":
                logger.warning(
                    "TARSY_POD_ID not set - chat messages from multiple pods may not gracefully shutdown"
                )
            
            # Start chat message processing tracking (sets pod_id and last_interaction_at)
            if self.history_service:
                await self.history_service.start_chat_message_processing(chat_id, pod_id)
            
            logger.debug(f"Chat message {execution_id} being processed by pod {pod_id}")
            
            # 6. Record interaction timestamps for orphan detection
            # Both session (parent) and chat need their timestamps updated
            if self.history_service:
                # Update parent session timestamp
                if hasattr(self.history_service, "record_session_interaction"):
                    rec = self.history_service.record_session_interaction
                    if asyncio.iscoroutinefunction(rec):
                        await rec(chat.session_id)
                    else:
                        await asyncio.to_thread(rec, chat.session_id)
                
                # Update chat timestamp (keeps processing marker fresh)
                if hasattr(self.history_service, "record_chat_interaction"):
                    rec_chat = self.history_service.record_chat_interaction
                    if asyncio.iscoroutinefunction(rec_chat):
                        await rec_chat(chat_id)
                    else:
                        await asyncio.to_thread(rec_chat, chat_id)
            
            # 7. Update stage execution to started
            await self._update_stage_execution_started(execution_id)
            
            # 8. Get MCP selection from chat
            mcp_selection = (
                MCPSelectionConfig(**chat.mcp_selection) 
                if chat.mcp_selection 
                else None
            )
            
            # 9. Create session-scoped MCP client for this chat execution
            logger.info(f"Creating MCP client for chat message {execution_id}")
            chat_mcp_client = await self.mcp_client_factory.create_client()
            
            # 10. Create ChatAgent with MCP selection configuration
            chat_agent = self.agent_factory.create_agent(
                agent_name="ChatAgent",
                mcp_client=chat_mcp_client
            )
            
            # Set stage execution ID for interaction tagging
            chat_agent.set_current_stage_execution_id(execution_id)
            
            # 11. Build ChainContext for chat (minimal, for compatibility)
            from tarsy.models.processing_context import ChainContext
            from tarsy.models.alert import ProcessingAlert
            
            processing_alert = ProcessingAlert(
                alert_type="chat",  # Special type for chat
                alert_data={"chat_id": chat_id, "user_question": user_question},
                mcp=mcp_selection  # Pass MCP selection
            )
            
            chain_context = ChainContext.from_processing_alert(
                processing_alert=processing_alert,
                session_id=chat.session_id,
                current_stage_name="chat-response",
                author=author
            )
            
            # Add chat-specific context to chain_context
            chain_context.chat_context = message_context
            
            # 12. Execute ChatAgent with timeout (600s like sessions)
            try:
                result = await asyncio.wait_for(
                    chat_agent.process_alert(chain_context),
                    timeout=600.0
                )
                
                # 13. Update stage execution as completed
                await self._update_stage_execution_completed(execution_id, result)
                
                logger.info(f"Chat message {execution_id} completed successfully")
                return execution_id
                
            except asyncio.TimeoutError:
                error_msg = "Chat message processing exceeded 600s timeout"
                logger.error(f"{error_msg} for execution {execution_id}")
                await self._update_stage_execution_failed(execution_id, error_msg)
                raise
            
        except Exception as e:
            error_msg = f"Chat message processing failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            
            # Update stage execution as failed if we have execution_id
            if execution_id:
                await self._update_stage_execution_failed(execution_id, str(e))
            
            raise
        
        finally:
            # CRITICAL: Always cleanup MCP client (like AlertService)
            if chat_mcp_client:
                try:
                    logger.debug(f"Closing MCP client for chat message {execution_id}")
                    await chat_mcp_client.close()
                    logger.debug(f"MCP client closed for chat message {execution_id}")
                except Exception as cleanup_error:
                    logger.warning(f"Error closing chat MCP client: {cleanup_error}")
    
    async def get_chat_history(
        self,
        chat_id: str,
        limit: Optional[int] = None
    ) -> List[ChatMessage]:
        """Retrieve chat message history."""
        pass
    
    async def close_chat(self, chat_id: str) -> None:
        """Mark chat as closed (future enhancement)."""
        pass
    
    # Context Building Helpers
    # 
    # These methods handle extracting and formatting conversation history
    # for chat messages. The design eliminates duplication by using a
    # common helper for both initial chat creation and subsequent messages.
    #
    # Flow:
    # 1. create_chat() → _capture_session_context() 
    #                   → _get_formatted_conversation_from_llm_interactions()
    #                   → Stores formatted text in chat.conversation_history
    #
    # 2. send_message() → _build_message_context()
    #    First message:  → Returns chat.conversation_history (pre-formatted)
    #    Later messages: → _get_formatted_conversation_from_llm_interactions()
    #                    → Formats conversation from last chat execution
    
    async def _get_formatted_conversation_from_llm_interactions(
        self,
        llm_interactions: List[LLMInteraction]
    ) -> str:
        """
        Extract and format conversation history from LLM interactions.
        
        Takes the LAST interaction (which contains complete cumulative history)
        and formats it as readable text for the chat agent.
        
        This is the core helper used by both:
        - create_chat(): Gets conversation from session's LLM interactions
        - send_message(): Gets conversation from previous chat execution's LLM interactions
        
        Args:
            llm_interactions: List of LLM interactions (ordered by timestamp)
        
        Returns:
            Formatted conversation history as text
        """
        if not llm_interactions:
            raise ValueError("No LLM interactions provided for formatting")
        
        # Get last interaction - has complete cumulative conversation
        last_interaction = llm_interactions[-1]
        
        # Format as readable text
        return format_conversation_history_as_text(last_interaction.conversation)
    
    async def _capture_session_context(self, session_id: str) -> SessionContextData:
        """
        Capture session context for initial chat creation.
        
        Gets the complete investigation history from the session's
        LLM interactions and formats it for chat use.
        
        Returns:
            SessionContextData with conversation_history, chain_id, and timestamp
        """
        # Get session's LLM interactions
        llm_interactions = await self.history_service.get_llm_interactions_for_session(
            session_id
        )
        
        # Format conversation using common helper
        history_text = await self._get_formatted_conversation_from_llm_interactions(
            llm_interactions
        )
        
        # Get session for metadata
        session = await self.history_service.get_alert_session(session_id)
        
        # Return typed dataclass
        return SessionContextData(
            conversation_history=history_text,
            chain_id=session.chain_id,
            captured_at_us=now_us()
        )
    
    def _determine_mcp_selection_from_session(
        self,
        session: AlertSession
    ) -> Optional[MCPSelectionConfig]:
        """
        Capture the MCP configuration that was actually used during the session.
        
        This ensures chat has access to the SAME servers/tools as the original
        investigation, regardless of whether they came from:
        - Custom MCP selection provided in the alert request, OR
        - Default MCP servers defined in agents.yaml for the chain/stages
        
        Strategy:
        1. If session.mcp_selection exists (alert had custom MCP selection):
           → Use that (preserves server names + any tool filtering)
           
        2. Otherwise (session used default agent servers):
           → Extract default servers from chain_definition.stages
           → Look up each agent's default mcp_servers from configuration
           → Build MCPSelectionConfig from those defaults (no tool filtering)
        
        Returns:
            MCPSelectionConfig with the servers/tools used during the session,
            or None if no MCP servers were used (shouldn't happen in practice)
        """
        # Case 1: Session had custom MCP selection from alert request
        if session.mcp_selection:
            logger.info(f"Chat using custom MCP selection from session {session.session_id}")
            return MCPSelectionConfig(**session.mcp_selection)
        
        # Case 2: Session used default agent servers - reconstruct them
        if not session.chain_definition:
            logger.warning(f"No chain definition in session {session.session_id}")
            return None
        
        # Extract unique server names from all stages' default configurations
        server_names = set()
        chain_def = session.chain_definition
        
        for stage in chain_def.get("stages", []):
            agent_name = stage.get("agent")
            if not agent_name:
                continue
            
            # Look up agent's default MCP servers from configuration
            # Option 1: Query agent_factory.agent_configs if it's a ConfigurableAgent
            # Option 2: Check builtin agent config via get_builtin_agent_config()
            # Implementation depends on where agent configs are stored
            
            # Example (pseudocode):
            if agent_name in self.agent_factory.agent_configs:
                agent_config = self.agent_factory.agent_configs[agent_name]
                server_names.update(agent_config.mcp_servers)
            else:
                # Builtin agent - get from builtin config
                from tarsy.config.builtin_config import get_builtin_agent_config
                builtin_config = get_builtin_agent_config(agent_name)
                if builtin_config and "mcp_servers" in builtin_config:
                    server_names.update(builtin_config["mcp_servers"])
        
        if not server_names:
            logger.warning(f"No MCP servers found in chain definition for session {session.session_id}")
            return None
        
        logger.info(f"Chat using default servers from chain: {sorted(server_names)}")
        
        # Build MCPSelectionConfig from collected default servers (no tool filtering)
        from tarsy.models.mcp_selection_models import MCPServerSelection
        return MCPSelectionConfig(
            servers=[
                MCPServerSelection(name=server_name, tools=None)
                for server_name in sorted(server_names)
            ]
        )
    
    async def _build_message_context(
        self,
        chat: Chat,
        user_question: str
    ) -> dict:
        """
        Build context for new chat message including conversation history.
        
        Strategy for context accumulation:
        - First chat message: Use chat.conversation_history (captured from session)
        - Subsequent messages: Get last chat execution's LLM interactions
          (which naturally includes all previous context + chat Q&A)
        
        This is cumulative - each LLM interaction contains the full history,
        so we just need the most recent one.
        
        Returns:
            Dict with 'conversation_history' (formatted text) and user_question
        """
        # Get previous chat executions for this chat
        prev_executions = await self._get_chat_executions(chat.chat_id)
        
        if not prev_executions:
            # First chat message - use pre-formatted context from session
            # (Already formatted during create_chat())
            context_history = chat.conversation_history
        else:
            # Subsequent message - get last chat execution's LLM interactions
            last_exec = prev_executions[-1]
            llm_interactions = await self.history_service.get_llm_interactions_for_stage(
                last_exec.execution_id
            )
            
            # Format conversation using common helper (includes previous chat Q&A)
            context_history = await self._get_formatted_conversation_from_llm_interactions(
                llm_interactions
            )
        
        return {
            "conversation_history": context_history,
            "user_question": user_question,
            "chat_id": chat.chat_id
        }
    
    async def _get_chat_executions(self, chat_id: str) -> List[StageExecution]:
        """
        Get all stage executions for a chat, ordered by timestamp.
        """
        return await self.chat_repository.get_stage_executions_for_chat(chat_id)
    
    # Stage Execution Lifecycle Methods (similar to AlertService)
    
    async def _update_stage_execution_started(self, stage_execution_id: str):
        """
        Update stage execution as started.
        
        Similar to AlertService._update_stage_execution_started()
        """
        try:
            if not self.history_service:
                return
            
            # Get existing stage execution record
            existing_stage = await self.history_service.get_stage_execution(stage_execution_id)
            if not existing_stage:
                logger.warning(f"Stage execution {stage_execution_id} not found for update")
                return
            
            # Update to active status and set start time
            existing_stage.status = StageStatus.ACTIVE.value
            existing_stage.started_at_us = now_us()
            
            # Trigger stage execution hooks (updates DB + broadcasts to dashboard)
            from tarsy.hooks.hook_context import stage_execution_context
            async with stage_execution_context(existing_stage.session_id, existing_stage) as ctx:
                pass
            
            logger.debug(f"Chat execution {stage_execution_id} marked as started")
            
        except Exception as e:
            logger.warning(f"Failed to update stage execution as started: {str(e)}")
    
    async def _update_stage_execution_completed(
        self, 
        stage_execution_id: str, 
        result: AgentExecutionResult
    ):
        """
        Update stage execution as completed.
        
        Similar to AlertService._update_stage_execution_completed()
        """
        try:
            if not self.history_service:
                return
            
            # Get existing stage execution record
            existing_stage = await self.history_service.get_stage_execution(stage_execution_id)
            if not existing_stage:
                logger.warning(f"Stage execution {stage_execution_id} not found for update")
                return
            
            # Update completion fields
            existing_stage.status = result.status.value
            existing_stage.completed_at_us = result.timestamp_us
            existing_stage.stage_output = result.model_dump(mode='json')
            existing_stage.error_message = None
            
            # Calculate duration
            if existing_stage.started_at_us and existing_stage.completed_at_us:
                existing_stage.duration_ms = int(
                    (existing_stage.completed_at_us - existing_stage.started_at_us) / 1000
                )
            
            # Trigger stage execution hooks (updates DB + broadcasts to dashboard)
            from tarsy.hooks.hook_context import stage_execution_context
            async with stage_execution_context(existing_stage.session_id, existing_stage) as ctx:
                pass
            
            logger.debug(f"Chat execution {stage_execution_id} marked as completed")
            
        except Exception as e:
            logger.warning(f"Failed to update stage execution as completed: {str(e)}")
    
    async def _update_stage_execution_failed(self, stage_execution_id: str, error_message: str):
        """
        Update stage execution as failed.
        
        Similar to AlertService._update_stage_execution_failed()
        """
        try:
            if not self.history_service:
                return
            
            # Get existing stage execution record
            existing_stage = await self.history_service.get_stage_execution(stage_execution_id)
            if not existing_stage:
                logger.warning(f"Stage execution {stage_execution_id} not found for update")
                return
            
            # Update failure fields
            existing_stage.status = StageStatus.FAILED.value
            existing_stage.completed_at_us = now_us()
            existing_stage.stage_output = None
            existing_stage.error_message = error_message
            
            # Calculate duration
            if existing_stage.started_at_us and existing_stage.completed_at_us:
                existing_stage.duration_ms = int(
                    (existing_stage.completed_at_us - existing_stage.started_at_us) / 1000
                )
            
            # Trigger stage execution hooks (updates DB + broadcasts to dashboard)
            from tarsy.hooks.hook_context import stage_execution_context
            async with stage_execution_context(existing_stage.session_id, existing_stage) as ctx:
                pass
            
            logger.debug(f"Chat execution {stage_execution_id} marked as failed")
            
        except Exception as e:
            logger.warning(f"Failed to update stage execution as failed: {str(e)}")
```

### 3.1. Hook System Extensions for Chat

The existing hook system (used for session LLM/MCP tracking) needs minor extensions to handle chat interaction recording alongside session interaction recording.

**Current Hook Behavior (Sessions):**
```python
# In BaseAgent or hook callbacks during LLM/MCP calls:
def on_llm_new_token(self, token, ...):
    # Record session interaction to keep it marked as active
    if history_service:
        history_service.record_session_interaction(session_id)

def on_tool_start(self, tool, ...):
    # Record session interaction
    if history_service:
        history_service.record_session_interaction(session_id)
```

**Extended Hook Behavior (Chats):**
```python
# In BaseAgent or hook callbacks:
def on_llm_new_token(self, token, ...):
    # Record session interaction (existing)
    if history_service and session_id:
        history_service.record_session_interaction(session_id)
    
    # NEW: Also record chat interaction if this is a chat execution
    if history_service and chat_id:  # chat_id available from StageExecution context
        history_service.record_chat_interaction(chat_id)

def on_tool_start(self, tool, ...):
    # Record session interaction (existing)
    if history_service and session_id:
        history_service.record_session_interaction(session_id)
    
    # NEW: Also record chat interaction if this is a chat execution
    if history_service and chat_id:
        history_service.record_chat_interaction(chat_id)
```

**Implementation Notes:**

1. **Chat ID Detection:** The hooks can determine if they're processing a chat message by checking if `StageExecution.chat_id` is set
2. **Parallel Recording:** Both session and chat timestamps get updated during ReAct iterations
3. **No New Hooks:** Existing hooks (`on_llm_new_token`, `on_llm_end`, `on_tool_start`, `on_tool_end`) are sufficient
4. **Graceful Degradation:** If `record_chat_interaction` is not available (older code), only session recording happens

**Example Hook Implementation:**
```python
class BaseAgent:
    def _get_current_chat_id(self) -> Optional[str]:
        """Get chat_id from current stage execution if this is a chat message."""
        if not self.current_stage_execution_id:
            return None
        
        # Query StageExecution to get chat_id
        stage_exec = self.history_repository.get_stage_execution(
            self.current_stage_execution_id
        )
        return stage_exec.chat_id if stage_exec else None
    
    def on_llm_new_token(self, token, **kwargs):
        """Hook called for each LLM token during streaming."""
        # ... existing token handling ...
        
        # Update activity timestamps
        if self.history_service:
            # Session timestamp (existing)
            if self.session_id:
                try:
                    self.history_service.record_session_interaction(self.session_id)
                except Exception as e:
                    logger.debug(f"Failed to record session interaction: {e}")
            
            # Chat timestamp (new)
            chat_id = self._get_current_chat_id()
            if chat_id:
                try:
                    self.history_service.record_chat_interaction(chat_id)
                except Exception as e:
                    logger.debug(f"Failed to record chat interaction: {e}")
```

**Alternative: Simpler Approach**

Instead of querying StageExecution in hooks, pass `chat_id` through context:

```python
# In ChatService.send_message():
chain_context.chat_id = chat_id  # Add chat_id to context

# In hooks:
def on_llm_new_token(self, token, **kwargs):
    if self.history_service:
        # Session
        if hasattr(self, 'session_id') and self.session_id:
            self.history_service.record_session_interaction(self.session_id)
        
        # Chat (if context has chat_id)
        if hasattr(self, 'chat_id') and self.chat_id:
            self.history_service.record_chat_interaction(self.chat_id)
```

**Frequency:** These hooks fire frequently during ReAct loops (every LLM token, every tool call), ensuring `last_interaction_at` stays fresh even during long-running chat message processing.

### 4. Chat-Specific ReAct Controller

New iteration controller for chat that prepends history to user messages:

```python
class ChatReActController(ReactController):
    """
    ReAct controller for chat that includes conversation history in user messages.
    
    Differs from standard ReAct by prepending formatted investigation history
    and previous chat messages to the initial user message.
    """
    
    def build_initial_conversation(self, context: 'StageContext') -> LLMConversation:
        """Build initial conversation for chat with history context."""
        
        # Get chat context from processing context
        chat_context = context.chat_context  # Added to StageContext for chat
        conversation_history = chat_context['conversation_history']
        user_question = chat_context['user_question']
        
        # System message with chat instructions (from ChatAgent.custom_instructions)
        system_content = self.prompt_builder.get_enhanced_react_system_message(
            context.agent._compose_instructions(),
            "answering follow-up questions about a completed investigation"
        )
        
        # User message = history + current question + ReAct instructions
        user_content = f"""{conversation_history}

================================================================================
FOLLOW-UP CHAT SESSION
================================================================================

The user has reviewed the investigation above and has a follow-up question.

You have access to the same tools that were used in the original investigation
(they are listed in the "Initial Investigation Request" section above).

**User's Follow-up Question:**

{user_question}

**Your Task:**

Answer the user's question using the ReAct format shown in your instructions.
Reference the investigation history when relevant, and use tools to gather 
fresh data if needed.

Begin your ReAct reasoning:
"""
        
        return LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content=system_content),
            LLMMessage(role=MessageRole.USER, content=user_content)
        ])
    
    def extract_final_analysis(self, analysis_result: str, context) -> str:
        """Extract final answer from ReAct conversation."""
        return self._extract_react_final_analysis(analysis_result)
```

### 5. Chat Repository

Database access layer for chat operations:

```python
class ChatRepository:
    """Repository for chat and chat message database operations."""
    
    def create_chat(self, chat: Chat) -> Chat:
        """Create new chat record."""
        pass
    
    def get_chat_by_id(self, chat_id: str) -> Optional[Chat]:
        """Get chat by ID."""
        pass
    
    def get_chat_by_session(self, session_id: str) -> Optional[Chat]:
        """Get chat for a session (if exists)."""
        pass
    
    def update_chat_last_message_time(self, chat_id: str, timestamp_us: int) -> None:
        """Update last message timestamp."""
        pass
    
    def create_message(self, message: ChatMessage) -> ChatMessage:
        """Create new chat message."""
        pass
    
    def get_messages_by_chat(
        self,
        chat_id: str,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> List[ChatMessage]:
        """Get messages for a chat, ordered by timestamp."""
        pass
    
    def get_message_count(self, chat_id: str) -> int:
        """Get total message count for a chat."""
        pass
    
    def get_stage_executions_for_chat(
        self,
        chat_id: str
    ) -> List[StageExecution]:
        """
        Get all stage executions for a chat, ordered by timestamp.
        
        Used to retrieve previous chat message executions for building
        cumulative conversation context.
        
        Args:
            chat_id: Chat identifier
        
        Returns:
            List of StageExecution records where chat_id matches, 
            ordered by created_at_us ASC
        """
        pass
    
    # Pod Tracking & Orphan Detection (mirrors AlertSession pattern)
    
    def update_chat_pod_tracking(
        self,
        chat_id: str,
        pod_id: str
    ) -> bool:
        """
        Update chat with pod tracking information.
        Sets pod_id and updates last_interaction_at timestamp.
        
        Args:
            chat_id: Chat identifier
            pod_id: Pod identifier to assign
        
        Returns:
            True if update successful, False otherwise
        """
        pass
    
    def find_chats_by_pod(
        self,
        pod_id: str
    ) -> List[Chat]:
        """
        Find chats being processed by a specific pod.
        
        Only returns chats with non-NULL last_interaction_at, indicating
        they have active message processing in progress.
        
        Args:
            pod_id: Kubernetes pod identifier
        
        Returns:
            List of Chat records being processed by the pod
        """
        pass
    
    def find_orphaned_chats(
        self,
        timeout_threshold_us: int
    ) -> List[Chat]:
        """
        Find chats with stale last_interaction_at (orphaned processing).
        
        Returns chats where:
        1. last_interaction_at is not NULL (processing started)
        2. last_interaction_at is older than timeout threshold
        
        Args:
            timeout_threshold_us: Timestamp threshold - chats with 
                                 last_interaction_at older than this are orphaned
        
        Returns:
            List of Chat records with stale processing
        """
        pass
```

### 6. HistoryService Extensions

Pod tracking and orphan detection for chat messages:

```python
class HistoryService:
    """Extended with chat pod tracking and orphan detection."""
    
    async def start_chat_message_processing(
        self,
        chat_id: str,
        pod_id: str
    ) -> bool:
        """
        Mark chat as processing a message on a specific pod.
        Updates pod_id and last_interaction_at.
        
        Called at the start of ChatService.send_message() to track
        which pod is handling the message for graceful shutdown.
        
        Args:
            chat_id: Chat identifier
            pod_id: Kubernetes pod identifier
        
        Returns:
            True if successful, False otherwise
        """
        if not self.is_enabled:
            return False
        
        def _start_operation():
            with self.get_repository() as repo:
                if not repo:
                    return False
                return repo.update_chat_pod_tracking(chat_id, pod_id)
        
        return self._retry_database_operation(
            "start_chat_message_processing",
            _start_operation
        ) or False
    
    def record_chat_interaction(self, chat_id: str) -> bool:
        """
        Update chat last_interaction_at timestamp.
        
        Called periodically during long-running chat message processing
        to keep the chat marked as active for orphan detection.
        
        Note: Synchronous function. When calling from async code,
        use asyncio.to_thread() to avoid blocking.
        
        Args:
            chat_id: Chat identifier
        
        Returns:
            True if successful, False otherwise
        """
        if not self.is_enabled:
            return False
        
        def _record_operation():
            with self.get_repository() as repo:
                if not repo:
                    return False
                from tarsy.utils.timestamp import now_us
                chat = repo.get_chat_by_id(chat_id)
                if not chat:
                    return False
                chat.last_interaction_at = now_us()
                return repo.update_chat(chat)
        
        return self._retry_database_operation(
            "record_chat_interaction",
            _record_operation
        ) or False
    
    def cleanup_orphaned_chats(
        self,
        timeout_minutes: int = 30
    ) -> int:
        """
        Find and clear stale processing markers from orphaned chats.
        
        An orphaned chat is one with last_interaction_at older than the timeout,
        indicating processing started but never completed (pod crash, timeout, etc).
        
        Unlike sessions, chats don't have a FAILED state. We simply clear the
        processing markers (pod_id, last_interaction_at) to indicate no active processing.
        
        Args:
            timeout_minutes: Inactivity threshold in minutes (default: 30)
        
        Returns:
            Number of chats cleaned up
        """
        if not self.is_enabled:
            return 0
        
        def _cleanup_operation():
            with self.get_repository() as repo:
                if not repo:
                    return 0
                
                from tarsy.utils.timestamp import now_us
                timeout_us = timeout_minutes * 60 * 1_000_000
                threshold = now_us() - timeout_us
                
                orphaned_chats = repo.find_orphaned_chats(threshold)
                
                # Clear processing markers
                for chat in orphaned_chats:
                    chat.pod_id = None
                    chat.last_interaction_at = None
                    repo.update_chat(chat)
                
                return len(orphaned_chats)
        
        count = self._retry_database_operation(
            "cleanup_orphaned_chats",
            _cleanup_operation
        )
        
        if count and count > 0:
            logger.info(
                f"Cleaned up {count} orphaned chat message processing markers"
            )
        
        return count or 0
    
    async def mark_pod_chats_interrupted(self, pod_id: str) -> int:
        """
        Clear processing markers for chats on a shutting-down pod.
        
        Called during graceful shutdown to mark chat message processing
        as interrupted. Unlike sessions (which get marked FAILED), chats
        just have their processing markers cleared.
        
        Args:
            pod_id: Kubernetes pod identifier
        
        Returns:
            Number of chats marked as interrupted
        """
        if not self.is_enabled:
            return 0
        
        def _interrupt_operation():
            with self.get_repository() as repo:
                if not repo:
                    return 0
                
                active_chats = repo.find_chats_by_pod(pod_id)
                
                # Clear processing markers
                for chat in active_chats:
                    chat.pod_id = None
                    chat.last_interaction_at = None
                    repo.update_chat(chat)
                
                return len(active_chats)
        
        count = self._retry_database_operation(
            "mark_interrupted_chats",
            _interrupt_operation
        )
        
        if count and count > 0:
            logger.info(
                f"Marked {count} chat message(s) as interrupted for pod {pod_id}"
            )
        
        return count or 0
```

### 7. Graceful Shutdown & Orphan Detection

Chat messages extend TARSy's existing graceful shutdown and orphan detection mechanisms to handle multi-replica deployments.

#### Pod Tracking Architecture

**Session-Level Tracking (Existing):**
```
AlertSession {
    pod_id: "tarsy-deployment-abc123"
    last_interaction_at: 1234567890000000  // Updated during processing
}
```

**Chat-Level Tracking (New):**
```
Chat {
    pod_id: "tarsy-deployment-abc123"  // Set when message processing starts
    last_interaction_at: 1234567890000000  // Updated during message processing
}
```

**Key Difference:** Unlike sessions (which have status transitions), chats use processing markers:
- `pod_id != NULL` + `last_interaction_at != NULL` = Message processing in progress
- `pod_id == NULL` + `last_interaction_at == NULL` = No active processing

#### Graceful Shutdown Flow

**Current (Sessions Only):**
```
SIGTERM received
    ↓
1. Set shutdown_in_progress = True (rejects new alerts)
2. Wait for active session tasks (600s timeout)
3. If timeout/error: Call mark_pod_sessions_interrupted(pod_id)
   → Sets status=FAILED, error_message="interrupted during shutdown"
```

**Extended (Sessions + Chats):**
```
SIGTERM received
    ↓
1. Set shutdown_in_progress = True (rejects new alerts AND chat messages)
2. Wait for active session tasks AND active chat tasks (600s timeout)
3. If timeout/error:
   a. Call mark_pod_sessions_interrupted(pod_id)
      → Marks sessions as FAILED
   b. Call mark_pod_chats_interrupted(pod_id)
      → Clears chat processing markers (pod_id, last_interaction_at)
```

**Implementation in `main.py`:**
```python
async def mark_active_tasks_as_interrupted(reason: str) -> None:
    """Mark both sessions and chats as interrupted."""
    if history_service is None:
        return
    
    pod_id = get_pod_id()
    
    # Mark sessions as interrupted (existing)
    session_count = await history_service.mark_pod_sessions_interrupted(pod_id)
    if session_count > 0:
        logger.info(f"Marked {session_count} session(s) as interrupted {reason} for pod {pod_id}")
    
    # Mark chats as interrupted (new)
    chat_count = await history_service.mark_pod_chats_interrupted(pod_id)
    if chat_count > 0:
        logger.info(f"Marked {chat_count} chat message(s) as interrupted {reason} for pod {pod_id}")

# During shutdown in lifespan():
try:
    # Wait for both session tasks and chat tasks
    async with active_tasks_lock:
        all_tasks = list(active_tasks.values()) + list(active_chat_tasks.values())
    
    await asyncio.wait_for(
        asyncio.gather(*all_tasks, return_exceptions=True),
        timeout=settings.alert_processing_timeout
    )
except asyncio.TimeoutError:
    await mark_active_tasks_as_interrupted("after timeout")
```

#### Orphan Detection

**Session Orphan Detection (Existing):**
```sql
-- Find sessions with stale last_interaction_at
SELECT * FROM alert_sessions 
WHERE status = 'in_progress' 
  AND last_interaction_at < (NOW() - INTERVAL '30 minutes')
  AND last_interaction_at IS NOT NULL;

-- Action: Mark as FAILED with error message
UPDATE alert_sessions 
SET status = 'failed',
    error_message = 'Session became unresponsive',
    completed_at_us = NOW()
WHERE ...;
```

**Chat Orphan Detection (New):**
```sql
-- Find chats with stale last_interaction_at
SELECT * FROM chats 
WHERE last_interaction_at < (NOW() - INTERVAL '30 minutes')
  AND last_interaction_at IS NOT NULL;

-- Action: Clear processing markers (no FAILED state for chats)
UPDATE chats 
SET pod_id = NULL,
    last_interaction_at = NULL
WHERE ...;
```

**Cleanup Integration:**

`HistoryCleanupService` periodic task extended to include chats:

```python
class HistoryCleanupService:
    async def _cleanup_loop(self):
        while self.running:
            try:
                # Existing: Cleanup orphaned sessions
                await self._cleanup_orphaned_sessions()
                
                # New: Cleanup orphaned chats
                await self._cleanup_orphaned_chats()
                
                # Existing: Retention cleanup (if interval elapsed)
                if self._should_run_retention_cleanup():
                    await self._cleanup_old_history()
                    self._update_last_retention_cleanup()
                
                await asyncio.sleep(self.orphaned_cleanup_interval)
            except Exception as e:
                logger.error(f"Cleanup loop error: {e}")
    
    async def _cleanup_orphaned_chats(self) -> None:
        """Clean up stale chat message processing markers."""
        try:
            history_service = get_history_service()
            count = history_service.cleanup_orphaned_chats(
                self.orphaned_timeout_minutes
            )
            if count > 0:
                logger.info(
                    f"Cleaned up {count} orphaned chat message processing markers"
                )
        except Exception as e:
            logger.error(f"Failed to cleanup orphaned chats: {e}")
```

#### Why Different Approaches?

**Sessions have status transitions:**
- PENDING → IN_PROGRESS → COMPLETED/FAILED
- Failed sessions are terminal states with error messages
- Clear lifecycle with start and end

**Chats use processing markers:**
- Chat entity persists indefinitely
- Processing markers indicate "message currently being processed"
- Clearing markers = "processing abandoned, ready for new messages"
- No concept of "failed chat" - individual messages can fail

This design allows chats to continue accepting new messages even if a previous message processing was interrupted.

### 8. WebSocket Events & Streaming

**Key Decision:** Reuse existing `session:{session_id}` channel for chat events.

**Rationale:**
- Dashboard already subscribes to `session:{session_id}` channel
- Subscription stays active as long as user is viewing the session (component lifecycle)
- Chat is an extension of the session, so same channel is logical
- No changes needed to existing streaming infrastructure

**Chat Event Types:**

```python
class ChatEventType(str, Enum):
    """Chat-specific WebSocket event types."""
    CHAT_CREATED = "chat.created"
    CHAT_USER_MESSAGE = "chat.user_message"
    # Note: AI responses stream via existing LLM streaming events!

# Event models
class ChatCreatedEvent(BaseEvent):
    """Published when a chat is created for a session."""
    type: Literal["chat.created"] = "chat.created"
    chat_id: str
    session_id: str
    created_by: str

class ChatUserMessageEvent(BaseEvent):
    """Published when a user sends a message to the chat."""
    type: Literal["chat.user_message"] = "chat.user_message"
    chat_id: str
    message_id: str
    content: str
    author: str
    timestamp_us: int
```

**AI Response Streaming:** Uses existing `LLMStreamChunkEvent`!

```python
# When ChatAgent generates response, existing streaming events fire:
LLMStreamChunkEvent(
    type="llm.stream.chunk",
    session_id=session_id,  # Original session ID
    stage_execution_id=stage_exec_id,  # Links to StageExecution with chat_id
    chunk=content,
    stream_type="thought",  # or "final_answer"
    is_complete=False
)

# Dashboard already handles these events!
# No changes needed to streaming infrastructure.
```

**WebSocket Channel:**
- **Single Channel:** `session:{session_id}` for all events (session lifecycle, LLM streaming, MCP tool calls, chat events)
- **Dashboard Behavior:** Subscription stays active while viewing session detail page, regardless of session status
- **Chat Events:** Published to same channel, dashboard recognizes `chat.*` event types

### 5. API Endpoints

New REST endpoints for chat operations:

```python
# POST /api/v1/sessions/{session_id}/chat
# Create a new chat for a completed session
# Returns: Chat object

# GET /api/v1/chats/{chat_id}
# Get chat details
# Returns: Chat object with message count

# POST /api/v1/chats/{chat_id}/messages
# Send a message to the chat
# Body: { "content": "user question", "author": "user@example.com" }
# Returns: Created user message (assistant response via WebSocket)
# Rejects with 503 if shutdown_in_progress (like alert submission)

# GET /api/v1/chats/{chat_id}/messages
# Get chat message history
# Query params: ?limit=50&offset=0
# Returns: List of ChatMessage objects

# GET /api/v1/sessions/{session_id}/chat-available
# Check if chat is available for a session
# Returns: { "available": bool, "reason": "optional message" }
```

---

## Configuration

### Chain Configuration (agents.yaml)

```yaml
agent_chains:
  kubernetes-alert-investigation:
    chain_id: "kubernetes-alert-investigation"
    alert_types:
      - "PodCrashLoop"
      - "NamespaceTerminating"
    stages:
      - name: "Initial Analysis"
        agent: "kubernetes-investigator"
      - name: "Deep Dive"
        agent: "kubernetes-deep-dive"
    description: "Kubernetes alert investigation chain"
    
    # NEW: Chat configuration
    chat_enabled: true  # Default: true, can set to false to disable
```

### Environment Variables

**Chat reuses existing agent configuration from settings:**

```bash
# Existing settings that apply to chat (no new env vars needed!)
MAX_LLM_MCP_ITERATIONS=30       # Max ReAct iterations (default: 30)
LLM_ITERATION_TIMEOUT=180       # Timeout per iteration in seconds (default: 180s = 3min)
ALERT_PROCESSING_TIMEOUT=600    # Overall timeout per chat response (default: 600s = 10min)

# Optional: Global chat enable/disable (could be added later)
# CHAT_ENABLED=true
```

**Note:** ChatAgent uses the same `get_settings().max_llm_mcp_iterations` and timeout settings as regular agents, ensuring consistent behavior across the system.

---

## UI/UX Design

### Session Detail Page - Chat Not Started

```
┌───────────────────────────────────────────────────────┐
│ Session Detail - COMPLETED                            │
│                                                       │
│ [Session Header with status badge]                    │
│ [Original Alert Card]                                 │
│ [Timeline/Stages]                                     │
│ [Final Analysis Card]                                 │
│                                                       │
│ ┌─────────────────────────────────────────────────┐   │
│ │ 💬 Have follow-up questions?                    │   │
│ │                                                 │   │
│ │ Continue the investigation with AI assistance   │   │
│ │                                                 │   │
│ │ [Start Follow-up Chat] button (primary)         │   │
│ └─────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────┘
```

### Session Detail Page - Chat Active

```
┌───────────────────────────────────────────────────────┐
│ Session Detail - COMPLETED                            │
│                                                       │
│ [Session Header - can collapse]                       │
│ [Original Alert - can collapse]                       │
│ [Timeline - can collapse for focus]                   │
│ [Final Analysis - can collapse]                       │
│                                                       │
│ ┌─────────────────────────────────────────────────┐   │
│ │ 💬 Follow-up Chat              [Collapse] [✕]   │   │
│ │─────────────────────────────────────────────────│   │
│ │                                                 │   │
│ │ alice@company.com • 2 minutes ago               │   │
│ │ Can you check the pod logs from 2 hours ago?    │   │
│ │                                                 │   │
│ │ 🤖 TARSy • 2 minutes ago                        │   │
│ │ Let me fetch those logs for you...              │   │
│ │ [Tool Call: kubectl logs...]                    │   │
│ │ I found the following in the logs:              │   │
│ │ [Analysis with markdown formatting]             │   │
│ │                                                 │   │
│ │ bob@company.com • 1 minute ago                  │   │
│ │ What about the database connection?             │   │
│ │                                                 │   │
│ │ 🤖 TARSy • typing... [streaming indicator]      │   │
│ │                                                 │   │
│ │─────────────────────────────────────────────────│   │
│ │ Type your question...                  [Send]   │   │
│ │ Shift+Enter for new line                        │   │
│ └─────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────┘
```

### Chat Message Components

**User Message:**
```
┌─────────────────────────────────────────────────┐
│ alice@company.com • 2 minutes ago               │
│ Can you check the pod logs from 2 hours ago?    │
└─────────────────────────────────────────────────┘
```

**Assistant Message with Tool Calls:**
```
┌─────────────────────────────────────────────────┐
│ 🤖 TARSy • 2 minutes ago                        │
│                                                 │
│ Let me investigate the pod logs...              │
│                                                 │
│ ▼ Tool Call: kubectl logs                       │
│   pod: my-pod, namespace: production            │
│   Result: [expandable/collapsible]              │
│                                                 │
│ Based on the logs, I found:                     │
│ - Error at 12:34:56                            │
│ - Out of memory condition                       │
│ - Process terminated                            │
└─────────────────────────────────────────────────┘
```

### Dashboard Sessions List - Chat Indicator

Add indicator when session has active chat:

```
┌──────────────────────────────────────────────────┐
│ PodCrashLoop • COMPLETED • 2 hours ago  💬(5)   │
│ my-app-pod crashed in production                │
│ 3 stages • 45s duration                         │
└──────────────────────────────────────────────────┘
                                          ↑
                                    Chat active
                                    with 5 messages
```

---

## Implementation Plan

### Phase 1: Core Infrastructure

**Backend:**
1. Add database migrations for `chats` (with pod tracking fields) and `chat_messages` tables
2. Add `chat_id` and `chat_user_message_id` fields to `StageExecution` table
3. Implement `ChatRepository` for database operations (including pod tracking methods)
4. Extend `HistoryRepository` with chat pod tracking methods:
   - `update_chat_pod_tracking()`
   - `find_chats_by_pod()`
   - `find_orphaned_chats()`
5. Extend `HistoryService` with chat tracking methods:
   - `start_chat_message_processing()`
   - `record_chat_interaction()`
   - `cleanup_orphaned_chats()`
   - `mark_pod_chats_interrupted()`
6. Extend `HistoryCleanupService` to include chat orphan cleanup
7. Update `main.py` graceful shutdown to handle chat tasks:
   - Add `active_chat_tasks` dictionary
   - Extend `mark_active_tasks_as_interrupted()` to include chats
   - Update shutdown logic to wait for chat tasks
8. Add `chat_enabled` field to `ChainConfigModel`
9. Create `ChatAgent` built-in agent
10. Implement `ChatService` (create chat, send message with full lifecycle management)

### Phase 2: Chat Agent & Tool Execution

**Backend:**
1. Implement session context capture logic (`format_conversation_history_as_text`)
2. Implement MCP server determination logic (chain + session)
3. Create `ChatReActController` (prepends conversation history)
4. Wire up `ChatAgent` with `ChatReActController`
5. **Extend hook system** to call `record_chat_interaction()` during LLM/MCP operations:
   - Update `BaseAgent` hooks (`on_llm_new_token`, `on_tool_start`, etc.)
   - Add chat_id detection from StageExecution or context
   - Ensure both session and chat timestamps get updated
6. Implement tool execution tracking (StageExecution with chat tags)
7. Add WebSocket events for chat (ChatCreatedEvent, ChatUserMessageEvent)

### Phase 3: API Endpoints

**Backend:**
1. Implement REST endpoints for chat operations
2. Add authorization checks (reuse session auth logic)
3. Add request validation
4. Implement WebSocket streaming for chat responses
5. Add error handling and timeouts

### Phase 4: UI Implementation

**Frontend:**
1. Add "Start Follow-up Chat" button to session detail page
2. Implement chat message list component
3. Implement message input component
4. Add WebSocket subscription for chat updates
5. Implement real-time streaming of assistant responses
6. Add chat indicator to sessions list
7. Handle multi-user message attribution

---

## Appendix

### Chat Context Architecture

#### Design Decision: Text-Based Context from LLM Interactions

The chat feature uses a **text-based context extraction** approach that leverages existing `LLMInteraction` records rather than building structured JSON contexts. This decision provides several benefits:

**Key Insights:**
1. `LLMInteraction.conversation` already contains the complete investigation history
2. Each LLM interaction includes all previous context (cumulative)
3. The last LLM interaction of a session = complete investigation record
4. Simple text formatting is more robust than complex JSON parsing
5. Tools list preservation provides valuable historical context

**Context Flow:**

```
Session Investigation
  └─> Multiple LLM Interactions (ordered by timestamp)
      └─> Last interaction has full conversation:
          - System: Instructions + MCP tools
          - User: Alert data + runbook + available tools + task
          - Assistant: Thought + Action
          - User: Observation (tool result)
          - Assistant: Thought + Action
          - User: Observation
          - Assistant: Final Answer

Chat Creation
  └─> Extract last LLM interaction
      └─> Format as text with section markers
          └─> Store in Chat.initial_context['conversation_history']

First Chat Message
  └─> Prepend conversation_history to user question
      └─> ChatAgent processes with ReAct
          └─> Creates new LLMInteraction (includes history + chat Q&A)

Subsequent Chat Messages
  └─> Get last chat execution's LLM interaction
      └─> Format that conversation (now includes previous chat)
          └─> Prepend to new user question
              └─> ChatAgent processes
                  └─> Creates new LLMInteraction (cumulative)
```

**Benefits:**
- ✅ Simple: Just string formatting
- ✅ Complete: All investigation details preserved
- ✅ Robust: No complex parsing of structured data
- ✅ Cumulative: Each interaction builds on previous
- ✅ Reuses infrastructure: Existing LLMInteraction queries

**Known Limitations:**
- Tools list reflects investigation time (may differ from current)
- Very old sessions may reference removed/changed tools
- Large investigations create large context (token usage consideration)

### Example Initial Context Structure

**Example Chat Record:**

```python
Chat(
    chat_id="chat-abc-123",
    session_id="session-123",
    created_by="alice@example.com",
    created_at_us=1730908800000000,
    
    # Context snapshot fields
    conversation_history="================================================================================\n"
                         "ORIGINAL ALERT INVESTIGATION HISTORY\n"
                         "================================================================================\n\n"
                         "### Initial Investigation Request\n\n"
                         "Answer the following question using the available tools.\n\n"
                         "Available tools:\n"
                         "1. **kubernetes-server.get_pods**: List pods in namespace\n"
                         "2. **kubernetes-server.get_pod_logs**: Get pod logs\n"
                         "...\n\n"
                         "Question: Analyze this PodCrashLoop alert...\n\n"
                         "[... full investigation history ...]\n\n"
                         "================================================================================\n"
                         "END OF INVESTIGATION HISTORY\n"
                         "================================================================================\n",
    
    chain_id="kubernetes-triage",
    
    mcp_selection={
        "servers": [
            {"name": "kubernetes-server", "tools": None},
            {"name": "prometheus-server", "tools": ["query", "query_range"]}
        ]
    },
    
    context_captured_at_us=1730908800000000
)
```

**Notes about the typed fields:**

1. **`conversation_history`** (TEXT):
   - Large text field containing formatted investigation history
   - Directly accessible without JSON parsing

2. **`chain_id`** (STRING):
   - Denormalized from session for convenience
   - Useful for filtering/grouping chats by chain type

3. **`mcp_selection`** (JSON):
   - Structured data that naturally fits JSON format
   - Preserves MCPSelectionConfig structure

4. **Benefits of typed fields:**
   - Type-safe schema enforced by database
   - No JSON parsing overhead for text fields
   - Queryable by individual fields
   - Clear, maintainable schema

**Notes about `mcp_selection`:**

1. **Structure:** Uses `MCPSelectionConfig` format from alert processing:
   - Each server can optionally specify a list of tools
   - `tools: null` means all tools from that server are available
   - `tools: ["query", "query_range"]` means only those specific tools

2. **Source:** Captured from the original session's actual configuration:
   - If alert request included custom `mcp` field → use that (with tool filtering)
   - If alert used default agent servers → extract from agents.yaml (no filtering)

3. **Purpose:** Ensures chat has the SAME tool access as the original investigation

### Complete Example: First Chat Message

This example shows what the ChatAgent receives when processing the first user question.

**User sends:** `"Can you check if there were any warnings in the logs before the crash?"`

**ChatReActController builds this user message:**

```
================================================================================
ORIGINAL ALERT INVESTIGATION HISTORY
================================================================================

### Initial Investigation Request

Answer the following question using the available tools.

Available tools:
1. **kubernetes-server.get_pods**: List pods in namespace with status
   Parameters: namespace (required)
2. **kubernetes-server.get_pod_logs**: Get logs from a pod
   Parameters: namespace, pod_name, container, since, tail

Question: Analyze this PodCrashLoop alert and provide actionable recommendations.

## Alert Details
**Alert Type:** PodCrashLoop
**Severity:** critical
**Namespace:** production
**Pod:** my-app-5d4c8f9b-xyz

[... full alert data ...]

## Runbook Content
[... full runbook if available ...]

**Agent Response:**

Thought: I need to check the pod status first to understand the crash pattern
Action: kubernetes-server.get_pods
Action Input: {"namespace": "production"}

**Observation:**

NAME                STATUS             RESTARTS   AGE
my-app-5d4c8f9b-xyz CrashLoopBackOff   12         2h

**Agent Response:**

Thought: The pod has restarted 12 times. I need to check the logs to find the cause
Action: kubernetes-server.get_pod_logs
Action Input: {"namespace": "production", "pod_name": "my-app-5d4c8f9b-xyz", "tail": "100"}

**Observation:**

[2024-11-06 14:32:10] Starting application...
[2024-11-06 14:32:12] Loading configuration...
[2024-11-06 14:32:13] Error: Out of memory
[2024-11-06 14:32:13] Fatal error, exiting

**Agent Response:**

Thought: I have enough information to provide a complete analysis
Final Answer: The pod is experiencing an Out of Memory (OOM) condition...

[... complete final analysis ...]

================================================================================
END OF INVESTIGATION HISTORY
================================================================================

================================================================================
FOLLOW-UP CHAT SESSION
================================================================================

The user has reviewed the investigation above and has a follow-up question.

You have access to the same tools that were used in the original investigation
(they are listed in the "Initial Investigation Request" section above).

**User's Follow-up Question:**

Can you check if there were any warnings in the logs before the crash?

**Your Task:**

Answer the user's question using the ReAct format shown in your instructions.
Reference the investigation history when relevant, and use tools to gather 
fresh data if needed.

Begin your ReAct reasoning:
```

**ChatAgent ReAct Loop:**

```
Thought: The user wants warnings before the crash. The previous investigation showed the crash at 14:32:13. I should get more logs with timestamps before that to look for warnings.

Action: kubernetes-server.get_pod_logs
Action Input: {"namespace": "production", "pod_name": "my-app-5d4c8f9b-xyz", "tail": "200"}

Observation: [Extended log output with 200 lines]

Thought: Now I can analyze the logs for warnings before the crash

Final Answer: Yes, there were several warnings before the crash:
1. [14:32:08] WARNING: Memory usage at 85%
2. [14:32:09] WARNING: Memory usage at 92%  
3. [14:32:10] WARNING: GC pressure increasing
4. [14:32:12] WARNING: Memory usage at 98%

These warnings appeared in the 5 seconds before the OOM crash, showing a rapid memory increase.
```

### Example: Subsequent Chat Message

**User sends:** `"What was the memory limit set for this pod?"`

**Context building:**
1. Get last chat execution's LLM interaction
2. That interaction now contains: original investigation history + first chat Q&A
3. Format it as text and prepend to new question

**ChatReActController builds:**

```
[... Original Investigation History (same as before) ...]

================================================================================
CHAT CONVERSATION HISTORY  
================================================================================

**User Question (alice@example.com, 2024-11-06 14:35:00):**
Can you check if there were any warnings in the logs before the crash?

**Agent Response:**
[Full ReAct reasoning and answer from previous chat message]

================================================================================
NEW USER MESSAGE
================================================================================

What was the memory limit set for this pod?

Begin your ReAct reasoning:
```

**ChatAgent processes:** References investigation history, may use tools to check current pod spec, provides answer.

---

### Pod Tracking & Graceful Shutdown: Complete Design

This section provides a comprehensive overview of how chat messages integrate with TARSy's multi-replica pod tracking and graceful shutdown mechanisms.

#### Overview

Chat extends the existing session-level pod tracking to ensure chat message processing is resilient to pod crashes, restarts, and graceful shutdowns in multi-replica Kubernetes deployments.

#### Data Model Extensions

**Chat Table - New Fields:**
```python
class Chat(SQLModel, table=True):
    # ... existing fields ...
    
    # Pod tracking for multi-replica support
    pod_id: Optional[str] = Field(
        default=None,
        description="Kubernetes pod identifier for multi-replica chat message tracking"
    )
    
    last_interaction_at: Optional[int] = Field(
        default=None,
        sa_column=Column(BIGINT),
        description="Last interaction timestamp (microseconds) for orphan detection"
    )
```

**Index for Efficient Queries:**
```sql
CREATE INDEX ix_chats_pod_last_interaction ON chats (pod_id, last_interaction_at);
```

#### Processing State Machine

**Chat Message Processing States:**

1. **Idle** (No Active Processing):
   - `pod_id = NULL`
   - `last_interaction_at = NULL`
   - Chat can accept new messages

2. **Processing** (Message Being Handled):
   - `pod_id = "tarsy-deployment-abc123"`
   - `last_interaction_at = 1234567890000000` (updated periodically)
   - Chat locked to specific pod

3. **Completed** (Message Finished):
   - Returns to Idle state (pod_id and last_interaction_at cleared)
   - Chat ready for next message

4. **Orphaned** (Processing Stalled):
   - `pod_id != NULL`
   - `last_interaction_at < (NOW - 30 minutes)`
   - Detected by cleanup service, markers cleared

#### Lifecycle Methods

**HistoryRepository Extensions:**
```python
# Set processing state (called at message start)
def update_chat_pod_tracking(chat_id: str, pod_id: str) -> bool:
    chat.pod_id = pod_id
    chat.last_interaction_at = now_us()
    return update_chat(chat)

# Find chats owned by pod (for graceful shutdown)
def find_chats_by_pod(pod_id: str) -> List[Chat]:
    return SELECT * FROM chats 
           WHERE pod_id = pod_id 
           AND last_interaction_at IS NOT NULL

# Find stale processing (for orphan cleanup)
def find_orphaned_chats(timeout_threshold_us: int) -> List[Chat]:
    return SELECT * FROM chats
           WHERE last_interaction_at < timeout_threshold_us
           AND last_interaction_at IS NOT NULL
```

**HistoryService Extensions:**
```python
# Start tracking (called by ChatService.send_message)
async def start_chat_message_processing(chat_id: str, pod_id: str) -> bool:
    """Mark chat as processing on this pod."""
    return repo.update_chat_pod_tracking(chat_id, pod_id)

# Update activity (called periodically during long processing)
def record_chat_interaction(chat_id: str) -> bool:
    """Update last_interaction_at to keep chat marked as active."""
    chat.last_interaction_at = now_us()
    return repo.update_chat(chat)

# Cleanup stale markers (called by HistoryCleanupService)
def cleanup_orphaned_chats(timeout_minutes: int = 30) -> int:
    """Clear processing markers from abandoned messages."""
    orphaned = repo.find_orphaned_chats(threshold)
    for chat in orphaned:
        chat.pod_id = None
        chat.last_interaction_at = None
        repo.update_chat(chat)
    return len(orphaned)

# Handle graceful shutdown (called during pod termination)
async def mark_pod_chats_interrupted(pod_id: str) -> int:
    """Clear processing markers for shutting-down pod."""
    active_chats = repo.find_chats_by_pod(pod_id)
    for chat in active_chats:
        chat.pod_id = None
        chat.last_interaction_at = None
        repo.update_chat(chat)
    return len(active_chats)
```

#### Graceful Shutdown Integration

**main.py Extensions:**

```python
# Global state
active_tasks: Dict[str, asyncio.Task] = {}        # session_id -> task
active_chat_tasks: Dict[str, asyncio.Task] = {}   # execution_id -> task
shutdown_in_progress: bool = False

async def mark_active_tasks_as_interrupted(reason: str) -> None:
    """Mark both sessions and chats as interrupted."""
    if history_service is None:
        return
    
    pod_id = get_pod_id()
    
    # Sessions (existing)
    session_count = await history_service.mark_pod_sessions_interrupted(pod_id)
    if session_count > 0:
        logger.info(f"Marked {session_count} session(s) as interrupted {reason}")
    
    # Chats (new)
    chat_count = await history_service.mark_pod_chats_interrupted(pod_id)
    if chat_count > 0:
        logger.info(f"Marked {chat_count} chat(s) as interrupted {reason}")

# Lifespan shutdown handler
async def lifespan(app: FastAPI):
    # ... startup ...
    yield
    
    # Shutdown sequence
    logger.info("Tarsy shutting down...")
    
    # 1. Reject new work
    shutdown_in_progress = True
    logger.info("Marked service as shutting down - rejecting new alerts/messages")
    
    # 2. Wait for active work (sessions + chats)
    async with active_tasks_lock:
        all_tasks = list(active_tasks.values()) + list(active_chat_tasks.values())
    
    if all_tasks:
        logger.info(f"Waiting for {len(all_tasks)} active task(s) to complete...")
        try:
            await asyncio.wait_for(
                asyncio.gather(*all_tasks, return_exceptions=True),
                timeout=600.0
            )
            logger.info("All tasks completed gracefully")
        except asyncio.TimeoutError:
            logger.warning(f"Graceful shutdown timeout - {len(all_tasks)} task(s) still active")
            await mark_active_tasks_as_interrupted("after timeout")
        except Exception as e:
            logger.error(f"Error during graceful shutdown: {e}")
            await mark_active_tasks_as_interrupted("after error")
    
    # ... cleanup MCP, event system, etc ...
```

**ChatController Shutdown Check:**

```python
@router.post("/api/v1/chats/{chat_id}/messages")
async def send_chat_message(chat_id: str, message: ChatMessageRequest):
    """Send a message to the chat."""
    from tarsy.main import shutdown_in_progress
    
    if shutdown_in_progress:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Service shutting down",
                "message": "Service is shutting down gracefully. Please retry.",
                "retry_after": 30
            }
        )
    
    # ... process message ...
```

#### Orphan Detection & Cleanup

**HistoryCleanupService Integration:**

```python
class HistoryCleanupService:
    async def _cleanup_loop(self):
        """Periodic cleanup of orphaned sessions and chats."""
        while self.running:
            try:
                # Sessions (existing)
                await self._cleanup_orphaned_sessions()
                
                # Chats (new)
                await self._cleanup_orphaned_chats()
                
                # Retention (existing, runs less frequently)
                if self._should_run_retention_cleanup():
                    await self._cleanup_old_history()
                    self._update_last_retention_cleanup()
                
                await asyncio.sleep(self.orphaned_cleanup_interval)  # Default: 60s
            except Exception as e:
                logger.error(f"Cleanup loop error: {e}")
    
    async def _cleanup_orphaned_chats(self) -> None:
        """Clean up stale chat message processing markers."""
        try:
            history_service = get_history_service()
            count = history_service.cleanup_orphaned_chats(
                self.orphaned_timeout_minutes  # Default: 30 minutes
            )
            if count > 0:
                logger.info(f"Cleaned up {count} orphaned chat processing markers")
        except Exception as e:
            logger.error(f"Failed to cleanup orphaned chats: {e}")
```

**Cleanup Cadence:**
- **Orphan Cleanup:** Every 60 seconds (checks both sessions and chats)
- **Timeout Threshold:** 30 minutes of inactivity
- **Retention Cleanup:** Every 24 hours (deletes old history, sessions only)

#### Design Rationale

**Why Different From Sessions?**

| Aspect | Sessions | Chats |
|--------|----------|-------|
| **Lifecycle** | PENDING → IN_PROGRESS → COMPLETED/FAILED | Persistent entity, no status |
| **Failure Handling** | Mark as FAILED with error message | Clear processing markers |
| **State Transitions** | Terminal states (COMPLETED, FAILED) | Returns to idle state |
| **Orphan Action** | Set status=FAILED, error_message | Set pod_id=NULL, last_interaction_at=NULL |
| **Retry** | Cannot retry failed session | Can send new message after cleanup |

**Benefits:**
- ✅ Chats remain available even after interrupted processing
- ✅ New messages can be sent after orphan cleanup
- ✅ Simpler state machine (idle vs processing)
- ✅ No terminal failure states to manage

**Trade-offs:**
- ⚠️ Individual message failures not tracked at chat level
- ⚠️ Must query StageExecution to see message processing history
- ✅ This is acceptable: StageExecution provides full audit trail per message

#### Summary

Chat pod tracking extends TARSy's robust multi-replica architecture to handle follow-up conversations:

1. **Pod Ownership:** Each chat message processing is owned by a specific pod
2. **Activity Tracking:** `last_interaction_at` updated during processing
3. **Graceful Shutdown:** Pods wait for active chat messages before terminating
4. **Orphan Detection:** Periodic cleanup recovers from pod crashes
5. **Resilient Design:** Chats continue accepting messages after interruptions

This design ensures reliable chat operation in Kubernetes deployments with rolling updates, autoscaling, and pod disruptions.
