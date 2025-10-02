# Alert Data Separation - Two-Model Architecture

**Status:** Pending  
**Created:** 2025-10-01  
**Author:** System Design  

## Overview

This enhancement introduces a clean separation between API input data and internal processing data for alerts, ensuring that client-provided alert data remains pristine and is not polluted with internal processing metadata.

**Key Point:** The `data` field in alerts can contain **any complex, nested JSON structure** sent by external clients (AlertManager, webhooks, monitoring systems, etc.). We don't control or predict its structure - it could be deeply nested objects, arrays, mixed types, etc. Our system must preserve this data exactly as received and pass it to the LLM for interpretation.

## Problem Statement

### Current Issues

1. **Name Collisions**: Client's fields can be overwritten by our metadata
   ```json
   // Client sends
   {
     "alert_type": "kubernetes",
     "severity": "critical",
     "data": {
       "namespace": "prod",
       "severity": "user-severity"  // ← Gets overwritten!
     }
   }
   
   // After normalization
   {
     "alert_type": "kubernetes",
     "severity": "critical",  // ← Our value overwrites client's!
     "namespace": "prod"
     // ← Client's severity is LOST!
   }
   ```

2. **Data Pollution**: Client's clean data is mixed with our internal metadata
   ```json
   // Client's clean data
   {"namespace": "prod", "pod": "api-123"}
   
   // After we "normalize" it
   {
     "alert_type": "kubernetes",   // ← Not client's data
     "severity": "critical",        // ← Not client's data
     "timestamp": 123,              // ← Not client's data
     "environment": "production",   // ← Not client's data
     "runbook": "https://...",      // ← Not client's data
     "namespace": "prod",           // ← Client's data
     "pod": "api-123"               // ← Client's data
   }
   ```

3. **Not Minimal**: Violates principle of minimal data manipulation
   - We merge, overwrite, and add fields unnecessarily
   - Client data should be passed as-is to LLM for interpretation

4. **Type Safety Issues**: `runbook_url` extracted from client's `alert_data` instead of being a first-class field

5. **Complex Nested JSON**: Client data can be deeply nested and complex
   ```json
   // Example: AlertManager payload
   {
     "alert_type": "prometheus",
     "data": {
       "receiver": "team-X-pager",
       "status": "firing",
       "alerts": [
         {
           "status": "firing",
           "labels": {
             "alertname": "HighMemoryUsage",
             "instance": "server-01:9100",
             "job": "node-exporter",
             "severity": "warning",
             "team": "platform"
           },
           "annotations": {
             "description": "Memory usage is above 90%",
             "summary": "High memory usage detected",
             "runbook_url": "https://wiki/memory-runbook"
           },
           "startsAt": "2025-10-01T12:00:00Z",
           "endsAt": "0001-01-01T00:00:00Z",
           "generatorURL": "http://prometheus/graph?g0.expr=...",
           "fingerprint": "abc123def456"
         }
       ],
       "groupLabels": {"alertname": "HighMemoryUsage"},
       "commonLabels": {"job": "node-exporter", "severity": "warning"},
       "commonAnnotations": {},
       "externalURL": "http://alertmanager",
       "version": "4",
       "groupKey": "{}/{}:{}"
     }
   }
   ```
   
   We must preserve this entire nested structure without flattening, merging, or modifying any fields.

## Proposed Solution

### Two-Model Architecture

Introduce two distinct models with clear responsibilities:

1. **Alert** (API Input Model)
   - What external clients send to the API
   - Validates incoming payloads
   - Minimal required fields
   - Flexible `data` field for client's JSON (**can be any complex, nested structure**)

2. **ProcessingAlert** (Internal Model)
   - What we use internally for processing
   - Contains normalized metadata (separate from client data)
   - Contains pristine client data (untouched)
   - Factory method to transform API → Internal

3. **ChainContext** (Updated)
   - Add metadata fields directly to the model
   - Keep `alert_data` pristine (client's original data)
   - Fix `get_runbook_url()` to use metadata field
   - Add factory method to create from ProcessingAlert

### Data Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│ 1. Client sends Alert to API                                        │
│                                                                      │
│    POST /api/v1/alerts                                              │
│    {                                                                 │
│      "alert_type": "kubernetes",                                    │
│      "runbook": "https://...",  // Optional                         │
│      "severity": "critical",     // Optional                        │
│      "data": {                   // Client's pristine data (can be │
│        "namespace": "prod",      // complex nested JSON)            │
│        "pod": "api-123",                                            │
│        "labels": {                                                  │
│          "app": "backend",                                          │
│          "version": "v1.2.3"                                        │
│        },                                                            │
│        "metrics": [                                                 │
│          {"cpu": 85, "memory": 90},                                │
│          {"cpu": 92, "memory": 88}                                 │
│        ]                                                             │
│      }                                                               │
│    }                                                                 │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              │ Pydantic validation
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 2. Alert Model validates and parses                                 │
│                                                                      │
│    alert = Alert(**request_body)                                    │
│    ✓ alert_type present                                             │
│    ✓ data is Dict[str, Any]                                         │
│    ✓ runbook is Optional[str]                                       │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              │ Transform
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 3. ProcessingAlert.from_api_alert()                                 │
│                                                                      │
│    processing_alert = ProcessingAlert.from_api_alert(alert)         │
│                                                                      │
│    Metadata (extracted/generated):                                  │
│    - alert_type: "kubernetes"                                       │
│    - severity: "critical" (from alert or default "warning")         │
│    - timestamp: 1759360789012345 (from alert or auto-generated)     │
│    - environment: "production" (from data or default)               │
│    - runbook_url: "https://..." (from alert)                        │
│                                                                      │
│    Client Data (pristine):                                          │
│    - alert_data: {                                                  │
│        "namespace": "prod",                                         │
│        "pod": "api-123",                                            │
│        "severity": "user-severity"  ← PRESERVED!                    │
│      }                                                               │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              │ Create context
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 4. ChainContext.from_processing_alert()                             │
│                                                                      │
│    chain_context = ChainContext.from_processing_alert(              │
│        processing_alert=processing_alert,                           │
│        session_id=session_id,                                       │
│        current_stage_name="initializing"                            │
│    )                                                                 │
│                                                                      │
│    Result:                                                           │
│    - Metadata fields: alert_type, severity, timestamp, etc.         │
│    - Pristine client data: alert_data                               │
│    - No collisions, no pollution                                    │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              │ Process
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 5. Alert Service processes with clean context                       │
│                                                                      │
│    await alert_service.process_alert(chain_context)                 │
│                                                                      │
│    Access metadata: context.severity, context.timestamp             │
│    Access client data: context.alert_data (pristine)                │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              │ Format for LLM
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 6. Prompt Template formats both sections separately                 │
│                                                                      │
│    ## Alert Metadata                                                │
│    **Alert Type:** kubernetes                                       │
│    **Severity:** critical                                           │
│    **Timestamp:** 1759360789012345                                  │
│    **Environment:** production                                      │
│    **Runbook:** https://...                                         │
│                                                                      │
│    ## Alert Data (from client)                                      │
│    **Namespace:** prod                                              │
│    **Pod:** api-123                                                 │
│    **Severity:** user-severity  ← No collision!                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Implementation Details

### 1. Alert Model (API Input)

**File:** `backend/tarsy/models/alert.py`

```python
from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class Alert(BaseModel):
    """
    API input model - what external clients send.
    
    This model validates incoming alert payloads from external systems
    (AlertManager, Prometheus, webhooks, monitoring tools, etc.).
    
    The 'data' field accepts any complex, nested JSON structure:
    - Deeply nested objects
    - Arrays and mixed types
    - Any field names (including those that might conflict with our metadata)
    - Completely arbitrary schema - we don't control what clients send
    
    Client data is preserved exactly as received and passed pristine to processing.
    """
    
    alert_type: str = Field(
        ..., 
        description="Alert type for agent selection"
    )
    runbook: Optional[str] = Field(
        None, 
        description="Processing runbook URL (optional, uses built-in default if not provided)"
    )
    severity: Optional[str] = Field(
        None, 
        description="Alert severity (defaults to 'warning')"
    )
    timestamp: Optional[int] = Field(
        None, 
        description="Alert timestamp in unix microseconds (auto-generated if not provided)"
    )
    data: Dict[str, Any] = Field(
        default_factory=dict, 
        description="Client's alert data - can be any complex nested JSON structure"
    )
    
    @classmethod
    def get_required_fields(cls) -> List[str]:
        """Get list of required API field names."""
        return [
            field_name 
            for field_name, field_info in cls.model_fields.items() 
            if field_info.is_required()
        ]
    
    @classmethod
    def get_optional_fields(cls) -> List[str]:
        """Get list of optional API field names."""
        return [
            field_name 
            for field_name, field_info in cls.model_fields.items() 
            if not field_info.is_required()
        ]
```

### 2. ProcessingAlert Model (Internal)

**File:** `backend/tarsy/models/alert.py`

```python
class ProcessingAlert(BaseModel):
    """
    Internal processing model - what we use for alert processing.
    
    This model contains:
    1. Normalized metadata (our fields)
    2. Client's pristine alert data (untouched)
    
    Keeps client data completely separate from our processing metadata.
    No name collisions, no data pollution.
    """
    
    # === Processing Metadata (our fields) ===
    alert_type: str = Field(
        ..., 
        description="Alert type (always set)"
    )
    severity: str = Field(
        ..., 
        description="Normalized severity (always set, default: 'warning')"
    )
    timestamp: int = Field(
        ..., 
        description="Processing timestamp in unix microseconds (always set)"
    )
    environment: str = Field(
        default="production",
        description="Environment (from client data or default)"
    )
    runbook_url: Optional[str] = Field(
        None, 
        description="Runbook URL if provided"
    )
    
    # === Client's Pristine Data ===
    alert_data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Client's original alert data (pristine, no metadata mixed in)"
    )
    
    @classmethod
    def from_api_alert(cls, alert: Alert) -> ProcessingAlert:
        """
        Transform API Alert to ProcessingAlert.
        
        Applies minimal manipulation:
        1. Extract/generate metadata (severity, timestamp, environment)
        2. Keep client's data pristine (no merging, no modifications)
        
        Args:
            alert: Validated API Alert from client
            
        Returns:
            ProcessingAlert ready for ChainContext
        """
        from tarsy.utils.timestamp import now_us
        from datetime import datetime
        
        # Extract environment from client data if present (but keep it there too)
        environment = alert.data.get('environment', 'production')
        
        # Generate timestamp if not provided
        if alert.timestamp is None:
            timestamp = now_us()
        elif isinstance(alert.timestamp, datetime):
            timestamp = int(alert.timestamp.timestamp() * 1000000)
        else:
            timestamp = alert.timestamp
        
        return cls(
            alert_type=alert.alert_type,
            severity=alert.severity or 'warning',
            timestamp=timestamp,
            environment=environment,
            runbook_url=alert.runbook,
            alert_data=alert.data  # ← PRISTINE!
        )
```

### 3. ChainContext Updates

**File:** `backend/tarsy/models/processing_context.py`

```python
class ChainContext(BaseModel):
    """
    Context for entire chain processing session.
    
    Uses composition to keep ProcessingAlert as a single source of truth
    for alert metadata and client data, while ChainContext manages session
    and execution state.
    
    This design follows the principle: "Different purposes deserve different models"
    - ProcessingAlert = Alert state (metadata + client data)
    - ChainContext = Session state (alert + execution + history)
    """
    model_config: ConfigDict = ConfigDict(extra="forbid", frozen=False)
    
    # === Alert state (composed) ===
    processing_alert: ProcessingAlert = Field(
        ..., 
        description="Complete alert state including metadata and client data"
    )
    
    # === Session state ===
    session_id: str = Field(..., description="Processing session ID", min_length=1)
    current_stage_name: str = Field(..., description="Currently executing stage name", min_length=1)
    stage_outputs: Dict[str, AgentExecutionResult] = Field(
        default_factory=dict,
        description="Results from completed stages"
    )
    
    # === Processing support ===
    runbook_content: Optional[str] = Field(None, description="Downloaded runbook content")
    chain_id: Optional[str] = Field(None, description="Chain identifier")
    
    @classmethod
    def from_processing_alert(
        cls,
        processing_alert: ProcessingAlert,
        session_id: str,
        current_stage_name: str = "initializing"
    ) -> ChainContext:
        """
        Create ChainContext from ProcessingAlert.
        
        This is the preferred way to create ChainContext from API alerts.
        
        Args:
            processing_alert: Processed alert with metadata
            session_id: Processing session ID
            current_stage_name: Initial stage name
            
        Returns:
            ChainContext ready for processing
        """
        return cls(
            processing_alert=processing_alert,
            session_id=session_id,
            current_stage_name=current_stage_name
        )
    
    # ... rest of methods stay the same ...
```

### 4. Controller Usage

**File:** `backend/tarsy/controllers/alert_controller.py`

```python
# In submit_alert endpoint

# 1. Validate API input with Alert model
alert_data = Alert(**sanitized_data)

# 2. Validate runbook URL scheme if provided
if alert_data.runbook:
    parsed = urlparse(alert_data.runbook)
    if parsed.scheme not in ["http", "https", "github"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "Invalid runbook URL scheme",
                "message": f"Runbook URL scheme must be http, https, or github. Got: {parsed.scheme}",
                "runbook_url": alert_data.runbook,
            }
        )

# 3. Transform to ProcessingAlert (adds metadata, keeps data pristine)
processing_alert = ProcessingAlert.from_api_alert(alert_data)

# 4. Generate session ID
session_id = generate_session_id()

# 5. Create ChainContext from ProcessingAlert
alert_context = ChainContext.from_processing_alert(
    processing_alert=processing_alert,
    session_id=session_id,
    current_stage_name="initializing"
)

# 6. Submit for processing
asyncio.create_task(alert_service.process_alert(alert_context))

# 7. Return response
return AlertResponse(
    alert_id=session_id,
    status="accepted",
    message="Alert accepted for processing"
)
```

## Benefits

### ✅ No Name Collisions
Client can have their own `severity`, `timestamp`, `alert_type`, etc. in their `data` field without any conflicts.

### ✅ Minimal Manipulation
Client data stays pristine - we only extract what we need for metadata, but don't modify or merge.

### ✅ Type-Safe
All fields validated by Pydantic at every layer:
- API input → Alert model
- Internal processing → ProcessingAlert model
- Context → ChainContext model

### ✅ Clean Separation
- **ProcessingAlert** = Alert state (metadata + client data)
- **ChainContext** = Session state (alert + execution + history)

Single source of truth via composition - no field duplication.

### ✅ Flexible
Client can send ANY JSON structure in `data` field. We don't need to know the schema.

### ✅ Clean Access Patterns
Access alert data directly through composition:
```python
# Alert metadata
context.processing_alert.severity
context.processing_alert.timestamp
context.processing_alert.environment
context.processing_alert.alert_type
context.processing_alert.runbook_url

# Client data
context.processing_alert.alert_data
```

### ✅ Handles Complex Nested JSON
`Dict[str, Any]` type allows any JSON structure:
- **Deeply nested objects**: `{"a": {"b": {"c": {"d": "value"}}}}`
- **Arrays of objects**: `{"alerts": [{"id": 1, "status": "firing"}]}`
- **Mixed types**: `{"metrics": [85, 92], "labels": {"team": "platform"}}`
- **Arbitrary schemas**: We don't need to know the structure ahead of time
- **Preserves everything**: No flattening, no field extraction, just pass it through

The LLM receives the entire structure as-is and can interpret it contextually.

## Migration Plan

### Phase 1: Model Updates
1. Update `backend/tarsy/models/alert.py`
   - Modify `Alert` model to match new structure
   - Add `ProcessingAlert` model
   - Keep `AlertResponse` unchanged

2. Update `backend/tarsy/models/processing_context.py`
   - Replace unpacked alert fields with `processing_alert: ProcessingAlert` field (composition)
   - Update `from_processing_alert()` factory method to use composition
   - Remove convenience methods (`get_runbook_url()`, `get_original_alert_data()`) - use direct access

### Phase 2: Controller Updates
3. Update `backend/tarsy/controllers/alert_controller.py`
   - Use `ProcessingAlert.from_api_alert()`
   - Use `ChainContext.from_processing_alert()`
   - **Delete** `NormalizedAlertData` class and all its usage

### Phase 3: Update All Alert Field Access
4. Update all code that accesses alert fields from ChainContext:
   - `context.alert_type` → `context.processing_alert.alert_type`
   - `context.severity` → `context.processing_alert.severity`
   - `context.timestamp` → `context.processing_alert.timestamp`
   - `context.environment` → `context.processing_alert.environment`
   - `context.alert_data` → `context.processing_alert.alert_data`
   - `context.get_runbook_url()` → `context.processing_alert.runbook_url`
   - `context.get_original_alert_data()` → `context.processing_alert.alert_data.copy()`
   
   Search for `chain_context.` and `context.` patterns in:
   - `backend/tarsy/services/`
   - `backend/tarsy/agents/`
   - Any other code using ChainContext

### Phase 4: Test Updates
5. Update test fixtures
   - `backend/tests/conftest.py`
   - `backend/tests/e2e/conftest.py`
   - `backend/tests/unit/models/test_context_factories.py`

### Phase 5: Prompt Template Updates
6. Update `backend/tarsy/agents/prompts/alert_section_template.py`
   - Separate "Alert Metadata" and "Alert Data" sections
   - Show metadata fields explicitly
   - Show client data as-is

7. Update test expectations
   - `backend/tests/e2e/expected_conversations.py`
   - Unit tests that check ChainContext structure

### Phase 6: Validation
8. Run full test suite
   ```bash
   cd backend
   make test-unit
   make test-integration
   make test-e2e
   ```

9. Manual testing
   - Submit alerts with and without runbook
   - Submit alerts with complex nested JSON
   - Verify prompts show metadata and client data correctly

## Testing Strategy

### Unit Tests

**Test ProcessingAlert.from_api_alert()**
```python
def test_processing_alert_preserves_client_data():
    """Client data stays pristine, no field overwrites."""
    alert = Alert(
        alert_type="kubernetes",
        severity="critical",
        data={
            "namespace": "prod",
            "severity": "user-severity",  # Collision!
            "custom_field": "value"
        }
    )
    
    processing_alert = ProcessingAlert.from_api_alert(alert)
    
    # Metadata correctly set
    assert processing_alert.severity == "critical"
    assert processing_alert.alert_type == "kubernetes"
    assert processing_alert.environment == "production"
    
    # Client data pristine (includes their severity!)
    assert processing_alert.alert_data == {
        "namespace": "prod",
        "severity": "user-severity",  # ← PRESERVED!
        "custom_field": "value"
    }
```

**Test ChainContext.from_processing_alert()**
```python
def test_chain_context_from_processing_alert():
    """ChainContext correctly populated from ProcessingAlert."""
    processing_alert = ProcessingAlert(
        alert_type="kubernetes",
        severity="warning",
        timestamp=123456789,
        environment="staging",
        runbook_url="https://example.com/runbook",
        alert_data={"namespace": "test"}
    )
    
    context = ChainContext.from_processing_alert(
        processing_alert=processing_alert,
        session_id="session-123",
        current_stage_name="init"
    )
    
    # Metadata fields populated
    assert context.alert_type == "kubernetes"
    assert context.severity == "warning"
    assert context.timestamp == 123456789
    assert context.environment == "staging"
    assert context.runbook_url == "https://example.com/runbook"
    
    # Client data pristine
    assert context.alert_data == {"namespace": "test"}
    
    # Session fields
    assert context.session_id == "session-123"
    assert context.current_stage_name == "init"
```

**Test Complex Nested JSON**
```python
def test_processing_alert_handles_complex_nested_json():
    """Complex nested JSON structures are preserved as-is."""
    alert = Alert(
        alert_type="prometheus",
        data={
            "receiver": "team-platform",
            "status": "firing",
            "alerts": [
                {
                    "status": "firing",
                    "labels": {
                        "alertname": "HighMemoryUsage",
                        "instance": "server-01:9100",
                        "severity": "warning"
                    },
                    "annotations": {
                        "description": "Memory > 90%",
                        "runbook_url": "https://wiki/memory"
                    },
                    "metrics": [
                        {"timestamp": 1234567, "value": 92.5},
                        {"timestamp": 1234568, "value": 93.2}
                    ]
                }
            ],
            "groupLabels": {"alertname": "HighMemoryUsage"},
            "commonLabels": {"job": "node-exporter"}
        }
    )
    
    processing_alert = ProcessingAlert.from_api_alert(alert)
    
    # Complex nested structure preserved exactly
    assert processing_alert.alert_data["receiver"] == "team-platform"
    assert len(processing_alert.alert_data["alerts"]) == 1
    assert processing_alert.alert_data["alerts"][0]["labels"]["severity"] == "warning"
    assert len(processing_alert.alert_data["alerts"][0]["metrics"]) == 2
    assert processing_alert.alert_data["alerts"][0]["metrics"][0]["value"] == 92.5
    
    # Nested structures stay nested (not flattened)
    assert isinstance(processing_alert.alert_data["alerts"], list)
    assert isinstance(processing_alert.alert_data["alerts"][0]["labels"], dict)
    assert isinstance(processing_alert.alert_data["alerts"][0]["metrics"], list)
```

### Integration Tests

**Test API → Processing Flow**
```python
async def test_alert_submission_with_data_collision():
    """Submit alert where client data has fields that match our metadata."""
    payload = {
        "alert_type": "kubernetes",
        "severity": "critical",
        "data": {
            "namespace": "prod",
            "severity": "INFO",  # Client's severity
            "timestamp": "2025-10-01T10:00:00Z"  # Client's timestamp
        }
    }
    
    response = await client.post("/api/v1/alerts", json=payload)
    assert response.status_code == 200
    
    # Verify ChainContext was created correctly
    # (Would need to inspect via dashboard or history)
```

### E2E Tests

**Test Full Alert Processing**
- Submit alert with complex client data
- Verify LLM receives both metadata and client data separately
- Verify no field collisions in conversation history
- Verify prompt shows "Alert Metadata" and "Alert Data" sections


## Conclusion

This two-model architecture provides:
- **Clean separation** between API contracts and internal processing
- **Minimal data manipulation** - client data stays pristine
- **No collisions** - metadata and client data in separate namespaces
- **Type safety** - Pydantic validation at every layer
- **Flexibility** - client can send any JSON structure

Clean, type-safe architecture ready for implementation.

