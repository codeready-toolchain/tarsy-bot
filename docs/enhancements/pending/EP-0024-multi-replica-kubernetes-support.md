# EP-0024: Multi-Replica Kubernetes Support

## Problem Statement

TARSy is not currently safe to run as a multi-replica Kubernetes deployment due to reliance on in-memory state, local file systems, and lack of cross-pod coordination. Running multiple replicas would result in duplicate alert processing, incomplete dashboard updates, scattered logs, and data inconsistencies.

**Note:** This EP covers production multi-replica deployments with PostgreSQL. SQLite is development-only and does not require HA support.

## Related Enhancements

- **EP-0025**: PostgreSQL LISTEN/NOTIFY Eventing System - Solves cross-pod event distribution for dashboard updates, session tracking, and real-time notifications

## Issues Identified

Issues are marked with their resolution approach:
- **[SOLVED BY EP-0025]** - Addressed by eventing system
- **[SEPARATE]** - Requires independent solution
- **[REMOVED]** - Removed by design decision (simpler approach chosen)

### Critical Issues

#### 1. Alert Deduplication State **[REMOVED]**
**Location:** `backend/tarsy/controllers/alert_controller.py:28-29`

In-memory dictionary `processing_alert_keys` is maintained per-pod. Same alert hitting different replicas would be processed multiple times.

**Design Decision - Deduplication Removed:**

After analysis, we've decided to **completely remove deduplication logic** instead of implementing distributed locking. Rationale:

1. **Current deduplication is ineffective** - In-memory per-pod state doesn't work for multi-replica
2. **Distributed locks add complexity and failure modes** - Lock timeouts, pod crashes leaving locks stuck, additional infrastructure
3. **Simpler is better** - Less code, fewer failure modes, easier to reason about

**Additional Simplification - Complete Removal of alert_id:**

Along with removing deduplication, we're completely eliminating the `alert_id` concept:
- **Before:** POST `/alerts` returns `alert_id` → client polls `/session-id/{alert_id}` → gets `session_id`
- **After:** POST `/alerts` returns `session_id` immediately (generated before response)
- **Result:** Single identifier (`session_id`) used throughout the entire system - API, database, dashboard, events

**What's being removed:**
- ❌ `alert_id` field from database schema
- ❌ `alert_id` parameter from all function signatures
- ❌ `alert_id` from API responses
- ❌ `/session-id/{alert_id}` endpoint
- ❌ In-memory `alert_session_mapping` cache
- ❌ In-memory `processing_alert_keys` deduplication

**What remains:**
- ✅ Single `session_id` (UUID) as the universal identifier
- ✅ Simpler API, simpler database schema, simpler code

#### 2. WebSocket Connection Management **[SOLVED BY EP-0025]**
**Location:** `backend/tarsy/services/dashboard_connection_manager.py:26-32`

WebSocket connections stored in-memory per pod. Dashboard clients connected to Pod A won't receive updates for alerts processed by Pod B.

**Solution:**
- ✅ Implement PostgreSQL LISTEN/NOTIFY for cross-pod event distribution
- ✅ WebSocket connections with channel subscriptions for real-time updates
- ✅ Events published by any pod are broadcast to all pods via database
- ✅ Each pod forwards events to its connected WebSocket clients
- ✅ Single WebSocket connection per tab with multiple channel subscriptions
- See **EP-0025** for complete implementation details

### Medium Severity Issues

#### 3. Local File System Logging **[SEPARATE]**
**Location:** `backend/tarsy/utils/logger.py:11-66`

Each replica writes to its own local logs directory, making debugging and monitoring difficult.

**Solution:**
- Drop file logging completely (for all environments)
- Ensure stdout/stderr logging covers all log levels and categories
- Use Kubernetes log aggregation (kubectl logs, Loki, CloudWatch, ELK)
- Simpler configuration, follows Kubernetes best practices

#### 4. Orphaned Session Cleanup & Graceful Shutdown **[SEPARATE]**
**Location:** `backend/tarsy/main.py:68-78`

Orphaned sessions from crashed pods need to be detected and marked as failed. Additionally, gracefully handle pod shutdown to prevent data loss.

**Solution - Hybrid Approach:**
1. **Track `last_interaction_at`** - Update on every LLM call, MCP tool call, stage transition
2. **Graceful shutdown hook** - Mark in-progress sessions as "interrupted" when pod shuts down (SIGTERM)
3. **Startup recovery** - On pod startup, find and mark orphaned sessions as "failed"

**Implementation:**
- No periodic cleanup tasks needed
- Orphaned sessions detected immediately when new pods start
- Integrates with EP-0025 to publish `session.failed` events
- Fast recovery after crashes (< 30s depending on pod restart time)
- Set `terminationGracePeriodSeconds: 60` in pod spec

#### 5. Dashboard Message Buffering **[SOLVED BY EP-0025]**
**Location:** `backend/tarsy/services/dashboard_broadcaster.py:36-74`

Session message buffers stored in-memory per pod. Messages may be lost if alert processing and dashboard connection are on different pods.

**Solution:**
- ✅ Events persisted to database (not just in-memory)
- ✅ WebSocket clients receive events via PostgreSQL LISTEN/NOTIFY
- ✅ Event table provides catchup mechanism for missed messages
- ✅ No separate buffering layer needed
- See **EP-0025** for event persistence and delivery mechanism

### Low Severity Issues

#### 6. Active Session Tracking **[SOLVED BY EP-0025]**
**Location:** `backend/tarsy/services/dashboard_update_service.py:65-75`

Dashboard service tracks active sessions per pod. Metrics are incomplete across cluster.

**Solution:**
- ✅ Session lifecycle events published to `sessions` channel
- ✅ Events: `session.created`, `session.started`, `session.completed`, `session.failed`
- ✅ All pods receive events and can track active sessions
- ✅ Database remains source of truth for consistency
- ✅ Dashboard derives active count from real-time events
- See **EP-0025** Event Channels section

### Infrastructure Concerns

#### 7. Health Check Enhancement **[SEPARATE]**
Current `/health` endpoint already checks database connectivity but always returns HTTP 200.

**Current Status:**
- ✅ Database connectivity check already implemented (`SELECT 1` query)
- ✅ Degraded status on database failure already implemented
- ✅ System warnings already integrated
- ❌ Always returns HTTP 200 (even when degraded/unhealthy)

**Additional Work Needed:**
- Return HTTP 503 when status is "degraded" or "unhealthy" (for Kubernetes readiness/liveness probes)
- Add event system status check (PostgreSQL LISTEN connection health)
- Event system check will be implemented as part of EP-0025

## Summary

### Issues Solved by EP-0025 (3 of 7)
- ✅ **Issue #2**: WebSocket Connection Management - Replaced with SSE + PostgreSQL LISTEN/NOTIFY
- ✅ **Issue #5**: Dashboard Message Buffering - Events persisted to database with catchup support
- ✅ **Issue #6**: Active Session Tracking - Session lifecycle events broadcast to all pods

### Issues Requiring Separate Implementation (3 of 7)
- **Issue #3**: Logging - Drop file logging, stdout/stderr only
- **Issue #4**: Orphaned Session Cleanup & Graceful Shutdown - Hybrid approach (startup recovery + graceful shutdown hook)
- **Issue #7**: Health Check Enhancement - Add event system status + HTTP 503 for degraded state

### Issues Removed by Design Decision (1 of 7)
- ❌ **Issue #1**: Alert Deduplication - Removed entirely (simpler approach, session_id as primary identifier)

## Design

### Phase 1: Event Distribution (Implemented by EP-0025)

EP-0025 provides the foundation for multi-replica support by solving cross-pod communication:

1. **PostgreSQL LISTEN/NOTIFY** - Real-time event broadcast to all pods
2. **Event Persistence** - Events stored in database for reliability and catchup
3. **SQLite Polling Fallback** - Development mode without PostgreSQL
4. **Two-Channel Architecture**:
   - `sessions` - Global session lifecycle events
   - `session:{id}` - Per-session detailed events
5. **Event Cleanup** - Automatic cleanup of old events

**Result:** Dashboard clients receive updates regardless of which pod processes the alert.

### Phase 2: Simplified Alert Submission (Issue #1 - Removed)

Instead of implementing distributed locking for deduplication, we've simplified the entire alert submission flow:

**Changes:**
1. Remove `alert_id` field from database schema entirely
2. Remove in-memory `processing_alert_keys` deduplication dictionary
3. Remove in-memory `alert_session_mapping` (TTLCache)
4. Remove in-memory `valid_alert_ids` (TTLCache)
5. Remove `/session-id/{alert_id}` polling endpoint
6. Return `session_id` directly in alert submission response
7. Use `session_id` as the sole identifier throughout the system

**New Alert Submission Flow:**

```python
@router.post("/alerts", response_model=AlertResponse)
async def submit_alert(request: Request) -> AlertResponse:
    """Submit a new alert for processing."""
    # ... validation code ...
    
    # Generate session_id BEFORE starting background processing
    session_id = str(uuid.uuid4())
    
    # Create ChainContext for processing  
    alert_context = ChainContext.from_processing_alert(
        processing_alert=processing_alert,
        session_id=session_id,
        current_stage_name="initializing"
    )
    
    # Start background processing
    asyncio.create_task(process_alert_background(session_id, alert_context))
    
    logger.info(f"Alert submitted with session_id: {session_id}")
    
    # Return session_id immediately - client can use it right away
    return AlertResponse(
        session_id=session_id,
        status="queued",
        message="Alert submitted for processing"
    )
```

**Updated Response Model:**

```python
class AlertResponse(BaseModel):
    """Response model for alert submission."""
    session_id: str  # Single universal identifier
    status: str
    message: str
```

**Database Schema Changes:**

A database migration will remove the `alert_id` column from the sessions table. The `session_id` (UUID) becomes the sole identifier.

**Client Integration:**

```typescript
// Dashboard client - single step, no polling needed
const response = await fetch('/api/v1/alerts', {
    method: 'POST',
    body: JSON.stringify(alertData)
});

const { session_id } = await response.json();

// Immediately subscribe to session updates using SSE
const eventSource = new EventSource(`/api/v1/events/subscribe?channels=session:${session_id}`);
```

### Phase 3: Deployment Infrastructure

**3.1 Logging (Issue #3)**

Remove file logging, use stdout/stderr only:

```python
# backend/tarsy/utils/logger.py

def setup_logging():
    """Configure logging to stdout/stderr only"""
    
    # Root logger configuration
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler()  # stdout/stderr only
        ]
    )
    
    # Set levels for specific loggers
    logging.getLogger('tarsy').setLevel(logging.DEBUG)
    logging.getLogger('uvicorn').setLevel(logging.INFO)
    
    # Remove any file handlers if present
    for handler in logging.root.handlers[:]:
        if isinstance(handler, logging.FileHandler):
            logging.root.removeHandler(handler)
```

**3.2 Session Cleanup (Issue #4)**

Hybrid approach combining startup recovery and graceful shutdown:

**Implementation follows proper layering:**

**Layer 1: Repository (backend/tarsy/repositories/history_repository.py)**
```python
from tarsy.models.constants import AlertSessionStatus

class HistoryRepository:
    """Repository for alert processing history data operations."""
    
    def find_orphaned_sessions(self, timeout_threshold_us: int) -> List[AlertSession]:
        """Find sessions that appear orphaned based on last interaction time."""
        statement = select(AlertSession).where(
            AlertSession.status == AlertSessionStatus.IN_PROGRESS.value,
            AlertSession.last_interaction_at < timeout_threshold_us
        )
        return self.session.exec(statement).all()
    
    def find_sessions_by_pod(self, pod_id: str, status: str = AlertSessionStatus.IN_PROGRESS.value) -> List[AlertSession]:
        """Find sessions being processed by a specific pod."""
        statement = select(AlertSession).where(
            AlertSession.status == status,
            AlertSession.pod_id == pod_id
        )
        return self.session.exec(statement).all()
    
    def update_session_pod_tracking(
        self, 
        session_id: str, 
        pod_id: str, 
        status: str = AlertSessionStatus.IN_PROGRESS.value
    ) -> bool:
        """Update session with pod tracking information."""
        session = self.get_alert_session(session_id)
        if not session:
            return False
        
        session.status = status
        session.pod_id = pod_id
        session.last_interaction_at = now_us()
        return self.update_alert_session(session)
```

**Layer 2: Service (backend/tarsy/services/history_service.py)**
```python
from tarsy.models.constants import AlertSessionStatus

class HistoryService:
    """Service for alert processing history management."""
    
    def cleanup_orphaned_sessions(self, timeout_minutes: int = 30) -> int:
        """
        Find and mark orphaned sessions as failed based on inactivity timeout.
        
        Replaces the existing simple cleanup_orphaned_sessions() method with
        timeout-based detection. An orphaned session is one that:
        - Is in 'in_progress' status
        - Has not had any interaction for longer than timeout_minutes
        
        This handles cases where:
        - Pod crashed without graceful shutdown
        - Session is stuck/hung without activity
        
        Args:
            timeout_minutes: Mark sessions inactive for this long as failed (default: 30)
        
        Returns:
            Number of sessions marked as failed
        """
        if not self.is_enabled:
            return 0
        
        def _cleanup_operation():
            with self.get_repository() as repo:
                if not repo:
                    return 0
                
                timeout_threshold_us = now_us() - (timeout_minutes * 60 * 1_000_000)
                orphaned_sessions = repo.find_orphaned_sessions(timeout_threshold_us)
                
                for session_record in orphaned_sessions:
                    session_record.status = AlertSessionStatus.FAILED.value
                    session_record.error_message = (
                        'Processing failed - session became unresponsive. '
                        'This may be due to pod crash, restart, or timeout during processing.'
                    )
                    session_record.completed_at_us = now_us()
                    repo.update_alert_session(session_record)
                
                return len(orphaned_sessions)
        
        count = self._retry_database_operation("cleanup_orphaned_sessions", _cleanup_operation)
        
        if count and count > 0:
            logger.info(f"Cleaned up {count} orphaned sessions during startup")
        
        return count or 0
    
    async def mark_pod_sessions_interrupted(self, pod_id: str) -> int:
        """
        Mark sessions being processed by a pod as failed during graceful shutdown.
        Sets descriptive error_message to distinguish from other failure types.
        
        Returns:
            Number of sessions marked as failed
        """
        if not self.is_enabled:
            return 0
        
        def _interrupt_operation():
            with self.get_repository() as repo:
                if not repo:
                    return 0
                
                in_progress_sessions = repo.find_sessions_by_pod(
                    pod_id, 
                    AlertSessionStatus.IN_PROGRESS.value
                )
                
                for session_record in in_progress_sessions:
                    session_record.status = AlertSessionStatus.FAILED.value
                    session_record.error_message = f"Session interrupted during pod '{pod_id}' graceful shutdown"
                    session_record.completed_at_us = now_us()
                    repo.update_alert_session(session_record)
                
                return len(in_progress_sessions)
        
        count = self._retry_database_operation("mark_interrupted_sessions", _interrupt_operation)
        
        if count and count > 0:
            logger.info(f"Marked {count} sessions as failed (interrupted) for pod {pod_id}")
        
        return count or 0
    
    async def start_session_processing(self, session_id: str, pod_id: str) -> bool:
        """
        Mark session as being processed by a specific pod.
        Updates status, pod_id, and last_interaction_at.
        """
        if not self.is_enabled:
            return False
        
        def _start_operation():
            with self.get_repository() as repo:
                if not repo:
                    return False
                return repo.update_session_pod_tracking(
                    session_id, 
                    pod_id, 
                    AlertSessionStatus.IN_PROGRESS.value
                )
        
        return self._retry_database_operation("start_session_processing", _start_operation) or False
    
    async def record_session_interaction(self, session_id: str) -> bool:
        """Update session last_interaction_at timestamp."""
        if not self.is_enabled:
            return False
        
        def _interaction_operation():
            with self.get_repository() as repo:
                if not repo:
                    return False
                
                session = repo.get_alert_session(session_id)
                if not session:
                    return False
                
                session.last_interaction_at = now_us()
                return repo.update_alert_session(session)
        
        return self._retry_database_operation("record_interaction", _interaction_operation) or False
```

**Layer 3: Application Lifecycle (backend/tarsy/main.py)**
```python
import os
from contextlib import asynccontextmanager
from tarsy.services.history_service import get_history_service

SESSION_TIMEOUT_MINUTES = 30

def get_pod_id() -> str:
    """
    Get the current pod/instance identifier from environment.
    
    Returns:
        Pod identifier from TARSY_POD_ID environment variable, or "unknown" if not set.
        In multi-replica deployments, this should be set to the pod name.
    """
    return os.environ.get("TARSY_POD_ID", "unknown")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown"""
    
    # Startup: Clean up orphaned sessions from previous pod crashes
    history_service = get_history_service()
    if history_service and history_service.is_enabled:
        cleaned_sessions = history_service.cleanup_orphaned_sessions(SESSION_TIMEOUT_MINUTES)
        if cleaned_sessions > 0:
            logger.info(f"Startup cleanup: marked {cleaned_sessions} orphaned sessions as failed")
    
    yield  # Application runs
    
    # Shutdown: Mark in-progress sessions as interrupted for graceful shutdown
    if history_service and history_service.is_enabled:
        pod_id = get_pod_id()
        await history_service.mark_pod_sessions_interrupted(pod_id)
```

**Layer 4: Alert Processing Integration (backend/tarsy/services/alert_service.py)**
```python
from tarsy.models.constants import AlertSessionStatus
from tarsy.main import get_pod_id

class AlertService:
    """Service for alert processing."""
    
    async def process_alert(self, chain_context: ChainContext, alert_id: str) -> str:
        """Process an alert by delegating to appropriate agent."""
        
        # ... existing processing logic ...
        
        # Create history session
        session_created = self._create_chain_history_session(chain_context, chain_definition)
        
        # Mark session as being processed by this pod
        if session_created and self.history_service:
            pod_id = get_pod_id()
            
            if pod_id == "unknown":
                logger.warning(
                    "TARSY_POD_ID not set - all pods will share pod_id='unknown'. "
                    "This breaks graceful shutdown in multi-replica deployments. "
                    "Set TARSY_POD_ID in Kubernetes pod spec."
                )
            
            await self.history_service.start_session_processing(
                chain_context.session_id, 
                pod_id
            )
        
        # ... continue with chain execution ...
```

**Model changes (backend/tarsy/models/db_models.py):**

Add new fields to `AlertSession` model:
```python
class AlertSession(SQLModel, table=True):
    """Represents an alert processing session with complete lifecycle tracking."""
    
    __tablename__ = "alert_sessions"
    
    __table_args__ = (
        # Existing indexes...
        Index('ix_alert_sessions_status', 'status'),
        Index('ix_alert_sessions_agent_type', 'agent_type'), 
        Index('ix_alert_sessions_alert_type', 'alert_type'),
        Index('ix_alert_sessions_status_started_at', 'status', 'started_at_us'),
        
        # NEW: Composite index for efficient orphan detection
        Index('ix_alert_sessions_status_last_interaction', 'status', 'last_interaction_at'),
    )
    
    # Existing fields...
    session_id: str = Field(primary_key=True, ...)
    alert_id: str = Field(unique=True, ...)
    # ... other existing fields ...
    
    # NEW: Pod tracking fields
    pod_id: Optional[str] = Field(
        default=None,
        description="Kubernetes pod identifier for multi-replica session tracking"
    )
    
    last_interaction_at: Optional[int] = Field(
        default=None,
        sa_column=Column(BIGINT),
        description="Last interaction timestamp (microseconds) for orphan detection"
    )
```

**Migration process:**

1. Add fields and index to the model (as shown above)
2. Generate migration: `make db-migration msg="add pod tracking for multi-replica support"`
3. Adjust auto-generated migration to add backfill logic

**Example migration (auto-generated, then adjusted with backfill):**
```python
def upgrade() -> None:
    """Add pod tracking columns for multi-replica support."""
    # These columns are auto-generated from model definition
    op.add_column('alert_sessions', sa.Column('pod_id', sa.String(255), nullable=True))
    op.add_column('alert_sessions', sa.Column('last_interaction_at', sa.BIGINT, nullable=True))
    
    # Backfill pod_id for existing rows (historical sessions get "unknown")
    op.execute("UPDATE alert_sessions SET pod_id = 'unknown' WHERE pod_id IS NULL")
    
    # Backfill last_interaction_at for existing rows
    op.execute('UPDATE alert_sessions SET last_interaction_at = started_at_us WHERE last_interaction_at IS NULL')
    
    # Index is auto-generated from __table_args__
    op.create_index('ix_alert_sessions_status_last_interaction', 'alert_sessions', ['status', 'last_interaction_at'])
```

**Migration considerations:**
- Add fields and index to model first (single source of truth)
- Run `make db-migration` to auto-generate migration
- Add backfill logic to the generated migration
- `pod_id` backfilled to `"unknown"` for historical sessions
- `last_interaction_at` backfilled to `started_at_us` for existing rows
- After migration, `pod_id` is always a string (never NULL)

**Failure Type Differentiation:**

Sessions are marked as `FAILED` with descriptive `error_message` to distinguish different failure scenarios:

```python
# Graceful shutdown (user-friendly)
error_message = "Session interrupted during pod 'tarsy-5d8f7b-xyz' graceful shutdown"

# Pod crash or timeout (user-friendly, explains what happened)
error_message = (
    "Processing failed - session became unresponsive. "
    "This may be due to pod crash, restart, or timeout during processing."
)

# Stage failure
error_message = "Chain execution failed: stage X failed"

# LLM/provider errors
error_message = "LLM Response Error - provider timeout"
```

This approach:
- ✅ No dashboard changes required (already displays error_message)
- ✅ Searchable via existing text search: `search="graceful shutdown"` or `search="unresponsive"`
- ✅ Clear audit trail in error_message field
- ✅ User-friendly messages that explain what happened
- ✅ Maintains backwards compatibility

**Pod ID Handling:**

The `pod_id` field uses string values consistently:
- **Configured pods:** Store actual pod name (e.g., `"tarsy-5d8f7b-xyz"`)
- **Unconfigured pods:** Store `"unknown"` when TARSY_POD_ID not set
- **Historical sessions:** Backfilled to `"unknown"` during migration

After migration, `pod_id` is never NULL - always a string. This simplifies queries and ensures graceful shutdown only affects sessions from the shutting-down pod:
```python
# Simple equality checks - no NULL handling needed
find_sessions_by_pod(pod_id="unknown")  # All unconfigured sessions
find_sessions_by_pod(pod_id="tarsy-5d8f7b-xyz")  # Specific pod's sessions
```

**Session Interaction Tracking Integration Points:**

For timeout-based orphan detection to work correctly, `record_session_interaction()` must be called regularly during active processing. This ensures `last_interaction_at` stays current, allowing the system to distinguish between:
- **Active sessions** (recent interaction) - kept running
- **Stuck/crashed sessions** (no interaction for 30+ minutes) - marked as failed

**Integration locations:**

1. **LLM Interactions** (backend/tarsy/hooks/history_hooks.py)
   ```python
   async def on_llm_call_complete(self, context: LLMHookContext) -> None:
       """Hook called after LLM call completes."""
       if not self.history_service:
           return
           
       session_id = context.session_id
       
       # Store the interaction
       await self.history_service.store_llm_interaction(interaction)
       
       # NEW: Update last interaction timestamp
       await self.history_service.record_session_interaction(session_id)
   ```

2. **MCP Tool Calls** (backend/tarsy/hooks/history_hooks.py)
   ```python
   async def on_mcp_tool_complete(self, context: MCPHookContext) -> None:
       """Hook called after MCP tool call completes."""
       if not self.history_service:
           return
           
       session_id = context.session_id
       
       # Store the communication
       await self.history_service.store_mcp_communication(interaction)
       
       # NEW: Update last interaction timestamp
       await self.history_service.record_session_interaction(session_id)
   ```

3. **Stage Transitions** (backend/tarsy/services/alert_service.py)
   ```python
   async def _execute_chain(self, chain_context: ChainContext, chain_definition: ChainConfigModel):
       """Execute a chain of stages."""
       
       for stage_index, stage_config in enumerate(chain_definition.stages):
           # Update current stage
           await self._update_session_current_stage(
               chain_context.session_id, 
               stage_index, 
               stage_execution_id
           )
           
           # NEW: Record stage transition as interaction
           if self.history_service:
               await self.history_service.record_session_interaction(
                   chain_context.session_id
               )
           
           # Execute stage...
   ```

4. **Session Start** - Already handled by `start_session_processing()` which updates `last_interaction_at` via `update_session_pod_tracking()`

**Why this matters:**
- Without regular updates, a legitimately active 40-minute session would be marked as orphaned with a 30-minute timeout
- With proper updates, only truly stuck/crashed sessions get cleaned up
- The timeout becomes meaningful: "no activity for X minutes" vs "session older than X minutes"

**3.3 Health Check Enhancement (Issue #7)**

Improve health check endpoint with proper HTTP status codes for Kubernetes readiness/liveness probes.

**Changes to backend/tarsy/main.py:**

```python
from fastapi import Response, status as http_status
from tarsy.models.constants import SystemHealthStatus

@app.get("/health")
async def health_check(response: Response) -> Dict[str, Any]:
    """
    Comprehensive health check endpoint for Kubernetes probes.
    
    Returns:
        - HTTP 200: All critical systems healthy
        - HTTP 503: Critical system degraded/unhealthy (Kubernetes will restart pod)
    """
    try:
        # Get basic service status
        health_status = {
            "status": SystemHealthStatus.HEALTHY.value,
            "service": "tarsy",
            "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        }
        
        # Check history service / database
        db_info = get_database_info()
        history_status = "disabled"
        if db_info.get("enabled"):
            if db_info.get("connection_test"):
                history_status = SystemHealthStatus.HEALTHY.value
            else:
                history_status = SystemHealthStatus.UNHEALTHY.value
                health_status["status"] = SystemHealthStatus.DEGRADED.value
        
        # Check event system (NEW: improved with PostgreSQL connection check)
        event_system_status = "unknown"
        event_listener_type = "unknown"
        try:
            from tarsy.services.events.manager import get_event_system
            from tarsy.services.events.postgresql_listener import PostgreSQLEventListener
            
            event_system = get_event_system()
            event_listener = event_system.get_listener() if event_system else None
            
            if event_listener is None:
                event_system_status = "not_initialized"
                event_listener_type = "none"
            elif isinstance(event_listener, PostgreSQLEventListener):
                # Check both running flag AND PostgreSQL connection
                listener_conn = event_listener.listener_conn
                conn_healthy = (
                    listener_conn is not None and
                    not listener_conn.is_closed()  # asyncpg connection check
                )
                if event_listener.running and conn_healthy:
                    event_system_status = SystemHealthStatus.HEALTHY.value
                else:
                    event_system_status = SystemHealthStatus.DEGRADED.value
                    health_status["status"] = SystemHealthStatus.DEGRADED.value
                event_listener_type = "PostgreSQLEventListener"
            else:
                # SQLite or other listener - just check running flag
                if event_listener.running:
                    event_system_status = SystemHealthStatus.HEALTHY.value
                else:
                    event_system_status = SystemHealthStatus.DEGRADED.value
                    health_status["status"] = SystemHealthStatus.DEGRADED.value
                event_listener_type = event_listener.__class__.__name__
                
        except RuntimeError:
            event_system_status = "not_initialized"
        except Exception as e:
            logger.debug(f"Error getting event system status: {e}")
            event_system_status = "error"
        
        # Build services status
        health_status["services"] = {
            "alert_processing": SystemHealthStatus.HEALTHY.value,
            "history_service": history_status,
            "event_system": {
                "status": event_system_status,
                "type": event_listener_type
            },
            "database": {
                "enabled": db_info.get("enabled", False),
                "connected": db_info.get("connection_test", False) if db_info.get("enabled") else None,
                "retention_days": db_info.get("retention_days") if db_info.get("enabled") else None
            }
        }
        
        # Check system warnings
        from tarsy.services.system_warnings_service import get_warnings_service
        warnings_service = get_warnings_service()
        warnings = warnings_service.get_warnings()
        
        if warnings:
            health_status["warnings"] = [
                {
                    "category": w.category,
                    "message": w.message,
                    "timestamp": w.timestamp
                }
                for w in warnings
            ]
            health_status["warning_count"] = len(warnings)
            
            # Warnings indicate degraded state
            if health_status["status"] == SystemHealthStatus.HEALTHY.value:
                health_status["status"] = SystemHealthStatus.DEGRADED.value
        else:
            health_status["warnings"] = []
            health_status["warning_count"] = 0
        
        # NEW: Return HTTP 503 for degraded/unhealthy status
        # This tells Kubernetes probes the pod is not ready
        if health_status["status"] in (SystemHealthStatus.DEGRADED.value, SystemHealthStatus.UNHEALTHY.value):
            response.status_code = http_status.HTTP_503_SERVICE_UNAVAILABLE
        
        return health_status
        
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        # Critical failure - return 503
        response.status_code = http_status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": SystemHealthStatus.UNHEALTHY.value,
            "service": "tarsy",
            "error": str(e)
        }
```

**Key improvements:**

1. **HTTP 503 support** - Kubernetes probes now properly detect unhealthy pods
2. **PostgreSQL connection health** - Checks `listener_conn.is_closed()` not just `running` flag
3. **Better error handling** - Returns 503 on exception (tells Kubernetes to restart)
4. **Maintains existing structure** - Compatible with current implementation
5. **System warnings integration** - Already implemented, kept in place

**Kubernetes Probe Configuration:**
```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 30
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 5
  timeoutSeconds: 3
  failureThreshold: 2
```

**3.4 Pod Identifier Configuration (Required for Issue #4)**

Session cleanup and graceful shutdown require each pod to have a unique identifier. The `pod_id` is used to:
- Track which pod is processing which session
- Safely mark only the current pod's sessions as interrupted during shutdown
- Prevent pods from interfering with each other's sessions

**Kubernetes Deployment Configuration:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: tarsy
spec:
  replicas: 3
  template:
    spec:
      terminationGracePeriodSeconds: 60  # Allow time for graceful shutdown
      containers:
      - name: tarsy
        image: tarsy:latest
        env:
        # Required: Inject pod name as TARSY_POD_ID for session tracking
        - name: TARSY_POD_ID
          valueFrom:
            fieldRef:
              fieldPath: metadata.name
        ports:
        - containerPort: 8000
```

**Why TARSY_POD_ID is Required:**

If `TARSY_POD_ID` is not set, all pods will have `pod_id = "unknown"`:
- ✅ Session creation will still work
- ✅ Orphaned session recovery will still work (uses `last_interaction_at`, not `pod_id`)
- ❌ **Graceful shutdown will break** - Pod A shutting down could mark Pod B's sessions as failed
- ❌ **Multi-pod interference** - All pods share the same `pod_id`, defeating the purpose of pod tracking

**Validation:**

The application will log a warning on each session start if `TARSY_POD_ID` is not set:
```
WARNING: TARSY_POD_ID not set - all pods will share pod_id='unknown'. This breaks graceful shutdown in multi-replica deployments. Set TARSY_POD_ID in Kubernetes pod spec.
```

For production multi-replica deployments, `TARSY_POD_ID` **must** be set in the pod spec as shown above.

**Alternative Configuration:**

You can also set `TARSY_POD_ID` manually for non-Kubernetes deployments:
```bash
export TARSY_POD_ID="tarsy-instance-1"
```

### Phase 4: Documentation

Update documentation to cover:
- Multi-replica deployment architecture
- Event-driven cross-pod communication patterns
- Session cleanup and recovery mechanisms

