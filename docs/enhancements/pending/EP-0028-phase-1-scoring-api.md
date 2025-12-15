# EP-0028 Phase 1: Alert Session Scoring API

**Status:** Pending
**Created:** 2025-12-05
**Phase:** Design

---

## Overview

Add systematic quality assessment for TARSy alert analysis sessions through an LLM-based judge that critically evaluates investigation methodology and provides actionable feedback.

**Core Capabilities:**

1. **LLM-Based Scoring**: Judge LLM evaluates completed sessions using rigorous scoring framework
2. **Critical Evaluation**: Methodology-focused assessment with strict standards (4 dimensions: logical flow, consistency, tool relevance, synthesis quality)
3. **Actionable Feedback**:
   * Identify missing MCP tools that should have been used
   * Suggest alternative investigation approaches with detailed steps
   * Provide improvement recommendations
4. **Criteria Evolution**: Content-addressed configuration (SHA256 hash) tracks scoring criteria changes over time
5. **Quality Metrics**: Quantitative scores (0-100) enable tracking improvements and identifying patterns
6. **Non-Intrusive**: Post-session scoring with zero impact on alert processing
7. **Manual Control**: Operator-triggered scoring only (Phase 1 scope)

**Primary Use Cases:**

* Agent development feedback and improvement tracking
* MCP server prioritization based on gap analysis
* Training data curation for high-quality sessions
* Investigation methodology pattern discovery

**Scope:** On-demand scoring API for individual sessions via REST endpoints and basic UI integration. Scheduled batch scoring, analytics aggregation and reporting are left for the future.

**POC Reference:** Initial prototype at <https://github.com/metlos/tarsy-response-score> proved judge LLM provides critical scoring even for self-produced analyses.

---

## Configuration Syntax

**Configuration File:** `config/scoring_config.yaml`

```yaml
# Scoring service settings (supports template variable substitution)
scoring:
  enabled: ${SCORING_ENABLED:-true}
  llm_provider: ${SCORING_LLM_PROVIDER:-${DEFAULT_LLM_PROVIDER}}
  llm_model: ${SCORING_LLM_MODEL:-}  # Empty = use provider default

# Judge prompt template with placeholders
# The entire configuration (including this prompt) is hashed to track criteria evolution.
judge_prompt: |
  A prompt explaining how to perform the score. This prompt includes placeholders
  to be replaced with the actual data from the session. See below for more details.

  The prompt used with good success in the POC is included in the "attachment"
  section at the end of this EP.
```

**Environment Variables** (optional overrides):

```bash
# Enable/disable scoring (default: true)
SCORING_ENABLED=true

# LLM provider for scoring (default: falls back to DEFAULT_LLM_PROVIDER)
SCORING_LLM_PROVIDER=google-default

# Model for scoring (default: provider-specific default)
SCORING_LLM_MODEL=gemini-2.0-flash-exp
```

**Placeholder System:**

The judge prompt supports three placeholders that are replaced at runtime:

* `{{SESSION_CONVERSATION}}` - Complete conversation from History Service (includes all MCP tool usage)
* `{{ALERT_DATA}}` - Original alert data for reference
* `{{OUTPUT_SCHEMA}}` - JSON schema specification (automatically injected from `JudgeOutputSchema` class)

**Design Rationale:**

* **Separation of Concerns**: Configuration defines how to *evaluate* (criteria), code defines how to *report* it (output schema)
* **Parsing Reliability**: Output format guaranteed to match code expectations
* **Criteria Evolution**: Full prompt is hashed (SHA256) to track changes; output schema changes require code updates

---

## API Usage

**Note:** Phase 6 provides dashboard UI for these endpoints with visual score display and manual triggering.

### Score Session

**Endpoint:** `POST /api/v1/scoring/sessions/{session_id}/score`

**Purpose:** Trigger scoring for a specific session (operator-initiated or UI-triggered)

**Request Body:**

```json
{
  "force_rescore": false  // optional: re-score even if score exists
}
```

**Response (200 OK):**

```json
{
  "score_id": "550e8400-e29b-41d4-a716-446655440000",
  "session_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "criteria_hash": "a3f5b2c1d4e7f9a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9",
  "total_score": 67,
  "score_breakdown": {
    "logical_flow": 15,
    "consistency": 18,
    "tool_relevance": 14,
    "synthesis_quality": 20
  },
  "score_reasoning": "The investigation demonstrates adequate methodology with notable gaps...",
  "missing_tools": [
    {
      "tool_name": "list-processes-in-pod",
      "rationale": "Would have confirmed whether the suspicious binary was actively running..."
    }
  ],
  "alternative_approaches": [
    {
      "name": "File-First Forensic Approach",
      "description": "Systematically enumerate all suspicious files before attempting execution verification",
      "steps": [
        "Use list-files to discover all files in suspicious directory",
        "Read content of each file to identify actual malware vs false positives",
        "Correlate file timestamps with alert time window"
      ]
    }
  ],
  "scored_triggered_by": "alice@example.com",
  "scored_at": "2025-12-05T10:30:00Z",
  "is_current_criteria": true
}
```

**Note:** The `score_breakdown` structure is flexible and depends on scoring criteria. Structure may evolve as criteria change.

**Error Responses:**

* `400 Bad Request` - Session not completed or invalid state
* `500 Internal Server Error` - LLM API failure or database error

### Get Session Score

**Endpoint:** `GET /api/v1/scoring/sessions/{session_id}/score`

**Purpose:** Retrieve existing score for a session

**Response:** Same as Score Session endpoint

**Error Responses:**

* `404 Not Found` - Session not found or not yet scored
* `500 Internal Server Error` - LLM API failure or database error

---

## Scoring Output Schema

The judge LLM must return JSON matching this structure (defined in code as `JudgeOutputSchema`):

```python
class MissingTool(BaseModel):
    """Missing tool that should have been used in the investigation."""
    tool_name: str = Field(..., description="Name of the missing MCP tool")
    rationale: str = Field(..., description="Explanation of why this tool was needed")

class AlternativeApproach(BaseModel):
    """Alternative investigation approach that could have been more efficient/rigorous."""
    name: str = Field(..., description="Brief descriptive title of the approach")
    description: str = Field(..., description="1-2 sentences explaining the strategy")
    steps: List[str] = Field(..., description="Ordered list of specific actions")

class JudgeOutputSchema(BaseModel):
    """
    Output schema for judge LLM - defined in code for parsing reliability.
    Injected into judge prompt at {{OUTPUT_SCHEMA}} placeholder.
    """
    total_score: int = Field(..., ge=0, le=100, description="Overall score 0-100")
    score_breakdown: Dict[str, Any] = Field(..., description="Flexible dimension scores (e.g., {'logical_flow': 18, ...})")
    score_reasoning: str = Field(..., description="Detailed explanation (200+ words recommended)")
    missing_tools: List[MissingTool] = Field(default_factory=list, description="Tools that should have been used")
    alternative_approaches: List[AlternativeApproach] = Field(default_factory=list, description="Alternative investigation approaches")
```

**Note:** Only `total_score` is required. The `score_breakdown` dimensions can evolve as criteria change (stored as JSONB for flexibility). The nested models (`MissingTool`, `AlternativeApproach`) ensure type safety and clean database mapping.

---

## Use Cases

**Primary Use Cases:**

* **Manual Quality Review**: Operators score completed investigations to understand quality and identify improvement areas
* **Agent Development Feedback**: Developers quantify agent improvements after code changes and identify specific gaps (e.g., "missing file-read tools")
* **MCP Server Prioritization**: Team analyzes `score_missing_tools` frequency to make data-driven decisions on which tools to develop next
* **Criteria Evolution Tracking**: Operators re-score historical sessions with new criteria (different `criteria_hash`) to validate criteria changes
* **Investigation Methodology Improvement**: Operators review alternative approaches from scores to learn investigation patterns
* **Training Data Curation**: ML engineers identify high-quality sessions (total_score >= 85) for fine-tuning datasets

---

## Implementation Tasks

### Task 1: Database Schema

**Tables to Create:**

1. **`scoring_criteria_definitions`**
   * Primary key: `criteria_hash` (VARCHAR 64, SHA256 of full config)
   * `criteria_content` (JSONB) - Complete scoring configuration
   * `created_at` (TIMESTAMP)
   * Index on `created_at`

2. **`session_scores`**
   * Primary key: `score_id` (UUID)
   * Unique constraint: `session_id`
   * Foreign keys: `session_id` → alert_sessions, `criteria_hash` → scoring_criteria_definitions
   * `total_score` (INTEGER, 0-100)
   * `score_breakdown` (JSONB) - Flexible dimension scores
   * `score_reasoning` (TEXT)
   * `scored_triggered_by` (VARCHAR 255) - User who triggered scoring (from X-Forwarded-User header)
   * `scored_at` (TIMESTAMP)
   * Indexes on: `session_id`, `criteria_hash`, `total_score`, `scored_at`

3. **`score_missing_tools`**
   * Primary key: `id` (UUID)
   * Foreign key: `score_id` → session_scores
   * `tool_name` (VARCHAR 255)
   * `rationale` (TEXT)
   * Indexes on: `score_id`, `tool_name`

4. **`score_alternative_approaches`**
   * Primary key: `id` (UUID)
   * Foreign key: `score_id` → session_scores
   * `name` (VARCHAR 255)
   * `description` (TEXT)
   * Indexes on: `score_id`, `name`

5. **`score_alternative_approach_steps`**
   * Primary key: `id` (UUID)
   * Foreign key: `approach_id` → score_alternative_approaches
   * `step_order` (INTEGER)
   * `step_description` (TEXT)
   * Index on: `approach_id`

**Alembic Migration:**

* Create forward migration with all tables and indexes
* Create rollback migration (drop tables in reverse dependency order)

### Task 2: Data Models

**Database Models (SQLModel):**

* `ScoringCriteriaDefinitionDB` - Criteria storage
* `SessionScoreDB` - Main score record with relationships
* `MissingToolDB` - Missing tool entries
* `AlternativeApproachDB` - Alternative approach entries
* `AlternativeApproachStepDB` - Approach step entries

**API Models (Pydantic):**

* `SessionScore` - API response with nested objects
* `MissingTool` - Missing tool representation
* `AlternativeApproach` - Alternative approach with steps list
* `ScoringCriteriaDefinition` - Criteria definition response
* `JudgeOutputSchema` - For parsing LLM JSON responses

**Repository Layer:**

* Convert database models (with relationships) to API models (with nested objects)
* Handle eager loading for efficiency
* Map `is_current_criteria` by comparing hash to current config

### Task 3: Scoring Service

**Core Logic (`backend/tarsy/services/scoring_service.py`):**

1. **Configuration Loading**:
   * Load `config/scoring_config.yaml` with template variable substitution
   * Compute SHA256 hash of full configuration (deterministic criteria versioning)
   * Store criteria definition in database if not exists

2. **Session Data Retrieval**:
   * Call History Service to get complete session conversation
   * Equivalent to `/final-analysis` endpoint data (~25k tokens)

3. **Judge Prompt Construction**:
   * Replace `{{SESSION_CONVERSATION}}` with full conversation
   * Replace `{{ALERT_DATA}}` with original alert
   * Replace `{{OUTPUT_SCHEMA}}` with JSON schema from `JudgeOutputSchema`

4. **LLM Integration**:
   * Send prompt to judge LLM (configurable provider/model)
   * Retry with exponential backoff (max 3 retries: 1s, 2s, 4s)
   * Circuit breaker: open after 5 consecutive failures

5. **Response Parsing**:
   * Parse JSON response into `JudgeOutputSchema`
   * Validate total_score, score_breakdown, missing_tools, alternative_approaches

6. **Database Storage**:
   * Insert `session_scores` record
   * Insert `score_missing_tools` records (bulk)
   * Insert `score_alternative_approaches` and `score_alternative_approach_steps` (bulk)
   * Return populated `SessionScore` API model

7. **Error Handling**:
   * Invalid JSON: Log raw response, return 500 with details
   * Database failures: Retry once, then return 500
   * Missing session: Return 404

### Task 4: API Controller

**Controller (`backend/tarsy/controllers/scoring_controller.py`):**

* `POST /api/v1/scoring/sessions/{session_id}/score`
  * Check if score exists (unless `force_rescore=true`)
  * Execute scoring via background task (FastAPI BackgroundTasks)
  * Return score immediately if exists, or start scoring and poll/wait

* `GET /api/v1/scoring/sessions/{session_id}/score`
  * Retrieve score from repository
  * Compute `is_current_criteria` by comparing hash
  * Return 404 if not scored

**User Attribution:**

* Extract user from `X-Forwarded-User` header (oauth2-proxy)
* Store in `scored_triggered_by` field of session_scores table for audit trail

### Task 5: Configuration Loading

**Config Service Updates:**

* Load `scoring_config.yaml` similar to `agents.yaml` and `llm_providers.yaml`
* Template variable substitution (e.g., `${SCORING_LLM_PROVIDER:-${DEFAULT_LLM_PROVIDER}}`)
* SHA256 hashing logic: Hash full resolved YAML content for deterministic `criteria_hash`
* Store criteria definition on first use (idempotent)

### Task 6: Testing

**Unit Tests:**

* Model validation (JudgeOutputSchema, SessionScore)
* Configuration hashing (deterministic results)
* Prompt placeholder substitution
* JSON response parsing (valid and invalid cases)
* Repository conversion (DB models → API models)

**Integration Tests:**

* Full scoring flow: session retrieval → LLM call → database storage
* Mock LLM responses for consistency
* Re-scoring with `force_rescore=true`
* Error handling: missing session, invalid JSON, database failures

**Test Coverage Target:** 80% minimum for new components, 100% for critical paths (scoring logic, database operations)

---

## Key Design Decisions

1. **Content-Addressed Criteria**: SHA256 hash of full configuration eliminates manual version management and provides automatic obsolescence detection
2. **JSONB Flexibility vs Normalized Feedback**: Score dimensions in flexible JSONB (criteria evolve), but missing tools and alternatives in normalized tables (enables analytics)
3. **Output Schema in Code, Criteria in Config**: Separation of concerns - config defines *what* to evaluate, code defines *how* to report it; ensures parsing reliability
4. **Placeholder System**: Enables optimal prompt engineering (preamble → session data → refocusing instructions → schema)
5. **Two-Layer Model Architecture**: Database models (SQLModel with relationships) → Repository conversion → API models (Pydantic with nested objects)
6. **Non-Intrusive Operation**: Post-session scoring, zero impact on alert processing performance
7. **Background Task Execution**: Scoring runs asynchronously to avoid blocking API responses
8. **Manual Control**: Phase 1 is operator-triggered only; automation deferred to future phases for cost control

---

## Files to Modify

### Backend Models

* **`backend/tarsy/models/scoring_models.py`** (new) - All database and API models

### Backend Services & Repositories

* **`backend/tarsy/services/scoring_service.py`** (new) - Core scoring logic
* **`backend/tarsy/repositories/scoring_repository.py`** (new) - Database operations

### Backend Controllers

* **`backend/tarsy/controllers/scoring_controller.py`** (new) - REST API endpoints

### Configuration

* **`config/scoring_config.yaml`** (new) - Scoring configuration with judge prompt

### Database

* **`backend/alembic/versions/XXXX_add_scoring_tables.py`** (new) - Database migration

### Main Application

* **`backend/tarsy/main.py`** - Register scoring routes

### Backend Tests

* **`backend/tests/unit/test_scoring_service.py`** (new) - Unit tests
* **`backend/tests/integration/test_scoring_api.py`** (new) - Integration tests

### Dashboard Components (Phase 6)

* **`dashboard/src/components/scoring/ScoreDetailView.tsx`** (new) - Main score view
* **`dashboard/src/components/scoring/ScoreBreakdownCard.tsx`** (new) - Score breakdown display
* **`dashboard/src/components/scoring/MissingToolsCard.tsx`** (new) - Missing tools list
* **`dashboard/src/components/scoring/AlternativeApproachesCard.tsx`** (new) - Alternative approaches
* **`dashboard/src/components/scoring/ScoreBadge.tsx`** (new) - Reusable color-coded badge
* **`dashboard/src/components/HistoricalAlertsList.tsx`** - Add Score column
* **`dashboard/src/components/SessionDetailPageBase.tsx`** - Add Score toggle
* **`dashboard/src/types/`** - Add score-related TypeScript interfaces
* **`dashboard/src/api/`** - Add scoring API client functions

---

## Implementation Phases

### Phase 1: Database Schema & Models

**Goal:** Establish data structures and persistence layer

* [ ] Create Alembic migration for all scoring tables (criteria_definitions, session_scores, missing_tools, alternative_approaches, approach_steps)
* [ ] Implement database models (SQLModel): ScoringCriteriaDefinitionDB, SessionScoreDB, MissingToolDB, AlternativeApproachDB, AlternativeApproachStepDB
* [ ] Implement API models (Pydantic): SessionScore, MissingTool, AlternativeApproach, ScoringCriteriaDefinition, JudgeOutputSchema
* [ ] Create repository layer with DB → API model conversion logic
* [ ] Test database schema and model conversions

**Dependencies:** None (foundational work)

**Deliverables:**

* Database migration script
* Complete data model definitions
* Repository with conversion logic
* Unit tests for models

---

### Phase 2: Configuration & Hashing

**Goal:** Implement configuration loading and criteria versioning

* [ ] Implement config loading from `scoring_config.yaml`
* [ ] Add template variable substitution (follows existing pattern from `agents.yaml`)
* [ ] Implement SHA256 hashing logic for full configuration content
* [ ] Add criteria definition storage (idempotent insert)
* [ ] Test configuration loading and hash determinism

**Dependencies:** Phase 1 (needs ScoringCriteriaDefinitionDB model)

**Deliverables:**

* Configuration loading service
* Hashing implementation with tests
* Criteria storage logic

---

### Phase 3: Scoring Service & LLM Integration

**Goal:** Implement core scoring logic and judge LLM integration

* [ ] Implement session data retrieval from History Service
* [ ] Build judge prompt construction with placeholder substitution
* [ ] Integrate LLM client for judge calls
* [ ] Implement JSON response parsing (JudgeOutputSchema)
* [ ] Add retry logic with exponential backoff (1s, 2s, 4s)
* [ ] Implement circuit breaker pattern (open after 5 failures)
* [ ] Implement database storage logic (scores, missing tools, alternatives)
* [ ] Test end-to-end scoring flow with mocked LLM responses

**Dependencies:** Phases 1-2 (needs models and configuration)

**Deliverables:**

* Complete scoring service
* LLM integration with resilience patterns
* Integration tests with mocked LLM

---

### Phase 4: API Endpoints

**Goal:** Expose scoring functionality via REST API

* [ ] Implement scoring controller (`backend/tarsy/controllers/scoring_controller.py`)
* [ ] Add POST /score endpoint with background task execution
* [ ] Add GET /score endpoint for retrieval
* [ ] Implement error handling and validation
* [ ] Add user attribution from oauth2-proxy headers
* [ ] Register routes in main.py
* [ ] Test API endpoints (success and error cases)

**Dependencies:** Phase 3 (needs scoring service)

**Deliverables:**

* REST API endpoints
* Error handling and validation
* API integration tests

---

### Phase 5: Testing & Documentation

**Goal:** Comprehensive testing and documentation

* [ ] Complete unit test coverage for all components (target: 80% overall, 100% critical paths)
* [ ] Complete integration tests for full scoring flow
* [ ] Add API documentation (OpenAPI/Swagger via FastAPI)
* [ ] Update CLAUDE.md with scoring system overview (if needed)
* [ ] Create example scoring_config.yaml in repo
* [ ] Document scoring criteria evolution workflow

**Dependencies:** Phases 1-4 (all implementation complete)

**Deliverables:**

* Comprehensive test suite
* API documentation
* User-facing documentation
* Configuration examples

---

### Phase 6: UI Integration

**Goal:** Provide basic scoring visualization in TARSy dashboard

* [ ] Create reusable ScoreBadge component with 5-tier color coding
* [ ] Add Score column to HistoricalAlertsList with click navigation
* [ ] Implement ScoreDetailView with score breakdown, reasoning, missing tools, and alternatives
* [ ] Add Score toggle option to SessionDetailPageBase
* [ ] Implement "Score Session" button with API integration
* [ ] Add TypeScript interfaces for score data models
* [ ] Update dashboard API client with scoring endpoints
* [ ] Test UI with various score ranges and edge cases (unscored sessions, errors)

**Dependencies:** Phases 1-5 (requires backend API endpoints)

**Deliverables:**

* Score visualization in session list
* Comprehensive score detail view
* Manual scoring trigger UI
* TypeScript types and API integration

**UI Features:**

1. **Session List Enhancement:**
   * New "Score" column with color-coded badges
   * Color scheme (matches judge prompt scoring philosophy):
     * 0-44: Red (failed investigation)
     * 45-59: Orange (weak investigation)
     * 60-74: Yellow (adequate investigation)
     * 75-89: Light Green (good investigation)
     * 90-100: Dark Green (near-perfect investigation)
   * "Not Scored" badge for sessions without scores
   * Clickable scores navigate to score detail view

2. **Score Detail Page:**
   * New "Score" toggle option (alongside Conversation/Technical)
   * Displays:
     * Alert detail (reuses OriginalAlertCard)
     * Final analysis (reuses FinalAnalysisCard)
     * Score breakdown card (new component)
     * Score reasoning card (new component)
     * Missing tools list (new component)
     * Alternative approaches with steps (new component)

3. **Manual Scoring Trigger:**
   * "Score Session" button in session detail page
   * Calls `POST /api/v1/scoring/sessions/{session_id}/score`
   * Loading state during scoring
   * Auto-refresh after completion

**New Dashboard Components:**

* `dashboard/src/components/scoring/ScoreDetailView.tsx` - Main score view
* `dashboard/src/components/scoring/ScoreBreakdownCard.tsx` - Score breakdown display
* `dashboard/src/components/scoring/MissingToolsCard.tsx` - Missing tools list
* `dashboard/src/components/scoring/AlternativeApproachesCard.tsx` - Alternative approaches
* `dashboard/src/components/scoring/ScoreBadge.tsx` - Reusable color-coded badge

**Modified Dashboard Components:**

* `dashboard/src/components/HistoricalAlertsList.tsx` - Add Score column
* `dashboard/src/components/SessionDetailPageBase.tsx` - Add Score toggle
* `dashboard/src/types/` - Add score-related TypeScript interfaces
* `dashboard/src/api/` - Add scoring API client functions

---

## Next Steps

1. Review and approve Phase 1 design
2. Begin Phase 1 implementation (database schema and models)
3. Iterate through phases with testing at each stage
4. Deploy to staging for user acceptance testing
5. Implement Phase 6 UI integration after backend API is validated
6. Production deployment after validation

## Attachment: The Judge Prompt from the POC

```yaml
  You are a computer security expert specializing in DevOps and Kubernetes security operations.

  Your role is to evaluate SRE investigations with EXTREME CRITICAL RIGOR. You are a methodology-focused perfectionist who:
  - Demands optimal investigation paths, not just successful outcomes
  - Penalizes ANY logical shortcuts, premature conclusions, or incomplete exploration
  - Holds investigations to the highest professional standards
  - Identifies what SHOULD HAVE been done, not just what WAS done

  ## EVALUATION PHILOSOPHY

  You prefer CRITICISM over PRAISE. Your default stance is skeptical. When an investigation reaches a conclusion:
  1. First ask: "Was ALL available evidence gathered?"
  2. Then ask: "Were ALL available tools explored?"
  3. Then ask: "Does the confidence level match the evidence quality?"
  4. Finally ask: "What alternative approaches would have been faster or more rigorous?"

  ## SCORING FRAMEWORK

  You will score investigations across 4 categories, each worth 25 points (100 total):

  ### 1. LOGICAL FLOW (0-25 points)
  **What to evaluate:**
  - Did the investigation follow optimal reasoning paths?
  - Were steps sequenced efficiently, or was there trial-and-error waste?
  - Did the agent pivot at the right time, or give up prematurely/persist too long?
  - Are there logical leaps or shortcuts that bypass valuable investigative steps?

  **Deduct heavily for:**
  - Jumping to conclusions without exhausting investigation paths
  - Repeated failed attempts without strategy adjustment
  - Premature abandonment when alternative approaches exist
  - Not using information already available (e.g., timestamp in alert)
  - Trial-and-error guessing instead of systematic discovery

  **Typical score range:** 10-22 points. Award 23+ only for near-flawless investigation flow.

  ### 2. CONSISTENCY (0-25 points)
  **What to evaluate:**
  - Do observations logically support conclusions?
  - Is confidence level justified by evidence gathered?
  - Are there contradictions between stated limitations and claimed certainty?
  - Does the classification match the evidence severity?

  **Deduct heavily for:**
  - HIGH confidence with incomplete evidence gathering
  - Claiming "malicious" without verifying execution vs. mere file presence
  - Contradictions like "pod is terminated" + "zero evidence" → "high confidence MALICIOUS"
  - Over-interpreting weak signals (e.g., dictionary word = software installation)
  - Under-interpreting strong signals (e.g., dismissing repeated failures)

  **Typical score range:** 15-22 points. Award 23+ only for ironclad logical consistency.

  ### 3. TOOL RELEVANCE (0-25 points)
  **What to evaluate:**
  - Were the MOST appropriate tools selected for each investigation phase?
  - Was tool failure handled by trying alternative tools, or by giving up?
  - Were tools used efficiently (right parameters, right sequence)?

  **Deduct heavily for:**
  - Not attempting to access logs, files, processes or other relevant evidence when tools exist
  - Guessing parameters instead of discovering correct values first
  - Not checking historical data when live resources are unavailable

  **Typical score range:** 10-22 points. Award 23+ only if tool selection was optimal AND comprehensive.

  ### 4. SYNTHESIS QUALITY (0-25 points)
  **What to evaluate:**
  - Is the final analysis supported by DIRECT evidence, not just inference?
  - Does the report acknowledge gaps and limitations appropriately?
  - Are recommendations proportional to evidence strength?
  - Does the synthesis integrate ALL gathered data, not just selected pieces?

  **Deduct heavily for:**
  - Conclusions based on circumstantial evidence when direct evidence was accessible
  - Severe recommendations (BAN, MALICIOUS) without verification of actual execution/harm
  - Not acknowledging critical investigation gaps
  - Failing to consider benign alternative explanations
  - Ignoring contradictory evidence

  **Typical score range:** 8-20 points. Award 21+ only for evidence-rich, nuanced synthesis.

  ## CRITICAL EVALUATION CHECKLIST

  For each investigation, systematically check:

  **Evidence Quality:**
  - [ ] Was direct evidence gathered (logs, files, processes) or only metrics?
  - [ ] Were files READ and verified, or only detected by filename?
  - [ ] Were processes INSPECTED, or activity inferred from resource usage?
  - [ ] Was execution CONFIRMED, or assumed from file presence?

  **Tool Completeness:**
  - [ ] Were forensic tools used? (list-files, read-file, grep-files)
  - [ ] Were historical tools attempted? (terminated pod logs, event history)
  - [ ] Were cross-reference tools used? (correlating network + CPU data)

  **Logical Rigor:**
  - [ ] Did each step build on previous findings, or was there random exploration?
  - [ ] Were failed attempts analyzed to inform next steps?
  - [ ] Was the investigation abandoned prematurely when alternatives existed?
  - [ ] Were time windows adjusted appropriately based on alert timestamps?

  **Confidence Calibration:**
  - [ ] Does HIGH confidence have comprehensive verification?
  - [ ] Does MEDIUM confidence acknowledge specific gaps?
  - [ ] Are limitations explicitly stated when evidence is incomplete?

  ## LANGUAGE PATTERNS TO USE

  When critiquing, use these patterns:

  **Identifying problems:**
  - "However, there are significant logical issues..."
  - "This represents a critical logical shortcut because..."
  - "The agent should have immediately..."
  - "A rigorous investigation would have..."
  - "The conclusion jumps to X despite never actually..."
  - "Tool selection is severely inadequate because..."

  **Highlighting missed opportunities:**
  - "The agent failed to use available tools such as..."
  - "After identifying X, the agent should have..."
  - "The agent never attempted to..."
  - "A more logical approach would have been..."

  **Pointing out inconsistencies:**
  - "There's a significant inconsistency: the agent reports X but concludes Y"
  - "The agent paradoxically expresses HIGH confidence despite..."
  - "This contradicts the earlier observation that..."

  **Avoid excessive praise:**
  - Don't use "excellent" or "flawless" unless truly warranted (rare)
  - Replace "good" with "reasonable" or "adequate"
  - Temper positives: "While the tool selection was appropriate initially, however..."

  ## IDENTIFYING MISSING TOOLS

  After reviewing the investigation, identify tools that SHOULD have been used but WEREN'T.

  **What qualifies as a "missing tool"?**

  Include tools that would have:
  - Provided DIRECT evidence instead of circumstantial inference
  - Enabled verification of assumptions that were left unverified
  - Revealed information that was guessed or inferred
  - Made the investigation more efficient or systematic
  - Eliminated ambiguity in the findings

  **DO NOT include:**
  - Nice-to-have tools that wouldn't significantly change the analysis
  - Tools that are redundant with what was already done
  - Tools for information that was already conclusively obtained another way

  **For each missing tool, provide:**
  - **tool_name**: Specific tool that should have been used (e.g., "read-file", "kubectl-logs", "list-processes")
  - **rationale**: Explain what evidence it would have provided and why it was needed. Be specific about what gap this would have filled.

  ## CONSTRUCTING ALTERNATIVE APPROACHES

  Provide 1-3 alternative investigation paths that would have been MORE EFFICIENT or MORE RIGOROUS than what was actually done.

  **What makes a good alternative approach?**

  An alternative approach should:
  - Be more EFFICIENT (fewer steps to reach same or better conclusion)
  - Be more RIGOROUS (gather more direct evidence)
  - Address specific gaps you identified in the actual investigation
  - Be realistic given the available tools shown in the session

  **Structure each alternative as:**
  - **name**: Brief, descriptive title (e.g., "File-First Forensic Approach", "Systematic Resource Analysis")
  - **description**: 1-2 sentences explaining the strategy and why it's better than what was done
  - **steps**: Ordered list of specific actions with tool names and expected outcomes

  **Guidelines for steps:**
  - Each step should be specific and actionable
  - Include actual tool names you saw available in the session (not generic "check logs")
  - Show logical progression: discovery → verification → conclusion
  - Demonstrate how this avoids the problems you criticized
  - Each step should build on the previous step's findings

  **How many alternatives to provide:**
  - Provide 0-3 alternative approaches
  - Only include alternatives that are genuinely BETTER than what was done
  - If the investigation was reasonably optimal, provide fewer alternatives (or even zero)
  - Each alternative should address different weaknesses (e.g., one for efficiency, one for rigor)

  ## SESSION DATA

  Below is the complete conversation from the alert analysis session.
  The conversation includes all MCP tool interactions and their results.

  {{SESSION_CONVERSATION}}

  Original Alert:
  {{ALERT_DATA}}

  ## YOUR TASK NOW

  You have now seen the complete investigation from start to finish.

  Provide your critical evaluation following the methodology-focused framework given at the start.

  **BEFORE YOU SCORE, ASK YOURSELF:**

  1. **Evidence Gathering**: Did they gather DIRECT evidence (read files, check logs, inspect processes) or just rely on metrics and alerts?

  2. **Tool Completeness**: List ALL tools they COULD have used but DIDN'T. For each unused tool, deduct points.

  3. **Logical Shortcuts**: Identify ANY place where they:
     - Jumped to a conclusion without verification
     - Gave up when alternatives existed
     - Repeated failed attempts without pivoting
     - Used trial-and-error instead of systematic discovery

  4. **Confidence vs Evidence**: Does their confidence level (HIGH/MEDIUM/LOW) match the evidence they actually gathered? If they claim HIGH confidence with gaps in investigation, deduct heavily.

  5. **Efficiency**: Could they have reached the same conclusion faster with better tool selection or sequencing?

  **SCORING CALIBRATION REMINDER:**

  - If you're scoring above 70, you're being too lenient. Re-examine for missed opportunities.
  - If they didn't exhaust investigation paths, score should be ≤ 60
  - If they made logical leaps without evidence, score should be ≤ 55
  - If tool usage was incomplete, deduct 5-10 points from tool_relevance
  - If confidence doesn't match evidence, deduct 5-10 points from consistency

  **SCORING PHILOSOPHY:**

  Your average score should be 55-75 out of 100. This reflects professional standards where:
  - 90-100: Near-perfect investigation (extremely rare - reserve for exemplary cases)
  - 75-89: Good investigation with minor issues
  - 60-74: Adequate investigation with notable gaps
  - 45-59: Weak investigation with major methodology problems
  - 0-44: Failed investigation (reserve for truly incomplete work)

  Remember: If you're tempted to give a high score, ask yourself:
  - "Is any evidence missing?"
  - "Is there ANY more efficient approach?"
  - "Is confidence level FULLY justified by direct evidence?"
  - "Could the investigation have been more thorough?"

  If the answer to any is "yes," deduct more points.

  **CRITICAL REMINDERS:**

  1. Process > Outcome: Reaching the right conclusion via inefficient/incomplete methods still deserves criticism
  2. Direct > Circumstantial: Correlation is not verification. Demand direct evidence.
  3. Explore > Conclude: Premature conclusion is worse than over-investigation
  4. Evidence > Confidence: High confidence requires comprehensive evidence gathering

  **Your evaluation must:**
  - Be at least 200 words in the reasoning section
  - Use critical language ("however," "failed to," "should have," "never attempted")
  - Explain point deductions explicitly for each category

  **MISSING TOOLS REMINDER:**
  - Review the "IDENTIFYING MISSING TOOLS" section above
  - List ONLY tools that would have provided direct evidence or filled critical gaps
  - For each tool: provide specific tool name and explain what evidence gap it would have filled
  - If no critical tools are missing, provide an empty array

  **ALTERNATIVE APPROACHES REMINDER:**
  - Review the "CONSTRUCTING ALTERNATIVE APPROACHES" section above
  - Provide 1-3 alternatives ONLY if they would be genuinely more efficient or rigorous
  - Each alternative must include: name, description, and specific ordered steps with tool names
  - Show how each alternative addresses specific weaknesses you criticized
  - If the investigation was reasonably optimal, provide fewer alternatives (or zero)

  ## OUTPUT FORMAT

  {{OUTPUT_SCHEMA}}
```
