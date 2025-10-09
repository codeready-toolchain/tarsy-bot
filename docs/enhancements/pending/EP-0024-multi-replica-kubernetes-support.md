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

### Critical Issues

#### 1. Alert Deduplication State **[SEPARATE]**
**Location:** `backend/tarsy/controllers/alert_controller.py:28-29`

In-memory dictionary `processing_alert_keys` is maintained per-pod. Same alert hitting different replicas will be processed multiple times.

**Solution:**
- Database-based locking table using existing PostgreSQL
- Implement distributed lock acquisition before processing
- Use PostgreSQL advisory locks or dedicated `alert_locks` table

#### 2. WebSocket Connection Management **[SOLVED BY EP-0025]**
**Location:** `backend/tarsy/services/dashboard_connection_manager.py:26-32`

WebSocket connections stored in-memory per pod. Dashboard clients connected to Pod A won't receive updates for alerts processed by Pod B.

**Solution:**
- ✅ Replace WebSockets with Server-Sent Events (SSE)
- ✅ Implement PostgreSQL LISTEN/NOTIFY for cross-pod event distribution
- ✅ Events published by any pod are broadcast to all pods
- ✅ Each pod forwards events to its connected SSE clients
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
- ✅ SSE clients receive events via PostgreSQL LISTEN/NOTIFY
- ✅ Event table provides catchup for missed messages
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

### Issues Requiring Separate Implementation (4 of 7)
- **Issue #1**: Alert Deduplication - Database-based locking
- **Issue #3**: Logging - Drop file logging, stdout/stderr only
- **Issue #4**: Orphaned Session Cleanup & Graceful Shutdown - Hybrid approach (startup recovery + graceful shutdown hook)
- **Issue #7**: Health Check Enhancement - Add event system status + HTTP 503 for degraded state

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

### Phase 2: Alert Deduplication (Issue #1)

Implement distributed locking for alert processing:

```python
# Pseudo-code
async def process_alert(alert_key: str):
    # Acquire distributed lock
    lock = await acquire_lock(alert_key, timeout=300)
    if not lock:
        logger.info(f"Alert {alert_key} already being processed")
        return
    
    try:
        # Process alert
        await _process_alert_logic(alert_key)
    finally:
        await release_lock(alert_key)
```

**Options:**
- PostgreSQL advisory locks: `pg_try_advisory_lock(hash)`
- Database table: `INSERT INTO alert_locks (alert_key, locked_at, pod_id)`

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

```python
# backend/tarsy/main.py

SESSION_TIMEOUT_MINUTES = 30

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown"""
    
    # Startup: Recover orphaned sessions
    await recover_orphaned_sessions()
    
    yield  # Application runs
    
    # Shutdown: Mark in-progress sessions
    await mark_interrupted_sessions()


async def recover_orphaned_sessions():
    """Find and mark orphaned sessions on pod startup"""
    async with get_async_session() as session:
        result = await session.execute(
            text("""
                UPDATE sessions 
                SET status = 'failed',
                    error = 'Session orphaned - pod crashed or timeout',
                    failed_at = NOW()
                WHERE status IN ('processing', 'interrupted')
                  AND last_interaction_at < NOW() - INTERVAL :timeout
                RETURNING id, alert_id
            """),
            {"timeout": f"{SESSION_TIMEOUT_MINUTES} minutes"}
        )
        
        orphaned = result.fetchall()
        await session.commit()
        
        # Publish events for dashboard updates
        for row in orphaned:
            await publish_event(
                session,
                channel=EventChannel.SESSIONS,
                event_type='session.failed',
                session_id=row.id,
                alert_id=row.alert_id,
                reason='orphaned'
            )
        
        if orphaned:
            logger.info(f"Recovered {len(orphaned)} orphaned sessions")


async def mark_interrupted_sessions():
    """Mark in-progress sessions as interrupted on graceful shutdown"""
    async with get_async_session() as session:
        result = await session.execute(
            text("""
                UPDATE sessions 
                SET status = 'interrupted',
                    interrupted_at = NOW()
                WHERE status = 'processing'
                  AND pod_id = :pod_id
                RETURNING id
            """),
            {"pod_id": os.environ.get("HOSTNAME", "unknown")}
        )
        
        interrupted_count = len(result.fetchall())
        await session.commit()
        
        if interrupted_count > 0:
            logger.info(f"Marked {interrupted_count} sessions as interrupted")


# Set pod_id during session start
async def start_session(session_id: str, alert_id: str):
    """
    Start processing a session and assign it to this pod.
    
    IMPORTANT: Requires HOSTNAME environment variable to be set in pod spec.
    Without it, multiple pods will have pod_id='unknown' and interfere during
    graceful shutdown (one pod could mark another pod's sessions as interrupted).
    """
    pod_id = os.environ.get("HOSTNAME", "unknown")
    
    if pod_id == "unknown":
        logger.warning(
            "HOSTNAME not set - pod_id will be 'unknown'. "
            "This may cause issues in multi-replica deployments. "
            "Set HOSTNAME in Kubernetes pod spec: "
            "env: [{name: HOSTNAME, valueFrom: {fieldRef: {fieldPath: metadata.name}}}]"
        )
    
    async with get_async_session() as session:
        await session.execute(
            text("""
                UPDATE sessions 
                SET status = 'processing',
                    pod_id = :pod_id,
                    last_interaction_at = NOW()
                WHERE id = :session_id
            """),
            {
                "session_id": session_id,
                "pod_id": pod_id
            }
        )
        await session.commit()


# Update last_interaction_at during processing
async def record_interaction(session_id: str):
    """Update session interaction timestamp"""
    async with get_async_session() as session:
        await session.execute(
            text("""
                UPDATE sessions 
                SET last_interaction_at = NOW()
                WHERE id = :session_id
            """),
            {"session_id": session_id}
        )
        await session.commit()
```

**Database Schema Addition:**
```sql
ALTER TABLE sessions 
ADD COLUMN last_interaction_at TIMESTAMP DEFAULT NOW(),
ADD COLUMN interrupted_at TIMESTAMP,
ADD COLUMN pod_id VARCHAR(255);

CREATE INDEX idx_sessions_orphan_detection 
ON sessions(status, last_interaction_at);
```

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

