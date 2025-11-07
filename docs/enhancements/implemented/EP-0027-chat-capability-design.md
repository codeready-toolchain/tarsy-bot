# EP-0027: Follow-up Chat Capability for TARSy Sessions

**Status:** Implemented  
**Created:** 2025-11-06  
**Implemented:** 2025-11-07  

---

## Overview

Add chat-like follow-up conversation capability to TARSy, allowing users to continue investigating after a session terminates (completed, failed, or cancelled). Users can ask clarifying questions, request deeper analysis, or explore different aspects of the original alert - all while preserving full context and tool execution capabilities.

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
    """Chat metadata and context snapshot from terminated session."""
    
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
    chat_context: Optional[ChatMessageContext] = None
    # Type-safe dataclass containing: conversation_history, user_question, chat_id
```

**Note:** Chat uses the same `ChainContext` → `StageContext` flow as regular sessions, ensuring compatibility with existing agent infrastructure. The `ChatMessageContext` dataclass provides type safety for chat-specific data.

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

**Note on Service Layering:**
- ChatService NEVER accesses repositories directly
- ALL database operations go through `HistoryService`
- HistoryService delegates to `HistoryRepository` (extended with chat methods)
- This maintains proper service → service → repository layering:
  - `ChatService` → `HistoryService` → `HistoryRepository` → Database
- Only service classes (like HistoryService) access repositories directly

```python
from dataclasses import dataclass

@dataclass
class SessionContextData:
    """Typed container for captured session context."""
    conversation_history: str
    chain_id: str
    captured_at_us: int


@dataclass
class ChatMessageContext:
    """
    Typed container for chat message context.
    
    Passed to ChatReActController via StageContext.chat_context
    to provide conversation history and user question.
    """
    conversation_history: str
    user_question: str
    chat_id: str


class ChatService:
    """
    Service for managing follow-up chat conversations.
    
    Architecture:
    - Orchestrates chat lifecycle and message processing
    - Delegates ALL database operations to HistoryService
    - Never directly accesses repositories (proper service layering)
    - Coordinates between HistoryService, AgentFactory, and MCP systems
    """
    
    def __init__(
        self,
        history_service: HistoryService,
        agent_factory: AgentFactory,
        mcp_manager: MCPManager,
        llm_provider_manager: LLMProviderManager
    ):
        self.history_service = history_service  # ALL DB operations go through here
        self.agent_factory = agent_factory
        self.mcp_manager = mcp_manager
        self.llm_provider_manager = llm_provider_manager
    
    async def create_chat(
        self, 
        session_id: str,
        created_by: str
    ) -> Chat:
        """
        Create a new chat for a terminated session.
        
        Steps:
        1. Validate session exists and is in a terminal state (completed, failed, or cancelled)
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
        
        # Check if session is in a terminal state (completed, failed, or cancelled)
        from tarsy.models.constants import AlertSessionStatus
        
        terminal_statuses = AlertSessionStatus.terminal_values()
        if session.status not in terminal_statuses:
            raise ValueError(
                f"Can only create chat for terminated sessions. "
                f"Current status: {session.status}, terminal statuses: {', '.join(terminal_statuses)}"
            )
        
        # Check if chat already exists (via history_service)
        existing_chat = await self.history_service.get_chat_by_session(session_id)
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
        
        return await self.history_service.create_chat(chat)
    
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
            # 1. Get chat and validate (via history_service)
            chat = await self.history_service.get_chat_by_id(chat_id)
            if not chat:
                raise ValueError(f"Chat {chat_id} not found")
            
            # 2. Create user message record (via history_service)
            user_msg = ChatUserMessage(
                chat_id=chat_id,
                content=user_question,
                author=author
            )
            await self.history_service.create_chat_user_message(user_msg)
            
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
            
            # Add chat-specific context to chain_context (type-safe!)
            chain_context.chat_context = message_context  # ChatMessageContext dataclass
            
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
    ) -> ChatMessageContext:
        """
        Build context for new chat message including conversation history.
        
        Strategy for context accumulation:
        - First chat message: Use chat.conversation_history (captured from session)
        - Subsequent messages: Get last chat execution's LLM interactions
          (which naturally includes all previous context + chat Q&A)
        
        This is cumulative - each LLM interaction contains the full history,
        so we just need the most recent one.
        
        Returns:
            ChatMessageContext with conversation_history, user_question, and chat_id
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
        
        # Return typed dataclass (type-safe!)
        return ChatMessageContext(
            conversation_history=context_history,
            user_question=user_question,
            chat_id=chat.chat_id
        )
    
    async def _get_chat_executions(self, chat_id: str) -> List[StageExecution]:
        """
        Get all stage executions for a chat, ordered by timestamp.
        
        Note: Delegates to HistoryService - services never access repositories directly.
        """
        return await self.history_service.get_stage_executions_for_chat(chat_id)
    
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
    
    Differs from standard ReAct by delegating user message construction to
    PromptBuilder.build_chat_user_message() which handles history formatting.
    """
    
    def build_initial_conversation(self, context: 'StageContext') -> LLMConversation:
        """Build initial conversation for chat with history context."""
        
        # Get chat context from processing context (type-safe!)
        chat_context: ChatMessageContext = context.chat_context
        
        # System message with chat instructions (from ChatAgent.custom_instructions)
        system_content = self.prompt_builder.get_enhanced_react_system_message(
            context.agent._compose_instructions(),
            "answering follow-up questions about a completed investigation"
        )
        
        # User message with history + question (delegated to prompt builder)
        user_content = self.prompt_builder.build_chat_user_message(
            conversation_history=chat_context.conversation_history,
            user_question=chat_context.user_question
        )
        
        return LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content=system_content),
            LLMMessage(role=MessageRole.USER, content=user_content)
        ])
    
    def extract_final_analysis(self, analysis_result: str, context) -> str:
        """Extract final answer from ReAct conversation."""
        return self._extract_react_final_analysis(analysis_result)
```

### 4.1. Prompt Builder Extension

Add chat-specific prompt construction to PromptBuilder:

```python
class PromptBuilder:
    """
    Handles prompt construction for agents.
    Extended to support chat-specific prompts.
    """
    
    def build_chat_user_message(
        self,
        conversation_history: str,
        user_question: str
    ) -> str:
        """
        Build user message for chat that includes conversation history.
        
        This formats the chat prompt by:
        1. Including the complete investigation history
        2. Clearly marking the transition to follow-up chat
        3. Presenting the user's question
        4. Providing instructions for the ReAct loop
        
        Args:
            conversation_history: Formatted investigation history from session
            user_question: User's follow-up question
        
        Returns:
            Formatted user message string for LLM
        """
        return f"""{conversation_history}

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
```

### 5. HistoryRepository Extensions (Chat Operations)

**Architecture Decision:** Chat database operations are added to `HistoryRepository` rather than creating a separate `ChatRepository`. This follows the existing pattern where all history/audit trail operations are centralized.

```python
class HistoryRepository:
    """
    Extended with chat and chat message database operations.
    
    All chat-related database access is consolidated here alongside
    session, stage execution, LLM interaction, and MCP interaction methods.
    """
    
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

HistoryService is extended to handle all chat-related database operations, maintaining proper service layer separation.

```python
class HistoryService:
    """
    Extended with chat CRUD operations, pod tracking, and orphan detection.
    
    Architecture Note:
    - ChatService calls HistoryService for all DB operations
    - HistoryService delegates to HistoryRepository (extended with chat methods)
    - This maintains proper service → service → repository layering
    """
    
    # Chat CRUD Operations (called by ChatService)
    
    async def create_chat(self, chat: Chat) -> Chat:
        """
        Create a new chat record.
        
        Args:
            chat: Chat object to create
        
        Returns:
            Created Chat object with database-assigned fields
        """
        if not self.is_enabled:
            raise ValueError("History service is disabled")
        
        def _create_operation():
            with self.get_repository() as repo:
                if not repo:
                    raise ValueError("Repository unavailable")
                return repo.create_chat(chat)
        
        return self._retry_database_operation("create_chat", _create_operation)
    
    async def get_chat_by_id(self, chat_id: str) -> Optional[Chat]:
        """
        Get chat by ID.
        
        Args:
            chat_id: Chat identifier
        
        Returns:
            Chat object if found, None otherwise
        """
        if not self.is_enabled:
            return None
        
        def _get_operation():
            with self.get_repository() as repo:
                if not repo:
                    return None
                return repo.get_chat_by_id(chat_id)
        
        return self._retry_database_operation("get_chat_by_id", _get_operation)
    
    async def get_chat_by_session(self, session_id: str) -> Optional[Chat]:
        """
        Get chat for a session (if exists).
        
        Args:
            session_id: Session identifier
        
        Returns:
            Chat object if exists, None otherwise
        """
        if not self.is_enabled:
            return None
        
        def _get_operation():
            with self.get_repository() as repo:
                if not repo:
                    return None
                return repo.get_chat_by_session(session_id)
        
        return self._retry_database_operation("get_chat_by_session", _get_operation)
    
    async def create_chat_user_message(self, message: ChatUserMessage) -> ChatUserMessage:
        """
        Create a new chat user message.
        
        Args:
            message: ChatUserMessage object to create
        
        Returns:
            Created message with database-assigned fields
        """
        if not self.is_enabled:
            raise ValueError("History service is disabled")
        
        def _create_operation():
            with self.get_repository() as repo:
                if not repo:
                    raise ValueError("Repository unavailable")
                return repo.create_chat_user_message(message)
        
        return self._retry_database_operation("create_chat_user_message", _create_operation)
    
    async def get_stage_executions_for_chat(
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
        if not self.is_enabled:
            return []
        
        def _get_operation():
            with self.get_repository() as repo:
                if not repo:
                    return []
                return repo.get_stage_executions_for_chat(chat_id)
        
        return self._retry_database_operation(
            "get_stage_executions_for_chat",
            _get_operation
        ) or []
    
    # Pod Tracking & Orphan Detection
    
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

#### Graceful Shutdown Integration

**Existing Implementation (Sessions) - Reference Pattern**

📁 **File:** `backend/tarsy/main.py` (lines ~120-330)
- Global: `active_tasks: Dict[str, asyncio.Task]` - Tracks session tasks
- Global: `shutdown_in_progress: bool` - Shutdown flag
- Function: `mark_active_sessions_as_interrupted()` - Marks sessions as interrupted
- Lifespan handler: Waits for active tasks, handles timeouts

📁 **File:** `backend/tarsy/services/history_service.py` (lines ~866-903)
- Method: `mark_pod_sessions_interrupted(pod_id)` - Marks sessions FAILED

**Implementation Tasks**

**Task 1:** Add chat task tracking to `main.py`

```python
# File: backend/tarsy/main.py
# Add near active_tasks definition (around line 68)

# Task tracking for session cancellation
active_tasks: Dict[str, asyncio.Task] = {}  # Existing - session_id -> task
active_chat_tasks: Dict[str, asyncio.Task] = {}  # NEW - execution_id -> task
active_tasks_lock: Optional[asyncio.Lock] = None
```

**Task 2:** Extend interrupt function in `main.py`

```python
# File: backend/tarsy/main.py
# Modify existing mark_active_sessions_as_interrupted() function (around line 120)
# Rename it to mark_active_tasks_as_interrupted()

async def mark_active_tasks_as_interrupted(reason: str) -> None:
    """
    Mark both sessions and chats as interrupted during shutdown.
    
    Pattern: Extend existing function to handle chats too.
    """
    if history_service is None:
        return
    
    pod_id = get_pod_id()
    
    # Sessions (existing code - keep as-is)
    session_count = await history_service.mark_pod_sessions_interrupted(pod_id)
    if session_count > 0:
        logger.info(f"Marked {session_count} session(s) as interrupted {reason}")
    
    # Chats (NEW - add this)
    chat_count = await history_service.mark_pod_chats_interrupted(pod_id)
    if chat_count > 0:
        logger.info(f"Marked {chat_count} chat(s) as interrupted {reason}")
```

**Task 3:** Update lifespan shutdown logic in `main.py`

```python
# File: backend/tarsy/main.py
# Modify lifespan() function shutdown section (around line 302)

# Inside lifespan() yield shutdown:
if active_tasks or active_chat_tasks:  # ADD: or active_chat_tasks
    # Combine both task dictionaries
    async with active_tasks_lock:
        all_tasks = list(active_tasks.values()) + list(active_chat_tasks.values())  # MODIFY
    
    logger.info(f"Waiting for {len(all_tasks)} active task(s)...")  # MODIFY: count
    
    try:
        await asyncio.wait_for(
            asyncio.gather(*all_tasks, return_exceptions=True),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        await mark_active_tasks_as_interrupted("after timeout")  # Call renamed function
```

**Task 4:** Add `mark_pod_chats_interrupted()` to `HistoryService`

```python
# File: backend/tarsy/services/history_service.py
# Add after mark_pod_sessions_interrupted() method (around line 904)

async def mark_pod_chats_interrupted(self, pod_id: str) -> int:
    """
    Clear processing markers for chats on shutting-down pod.
    
    Pattern: Copy from mark_pod_sessions_interrupted() but adapted for chats.
    
    Key Difference: Chats don't get marked FAILED, we just clear
    their processing markers (pod_id, last_interaction_at).
    
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
            
            # Find active chats for this pod
            active_chats = repo.find_chats_by_pod(pod_id)
            
            # Clear processing markers (different from sessions!)
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
        logger.info(f"Marked {count} chat(s) as interrupted for pod {pod_id}")
    
    return count or 0
```

**Implementation Notes:**
- ✅ Follow existing session shutdown patterns
- ✅ Add chat tasks to global tracking dictionaries
- ✅ Extend (don't replace) existing shutdown logic
- ✅ Chats clear markers instead of marking FAILED

#### Orphan Detection

**Existing Pattern (Sessions) - Reference for Implementation**

TARSy already has orphan detection for sessions. **Study these existing implementations** as a pattern for chat implementation:

📁 **File:** `backend/tarsy/repositories/history_repository.py`
- Method: `find_orphaned_sessions(timeout_threshold_us)` (lines ~830-850)
- Uses `select(AlertSession).where(...)` with SQLModel
- Filters by status, last_interaction_at, and threshold

📁 **File:** `backend/tarsy/services/history_service.py`
- Method: `cleanup_orphaned_sessions(timeout_minutes)` (lines ~820-865)
- Calls repository method
- Updates session status to FAILED
- Sets error_message

**Implementation Task: Add Chat Orphan Detection**

**Step 1:** Add to `HistoryRepository` (follow session pattern):

```python
# File: backend/tarsy/repositories/history_repository.py
# Add after find_orphaned_sessions() method

def find_orphaned_chats(
    self,
    timeout_threshold_us: int
) -> List[Chat]:
    """
    Find chats with stale last_interaction_at (orphaned processing).
    
    Pattern: Copy from find_orphaned_sessions() but adapted for Chat model.
    
    Returns chats where:
    - last_interaction_at IS NOT NULL (processing was started)
    - last_interaction_at < timeout_threshold_us (processing is stale)
    
    Args:
        timeout_threshold_us: Timestamp threshold in microseconds
    
    Returns:
        List of Chat records with stale processing markers
    """
    try:
        statement = select(Chat).where(
            Chat.last_interaction_at.isnot(None),
            Chat.last_interaction_at < timeout_threshold_us
        )
        return self.session.exec(statement).all()
    except Exception as e:
        logger.error(f"Failed to find orphaned chats: {str(e)}")
        raise
```

**Step 2:** Add to `HistoryService` (follow session pattern):

```python
# File: backend/tarsy/services/history_service.py
# Add after cleanup_orphaned_sessions() method

def cleanup_orphaned_chats(
    self,
    timeout_minutes: int = 30
) -> int:
    """
    Find and clear stale processing markers from orphaned chats.
    
    Pattern: Copy from cleanup_orphaned_sessions() but adapted for chats.
    
    Key Difference: Chats don't have a FAILED state. We just clear
    the processing markers (pod_id, last_interaction_at) to indicate
    no active processing.
    
    Args:
        timeout_minutes: Inactivity threshold (default: 30 minutes)
    
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
            
            # Get orphaned chats (follow session pattern)
            orphaned_chats = repo.find_orphaned_chats(threshold)
            
            # Clear processing markers (different from sessions!)
            for chat in orphaned_chats:
                chat.pod_id = None
                chat.last_interaction_at = None
                repo.update_chat(chat)  # Will need to add this method too
            
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
```

**Implementation Notes:**
- ✅ Use existing session methods as templates
- ✅ Copy the SQLModel query patterns
- ✅ Adapt field names (AlertSession → Chat)
- ✅ Key difference: Clear markers instead of marking as FAILED

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
# Create a new chat for a terminated session
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
# Available when session is in a terminal state (completed, failed, or cancelled)
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

### Actual Implementation: Unified Conversation Timeline

**Key Design Decision:** Chat messages are rendered inline within the existing `ConversationTimeline` component rather than in a separate chat message list. This creates a unified, chronological view of the entire investigation including follow-up conversations.

### Session Detail Page - Chat Not Started

```
┌───────────────────────────────────────────────────────┐
│ Session Detail - COMPLETED/FAILED/CANCELLED           │
│                                                       │
│ [Session Header with status badge]                    │
│ [Original Alert Card]                                 │
│ [Reasoning Tab - ConversationTimeline showing]       │
│ │ investigation stages, thoughts, tool calls, etc]    │
│ [Final Analysis Card]                                 │
│                                                       │
│ ┌─────────────────────────────────────────────────┐   │
│ │ 💬 Follow-up Chat                               │   │
│ │─────────────────────────────────────────────────│   │
│ │ Have questions about this investigation?        │   │
│ │                                                 │   │
│ │ [Start Chat] button (primary)                   │   │
│ └─────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────┘
```

### Session Detail Page - Chat Active

```
┌───────────────────────────────────────────────────────┐
│ Session Detail - COMPLETED/FAILED/CANCELLED           │
│                                                       │
│ [Session Header]                                      │
│ [Original Alert Card]                                 │
│                                                       │
│ [Reasoning Tab - ConversationTimeline showing:]      │
│ │ ┌─ Stage: Initial Analysis (Agent: K8s Agent) ──┐  │
│ │ │ 💭 Checking pod status...                     │  │
│ │ │ 🔧 Tool: kubectl get pod                      │  │
│ │ │ 🎯 Final Answer: Pod is in CrashLoopBackOff  │  │
│ │ └────────────────────────────────────────────────┘  │
│ │                                                     │
│ │ ┌─ Stage: Chat Response ────────────────────────┐  │
│ │ │ 👤 alice@company.com                          │  │
│ │ │ Can you check the pod logs from 2 hours ago?  │  │
│ │ │                                                │  │
│ │ │ 💭 Let me fetch those logs...                 │  │
│ │ │ 🔧 Tool: kubectl logs --since=2h              │  │
│ │ │ 🎯 Final Answer: Found OOM errors at 14:23   │  │
│ │ └────────────────────────────────────────────────┘  │
│ │                                                     │
│ │ ┌─ Stage: Chat Response ────────────────────────┐  │
│ │ │ 👤 bob@company.com                            │  │
│ │ │ What about the database connection?           │  │
│ │ │                                                │  │
│ │ │ 💭 Streaming... (typing indicator)            │  │
│ │ └────────────────────────────────────────────────┘  │
│                                                       │
│ [Final Analysis Card - auto-collapses on chat]      │
│                                                       │
│ ┌─────────────────────────────────────────────────┐   │
│ │ 💬 Follow-up Chat              [−] (collapse)   │   │
│ │─────────────────────────────────────────────────│   │
│ │ Type your question...                  [Send]   │   │
│ │ Shift+Enter for new line • [Cancel] (if active) │   │
│ └─────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────┘
```

### Component Breakdown

**User Message (rendered by `ChatFlowItem`):**
```
👤 alice@company.com
┌─────────────────────────────────────────────────┐
│ Can you check the pod logs from 2 hours ago?    │
└─────────────────────────────────────────────────┘
(Appears inline in timeline with grey background and user avatar icon)
```

**Assistant Response (rendered by standard `ChatFlowItem` components):**
```
💭 Let me investigate the pod logs...

🔧 Tool Call: kubectl logs
   ▼ kubectl logs --since=2h my-app-pod
   Result: [expandable/collapsible - shows logs]
   Duration: 250ms

🎯 Final Answer:
Based on the logs, I found:
- Out of Memory error at 14:23:45
- Pod was killed by OOMKiller
- Memory limit: 512Mi, Peak usage: 523Mi
(Rendered with markdown support)
```

### Chat Input Panel (`ChatPanel` component)

The `ChatPanel` component provides:
- Expandable/collapsible container
- Chat creation button (when not yet created)
- Text input with send button (when chat exists)
- Cancel execution button (when chat stage is in progress)
- Processing indicator (when sending or processing)

**Note:** The `ChatPanel` does NOT render messages - all message rendering happens in the `ConversationTimeline` above it.

### Dashboard Sessions List - Chat Badge

Sessions with active chat show a message count badge:

```
┌──────────────────────────────────────────────────┐
│ PodCrashLoop • COMPLETED • 2 hours ago  💬 3     │
│ my-app-pod crashed in production                │
│ 4 stages • 45s duration                         │
└──────────────────────────────────────────────────┘
                                          ↑
                                    Chat active
                                    with 3 messages
```

---

## Implementation Plan

### Phase 1: Core Infrastructure

**Backend:**

1. **Database Migrations:**
   - Create `chats` table with all fields including pod tracking (`pod_id`, `last_interaction_at`)
   - Create `chat_user_messages` table with cascade delete on chat_id
   - Add composite index on Chat: `ix_chats_pod_last_interaction` (pod_id, last_interaction_at)
   - Add standard indexes: `ix_chats_session_id`, `ix_chats_created_at`
   - Add indexes on ChatUserMessage: `ix_chat_user_messages_chat_id`, `ix_chat_user_messages_created_at`
   - Migration for adding `chat_id` and `chat_user_message_id` fields to `StageExecution` table

2. **Data Model Classes:**
   - Create `Chat` SQLModel (already defined in document)
   - Create `ChatUserMessage` SQLModel (already defined in document)
   - Create `ChatMessageContext` dataclass (for StageContext.chat_context)
   - Create `SessionContextData` dataclass (for context capture return type)
   - Modify `ChainContext` to add optional `chat_context: Optional[ChatMessageContext]` field
   - Modify `StageExecution` to add `chat_id` and `chat_user_message_id` fields

3. **Extend `HistoryRepository`** with chat database operations:
   - CRUD: `create_chat()`, `get_chat_by_id()`, `get_chat_by_session()`
   - **Update**: `update_chat()` - Required for orphan cleanup and pod tracking
   - Messages: `create_chat_user_message()`, `get_chat_user_messages()`
   - Executions: `get_stage_executions_for_chat()`
   - Pod tracking: `update_chat_pod_tracking()`, `find_chats_by_pod()`, `find_orphaned_chats()`

4. **Extend `HistoryService`** with chat operations (delegates to HistoryRepository):
   - Chat CRUD: `create_chat()`, `get_chat_by_id()`, `get_chat_by_session()`
   - Message operations: `create_chat_user_message()`
   - Execution queries: `get_stage_executions_for_chat()`
   - Pod tracking: `start_chat_message_processing()`, `record_chat_interaction()`
   - Cleanup: `cleanup_orphaned_chats()`, `mark_pod_chats_interrupted()`

5. **Extend `HistoryCleanupService`:**
   - Add `_cleanup_orphaned_chats()` method to cleanup loop
   - Call `history_service.cleanup_orphaned_chats()` with same timeout as sessions

6. **Update `main.py` graceful shutdown:**
   - Add `active_chat_tasks: Dict[str, asyncio.Task]` global dictionary
   - Rename `mark_active_sessions_as_interrupted()` to `mark_active_tasks_as_interrupted()`
   - Extend interrupt function to call `history_service.mark_pod_chats_interrupted()`
   - Update lifespan shutdown to combine `active_tasks` and `active_chat_tasks` when waiting

7. **Configuration:**
   - Add `chat_enabled: bool = True` field to `ChainConfigModel` in agent_config.py

8. **Agent Factory:**
   - Register `ChatAgent` as a built-in agent in `AgentFactory`
   - Ensure `create_agent()` can instantiate ChatAgent with proper dependencies (llm_client, mcp_client, mcp_registry)

9. **Create `ChatAgent` built-in agent:**
   - Implement in `backend/tarsy/agents/builtin/chat_agent.py`
   - Set `iteration_strategy=IterationStrategy.REACT`
   - Return empty list from `mcp_servers()` (uses dynamic MCP from context)
   - Implement `custom_instructions()` with ReAct-style chat instructions

10. **Implement `ChatService`:**
    - Create `backend/tarsy/services/chat_service.py`
    - Implement `create_chat()` with session validation and context capture
    - Implement `send_message()` with full lifecycle management (pod tracking, timeouts, MCP cleanup)
    - Implement context helpers: `_capture_session_context()`, `_build_message_context()`, `_get_formatted_conversation_from_llm_interactions()`
    - Implement stage execution lifecycle: `_update_stage_execution_started()`, `_update_stage_execution_completed()`, `_update_stage_execution_failed()`

### Phase 2: Chat Agent & Tool Execution

**Backend:**

1. **Context Helper Functions:**
   - Implement `format_conversation_history_as_text(conversation: LLMConversation) -> str`
   - Location: `backend/tarsy/services/chat_service.py` or `backend/tarsy/utils/chat_utils.py`
   - Extracts user/assistant messages, skips system messages, formats with clear section markers

2. **MCP Selection Logic:**
   - Implement `_determine_mcp_selection_from_session()` in ChatService
   - Handle custom MCP selection (from session.mcp_selection)
   - Handle default MCP servers (extract from chain_definition.stages)
   - Return `MCPSelectionConfig` object

3. **Extend `PromptBuilder`** (backend/tarsy/services/prompt_builder.py):
   - Add `build_chat_user_message(conversation_history: str, user_question: str) -> str` method
   - Formats conversation history + user question with clear markers
   - Adds ReAct instructions for follow-up context

4. **Create `ChatReActController`:**
   - Location: `backend/tarsy/agents/iteration_controllers/chat_react_controller.py`
   - Extend `ReactController` class
   - Override `build_initial_conversation()` to use `ChatMessageContext` from context
   - Delegate user message construction to `PromptBuilder.build_chat_user_message()`
   - Use `get_enhanced_react_system_message()` for system message

5. **Register `ChatReActController`:**
   - Ensure it's available when ChatAgent requests `IterationStrategy.REACT`
   - May need to modify iteration strategy selection logic if ChatAgent needs special handling

6. **Wire up `ChatAgent` with `ChatReActController`:**
   - ChatAgent constructor sets `iteration_strategy=IterationStrategy.REACT`
   - Controller factory creates ChatReActController (or modify ChatAgent to use it explicitly)

7. **Extend hook system** for chat interaction recording:
   - Update `BaseAgent` hooks: `on_llm_new_token()`, `on_llm_end()`, `on_tool_start()`, `on_tool_end()`
   - Add chat_id detection (either from StageExecution query or from context)
   - Call both `record_session_interaction(session_id)` (existing) and `record_chat_interaction(chat_id)` (new)
   - Handle graceful degradation if record_chat_interaction not available

8. **WebSocket Event Types:**
   - Create `ChatCreatedEvent` class in `backend/tarsy/models/events.py`
   - Create `ChatUserMessageEvent` class
   - Register event types in event system
   - Ensure serialization/deserialization works
   - Note: AI responses use existing `LLMStreamChunkEvent` (no changes needed)

9. **Event Publishing:**
   - Publish `ChatCreatedEvent` in `ChatService.create_chat()`
   - Publish `ChatUserMessageEvent` in `ChatService.send_message()`
   - Use existing `session:{session_id}` channel (no new channels needed)

### Phase 3: API Endpoints

**Backend:**

1. **Create Chat Controller** (`backend/tarsy/controllers/chat_controller.py`):
   - Implement all REST endpoints
   - Inject ChatService, HistoryService dependencies

2. **Implement REST Endpoints:**
   - `POST /api/v1/sessions/{session_id}/chat`
     - Create new chat for terminated session
     - Returns: Chat object with chat_id
     - Validates session exists and is in a terminal state (completed, failed, or cancelled)
     - Checks chain has chat_enabled=true
   
   - `GET /api/v1/chats/{chat_id}`
     - Get chat details
     - Returns: Chat object
   
   - `POST /api/v1/chats/{chat_id}/messages`
     - Send message to chat
     - Body: `{ "content": "user question", "author": "user@example.com" }`
     - Returns: Created ChatUserMessage (assistant response via WebSocket)
     - Rejects with 503 if `shutdown_in_progress=True` (like alert submission)
   
   - `GET /api/v1/chats/{chat_id}/messages`
     - Get chat message history
     - Query params: `?limit=50&offset=0`
     - Returns: List of ChatUserMessage objects (user messages only)
   
   - `GET /api/v1/sessions/{session_id}/chat-available`
     - Check if chat available for session
     - Returns: `{ "available": bool, "reason": "optional message" }`
     - Validates session status and chain configuration

3. **Authorization:**
   - Reuse existing session authorization patterns
   - Verify user has access to parent session before allowing chat operations
   - Apply same RBAC rules as session access

4. **Request Validation:**
   - Add Pydantic models for request bodies (ChatCreateRequest, ChatMessageRequest)
   - Validate message content (max length, required fields)
   - Validate chat exists and is accessible

5. **WebSocket Streaming:**
   - No changes needed - reuse existing `session:{session_id}` channel
   - Chat responses stream via existing LLM streaming events
   - Dashboard already subscribed to session channel

6. **Error Handling:**
   - Handle chat not found (404)
   - Handle session not completed (400)
   - Handle chat disabled for chain (400)
   - Handle timeout errors (timeout during message processing)
   - Handle shutdown in progress (503)

7. **Register Routes:**
   - Add chat routes to FastAPI app in `backend/tarsy/main.py`
   - Mount chat controller

### Phase 4: UI Implementation

**Frontend - Actual Implementation:**

1. **TypeScript Types** (`dashboard/src/types/` and inline):
   - ✅ `Chat` interface in API models
   - ✅ `ChatUserMessage` interface (embedded in stage execution data)
   - ✅ `ChatCreatedEvent` and `ChatUserMessageEvent` interfaces
   - ✅ `ChatFlowItemData` type for unified timeline rendering
   - ✅ API request/response types

2. **API Client** (`dashboard/src/services/chatApi.ts` and inline):
   - ✅ `createChat(sessionId: string): Promise<Chat>` - creates chat for session
   - ✅ `sendMessage(chatId: string, content: string): Promise<...>` - sends user message
   - ✅ `checkChatAvailable(sessionId: string)` - checks if chat is available
   - Note: Chat messages fetched as part of session detail (not separate endpoint)

3. **State Management** (`dashboard/src/hooks/useChatState.ts`):
   - ✅ Custom hook for managing chat state
   - ✅ Handles chat creation, message sending, loading states
   - ✅ Integrates with session WebSocket for real-time updates
   - ✅ Error handling and retry logic

4. **WebSocket Integration:**
   - ✅ Extended session WebSocket subscription to handle chat events
   - ✅ Handles `chat.created`, `chat.user_message` events (though user messages come via stage.started)
   - ✅ Reuses existing LLM streaming handlers via stage_execution_id
   - ✅ User messages streamed in `stage.started` events with chat metadata

5. **Chat Components - Unified Timeline Approach:**

   **a. ConversationTimeline Component** (`dashboard/src/components/ConversationTimeline.tsx`):
   - ✅ **KEY CHANGE:** Renders ALL messages including chat messages in unified timeline
   - ✅ Uses `chatFlowParser.ts` to extract user messages from stage executions
   - ✅ Displays user messages inline with investigation stages
   - ✅ Handles streaming updates for both investigation and chat stages
   - ✅ Shows processing indicator during chat message processing
   
   **b. ChatFlowItem Component** (`dashboard/src/components/ChatFlowItem.tsx`):
   - ✅ Renders all flow item types: thoughts, tool calls, final answers, **user messages**
   - ✅ User messages shown with avatar icon and grey background box
   - ✅ Consistent styling across all message types
   - ✅ Supports markdown in final answers
   
   **c. ChatPanel Component** (`dashboard/src/components/Chat/ChatPanel.tsx`):
   - ✅ Collapsible container for chat input (NOT for message display)
   - ✅ Shows "Start Chat" button when no chat exists
   - ✅ Shows text input with send/cancel buttons when chat active
   - ✅ Processing indicator during message sending
   - ✅ Auto-collapses Final Analysis when expanded
   
   **d. ChatInput Component** (`dashboard/src/components/Chat/ChatInput.tsx`):
   - ✅ Text input with send button
   - ✅ Shift+Enter for new line, Enter to send
   - ✅ Disabled during streaming
   - ✅ Cancel execution button when processing
   
   **e. ChatMessageList, ChatUserMessage, ChatAssistantMessage Components:**
   - ⚠️ Created but NOT USED in actual implementation
   - Messages displayed in ConversationTimeline instead
   - Kept in codebase for potential future use

6. **Utilities:**
   - ✅ `chatFlowParser.ts` - Parses session into unified chat flow including user messages
   - ✅ `conversationParser.ts` - Extracts ReAct patterns from LLM interactions
   - ✅ `reactParser.ts` - Parses thoughts, actions, and final answers
   - ✅ Integration with existing markdown rendering

7. **Session Detail Page Integration** (`SessionDetailPageBase.tsx`):
   - ✅ ChatPanel shown at bottom for terminal sessions (completed/failed/cancelled)
   - ✅ Uses `isTerminalSessionStatus()` helper for visibility logic
   - ✅ Auto-collapse Final Analysis when chat is expanded
   - ✅ "Jump to Chat" button to quickly access chat input
   - ✅ Chat messages appear inline in Reasoning tab timeline

8. **Sessions List Integration:**
   - ✅ Chat badge indicator (💬 with count) shown for sessions with chat
   - ✅ Real-time updates when chat events received
   - ✅ Visual indication of active conversations

9. **UI Polish:**
   - ✅ Processing indicator during streaming
   - ✅ Collapsible sections for focused reading
   - ✅ Expandable/collapsible tool call results
   - ✅ Markdown rendering in final answers
   - ✅ Multi-user attribution with author names
   - ✅ Smooth scrolling to chat input
   - ✅ Error states with retry capability

10. **Key Benefits of Implementation Approach:**
    - **Unified View:** All investigation activity in single chronological timeline
    - **Consistent UX:** Chat uses same rendering as investigation stages
    - **Simpler Code:** Reuses existing timeline infrastructure
    - **Better Context:** User questions appear inline with agent responses
