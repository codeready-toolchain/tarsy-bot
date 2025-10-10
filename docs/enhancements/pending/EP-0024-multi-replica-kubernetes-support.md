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
class HistoryRepository:
    """Repository for alert processing history data operations."""
    
    def find_orphaned_sessions(self, timeout_threshold_us: int) -> List[AlertSession]:
        """Find sessions that appear orphaned based on last interaction time."""
        statement = select(AlertSession).where(
            AlertSession.status.in_(['processing', 'interrupted']),
            AlertSession.last_interaction_at < timeout_threshold_us
        )
        return self.session.exec(statement).all()
    
    def find_sessions_by_pod(self, pod_id: str, status: str = 'processing') -> List[AlertSession]:
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
        status: str = 'processing'
    ) -> bool:
        """Update session with pod tracking information."""
        session = self.get_alert_session(session_id)
        if not session:
            return False
        
        session.status = status
        session.pod_id = pod_id
        session.last_interaction_at = now_us()
        return self.update_alert_session(session) is not None
```

**Layer 2: Service (backend/tarsy/services/history_service.py)**
```python
class HistoryService:
    """Service for alert processing history management."""
    
    async def recover_orphaned_sessions(self, timeout_minutes: int = 30) -> int:
        """
        Find and mark orphaned sessions on pod startup.
        
        Returns:
            Number of sessions recovered
        """
        if not self.is_enabled:
            return 0
        
        def _recovery_operation():
            with self.get_repository() as repo:
                if not repo:
                    return 0
                
                timeout_threshold_us = now_us() - (timeout_minutes * 60 * 1_000_000)
                orphaned_sessions = repo.find_orphaned_sessions(timeout_threshold_us)
                
                for session_record in orphaned_sessions:
                    session_record.status = 'failed'
                    session_record.error_message = 'Session orphaned - pod crashed or timeout'
                    session_record.completed_at_us = now_us()
                    repo.update_alert_session(session_record)
                
                return len(orphaned_sessions)
        
        count = self._retry_database_operation("recover_orphaned_sessions", _recovery_operation)
        
        # Publish events (outside transaction)
        if count and count > 0:
            logger.info(f"Recovered {count} orphaned sessions")
            # Event publishing happens via existing session lifecycle events
        
        return count or 0
    
    async def mark_pod_sessions_interrupted(self, pod_id: str) -> int:
        """
        Mark sessions being processed by a pod as interrupted.
        Used during graceful shutdown.
        
        Returns:
            Number of sessions marked as interrupted
        """
        if not self.is_enabled:
            return 0
        
        def _interrupt_operation():
            with self.get_repository() as repo:
                if not repo:
                    return 0
                
                in_progress_sessions = repo.find_sessions_by_pod(pod_id, 'processing')
                
                for session_record in in_progress_sessions:
                    session_record.status = 'interrupted'
                    session_record.interrupted_at = now_us()
                    repo.update_alert_session(session_record)
                
                return len(in_progress_sessions)
        
        count = self._retry_database_operation("mark_interrupted_sessions", _interrupt_operation)
        
        if count and count > 0:
            logger.info(f"Marked {count} sessions as interrupted for pod {pod_id}")
        
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
                return repo.update_session_pod_tracking(session_id, pod_id, 'processing')
        
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
                return repo.update_alert_session(session) is not None
        
        return self._retry_database_operation("record_interaction", _interaction_operation) or False
```

**Layer 3: Application Lifecycle (backend/tarsy/main.py)**
```python
import os
from contextlib import asynccontextmanager
from tarsy.services.history_service import get_history_service

SESSION_TIMEOUT_MINUTES = 30

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown"""
    
    # Startup: Recover orphaned sessions
    history_service = get_history_service()
    if history_service and history_service.is_enabled:
        await history_service.recover_orphaned_sessions(SESSION_TIMEOUT_MINUTES)
    
    yield  # Application runs
    
    # Shutdown: Mark in-progress sessions as interrupted
    if history_service and history_service.is_enabled:
        pod_id = os.environ.get("HOSTNAME", "unknown")
        await history_service.mark_pod_sessions_interrupted(pod_id)
```

**Usage in Alert Processing (backend/tarsy/services/alert_service.py)**
```python
class AlertService:
    """Service for alert processing."""
    
    async def start_processing(self, session_id: str):
        """Start processing an alert session."""
        pod_id = os.environ.get("HOSTNAME", "unknown")
        
        if pod_id == "unknown":
            logger.warning(
                "HOSTNAME not set - pod tracking disabled. "
                "Set HOSTNAME in Kubernetes pod spec for multi-replica support."
            )
        
        # Mark session as being processed by this pod
        if self.history_service:
            await self.history_service.start_session_processing(session_id, pod_id)
        
        # ... rest of processing logic ...
    
    async def _record_interaction(self, session_id: str):
        """Record interaction timestamp (called on LLM calls, MCP tools, stage transitions)."""
        if self.history_service:
            await self.history_service.record_session_interaction(session_id)
```

**Database Schema Changes:**

A database migration will add the following columns to the `alert_sessions` table:
- `last_interaction_at` (BIGINT) - Unix timestamp in microseconds, updated on every LLM call, MCP tool call, stage transition
- `interrupted_at` (BIGINT) - Unix timestamp in microseconds when session was interrupted
- `pod_id` (VARCHAR) - Kubernetes pod identifier for tracking which pod is processing the session

An index will be created on `(status, last_interaction_at)` for efficient orphaned session detection.

**3.3 Health Check Enhancement (Issue #7)**

Add event system health check and proper HTTP status codes:

```python
# backend/tarsy/main.py
from fastapi import Response, status

@app.get("/health")
async def health_check(response: Response):
    """
    Health check endpoint for Kubernetes readiness/liveness probes.
    
    Returns:
        - HTTP 200: healthy
        - HTTP 503: degraded or unhealthy
    """
    # Database check already implemented ✅
    db_info = get_database_info()  # Already checks connection with SELECT 1
    
    # Add event system check (NEW)
    event_system_healthy = False
    event_system_type = "unknown"
    event_system_error = None
    
    if event_listener is None:
        # Event listener not initialized
        event_system_healthy = False
        event_system_type = "unknown"
        event_system_error = "Event listener not initialized"
    elif isinstance(event_listener, PostgreSQLEventListener):
        # Check if LISTEN connection is alive
        listener_conn = event_listener.listener_conn
        event_system_healthy = (
            listener_conn is not None and
            not listener_conn.closed
        )
        event_system_type = "postgresql"
    else:
        # SQLite polling
        event_system_healthy = event_listener.running
        event_system_type = "sqlite"
    
    health_status = {
        "status": "healthy",
        "service": "tarsy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "services": {
            "database": {
                "enabled": db_info.get("enabled"),
                "connected": db_info.get("connection_test")
            },
            "event_system": {
                "type": event_system_type,
                "connected": event_system_healthy
            }
        }
    }
    
    # Add error message if present
    if event_system_error:
        health_status["services"]["event_system"]["error"] = event_system_error
    
    # Set degraded status if critical systems fail
    if db_info.get("enabled") and not db_info.get("connection_test"):
        health_status["status"] = "degraded"
    
    if not event_system_healthy:
        health_status["status"] = "degraded"
    
    # Return HTTP 503 for degraded/unhealthy (Kubernetes probes)
    if health_status["status"] in ("degraded", "unhealthy"):
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    
    return health_status
```

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
        # Required: Inject pod name as HOSTNAME for session tracking
        - name: HOSTNAME
          valueFrom:
            fieldRef:
              fieldPath: metadata.name
        ports:
        - containerPort: 8000
```

**Why HOSTNAME is Required:**

If `HOSTNAME` is not set, all pods will have `pod_id = "unknown"`:
- ✅ Session creation will still work
- ✅ Orphaned session recovery will still work (uses `last_interaction_at`, not `pod_id`)
- ❌ **Graceful shutdown will break** - Pod A shutting down could mark Pod B's sessions as interrupted
- ❌ **Multi-pod interference** - All pods share the same `pod_id`, defeating the purpose of pod tracking

**Validation:**

The application will log a warning on each session start if `HOSTNAME` is not set:
```
WARNING: HOSTNAME not set - pod_id will be 'unknown'. This may cause issues in multi-replica deployments.
```

For production multi-replica deployments, `HOSTNAME` **must** be set in the pod spec as shown above.

### Phase 4: Documentation

Update documentation to cover:
- Multi-replica deployment architecture
- Event-driven cross-pod communication patterns
- Session cleanup and recovery mechanisms

