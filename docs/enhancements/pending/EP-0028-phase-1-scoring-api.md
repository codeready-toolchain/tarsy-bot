# EP-0028 Phase 1: Alert Session Scoring API

**Status:** Pending
**Created:** 2025-12-05
**Phase:** Design

---

## Overview

Add systematic quality assessment for TARSy alert analysis sessions through an LLM-based judge that critically evaluates investigation methodology and provides actionable feedback.

**Core Capabilities:**

1. **Actionable Feedback**:
   * Quantitative total score (0-100) for filtering and tracking
   * Detailed scoring analysis with reasoning
   * Identification of missing MCP tools with rationale
2. **Critical Evaluation**: Methodology-focused assessment with strict standards delivered as freeform analysis
3. **Criteria Tracking**: SHA256 hash of the scoring prompts stored with each score enables detection of scores produced using obsolete criteria
4. **Flexible Storage**: Scoring analyses are stored as free-form text enabling LLMs to process them without being restricted by formal structure
5. **Non-Intrusive**: Post-session scoring with zero impact on alert processing
6. **Manual Control**: Operator-triggered scoring only (Phase 1 scope)

**Primary Use Cases:**

* Agent development feedback and improvement tracking
* MCP server prioritization based on gap analysis

**Scope:** On-demand scoring API for individual sessions via REST endpoints and basic UI integration. Scheduled batch scoring, analytics aggregation and reporting are left for the future.

**POC Reference:** Initial prototype at <https://github.com/metlos/tarsy-response-score> proved judge LLM provides critical scoring even for self-produced analyses.

---

## Configuration

**Judge Prompts:**

For Phase 1, the judge prompts are **hardcoded in Python** (see Attachment section for full prompt text). The prompts support runtime placeholder substitution:

* `{{SESSION_CONVERSATION}}` - Complete conversation from History Service (includes all MCP tool usage). This uses the same data as the `/final-analysis` endpoint.
* `{{ALERT_DATA}}` - Original alert data for reference
* `{{OUTPUT_SCHEMA}}` - Output format instructions (automatically injected by code):
  * For `judge_prompt_score`: "You MUST end your response with a single line containing ONLY the total score as an integer (0-100)"
  * For `judge_prompt_followup_missing_tools`: No special format requirements (freeform text expected)

**Criteria Versioning:**

The system computes a SHA256 hash of BOTH prompts (concatenated) to create a unique `criteria_hash`. This hash:

* Is stored with each score in the database
* Enables detection of scores produced using obsolete criteria when prompts are updated in code
* Allows future comparison and re-scoring with new criteria

**Design Rationale:**

* **Hardcoded Prompts**: Simplifies initial implementation; future phases can externalize to configuration files
* **Multi-Turn Conversation**: Single conversation context enables LLM to reference its own scoring when analyzing missing tools
* **Freeform Text Storage**: Reduces LLM parsing errors compared to strict schemas; enables natural language analysis
* **Number-on-Last-Line Pattern**: Simple, reliable score extraction using regex with minimal complexity
* **Separate Analysis Fields**: Database stores score_analysis and missing_tools_analysis separately, enabling lightweight report generation (load only what's needed)
* **Criteria Hash Tracking**: SHA256 hash enables automatic obsolescence detection

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
  "score_analysis": "The investigation demonstrates adequate methodology with notable gaps in evidence gathering and tool selection.\n\n## Score Breakdown\n\nLogical Flow: 15/25\n- The investigation followed a reasonable path initially\n- However, there were logical shortcuts when pod access failed\n- Should have pivoted to historical data analysis sooner\n\nConsistency: 18/25\n- Observations generally support conclusions\n- Some contradictions between stated limitations and confidence level\n\nTool Relevance: 14/25\n- Initial tool selection was appropriate\n- Failed to explore alternative tools after encountering access restrictions\n- Missing critical forensic tools\n\nSynthesis Quality: 20/25\n- Final analysis integrates most available data\n- Could have been more explicit about gaps\n\nTotal: 67",
  "missing_tools_analysis": "The investigation would have benefited from several additional tools:\n\n1. **list-processes-in-pod**: Would have confirmed whether the suspicious binary was actively running at the time of the alert, providing direct evidence instead of inference from metrics.\n\n2. **read-file-content**: Could have examined the actual malware payload to determine its capabilities and verify the alert classification.\n\n3. **get-pod-events**: Would have provided historical context about pod lifecycle events, helping correlate the alert timing with actual pod activity.",
  "scored_triggered_by": "alice@example.com",
  "scored_at": "2025-12-05T10:30:00Z",
  "is_current_criteria": true
}
```

**Note:** Both `score_analysis` and `missing_tools_analysis` are freeform text fields. The total_score is extracted from the last line of the LLM's scoring response.

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

## Key Design Decisions

1. **Multi-Turn Conversation**: Single conversation context enables LLM to reference its own scoring when analyzing missing tools; reduces repetitive context loading
2. **Freeform Text Storage**: Reduces LLM parsing errors compared to strict JSON schemas; enables natural language analysis and flexibility as criteria evolve
3. **Number-on-Last-Line Pattern**: Simple, reliable score extraction using regex (`r'(\d+)\s*$'`) without JSON parsing complexity
4. **Separate Analysis Fields**: Database stores score_analysis and missing_tools_analysis separately, enabling lightweight report generation (load only what's needed for specific analytics)
5. **LLM-Based Report Aggregation**: For MCP prioritization, aggregate freeform missing_tools_analysis text → feed to LLM → generate actionable reports
6. **Content-Addressed Criteria**: SHA256 hash of BOTH prompts eliminates manual version management and provides automatic obsolescence detection
7. **Minimal Output Schema**: Code only enforces number-on-last-line requirement; prompt defines scoring dimensions (enables criteria evolution without code changes)
8. **Simple Data Model**: No complex relationships or normalization of feedback data
9. **Non-Intrusive Operation**: Post-session scoring, zero impact on alert processing performance
10. **Background Task Execution**: Scoring runs asynchronously to avoid blocking API responses
11. **Manual Control**: Phase 1 is operator-triggered only; automation deferred to future phases for cost control

---

## Implementation Plan

### Phase 1: Database Schema & Models

**Goal:** Establish data structures and persistence layer

* [ ] Create Alembic migration for session_scores table
  * Table name: `session_scores`
  * Columns:
    * `score_id` (UUID, primary key)
    * `session_id` (UUID, unique constraint, foreign key → alert_sessions)
    * `criteria_hash` (VARCHAR 64) - SHA256 hash of hardcoded judge prompts
    * `total_score` (INTEGER, 0-100) - Extracted from last line of score response
    * `score_analysis` (TEXT) - Freeform score breakdown and reasoning
    * `missing_tools_analysis` (TEXT) - Freeform missing tools analysis
    * `scored_triggered_by` (VARCHAR 255) - User from X-Forwarded-User header
    * `scored_at` (TIMESTAMP)
  * Indexes: `session_id`, `criteria_hash`, `total_score`, `scored_at`
  * Forward migration: CREATE TABLE with indexes
  * Rollback migration: DROP TABLE

* [ ] Implement database model (SQLModel): SessionScoreDB
  * Main score record with freeform text fields
  * Maps to session_scores table

* [ ] Implement API model (Pydantic): SessionScore
  * API response model with all database fields
  * Computed field: `is_current_criteria` (boolean)
    * Compares stored `criteria_hash` to current hardcoded prompts hash
    * Current hash computed once at TARSy startup

* [ ] Create repository layer with simple CRUD operations
  * Basic CRUD for session_scores table
  * Hash comparison logic for `is_current_criteria`
  * Database to API model mapping

* [ ] Test database schema and basic model operations
  * Unit tests for model validation
  * Migration up/down testing

**Dependencies:** None (foundational work)

**Deliverables:**

* Database migration script with complete schema
* SQLModel database model (SessionScoreDB)
* Pydantic API model (SessionScore)
* Repository with CRUD and hash comparison
* Unit tests for models and migrations

---

### Phase 2: Hardcoded Prompts & Hashing

**Goal:** Implement hardcoded judge prompts and criteria versioning

* [ ] Hardcode judge prompts as module constants in scoring service
  * Module file: `backend/tarsy/services/scoring_service.py`
  * Constants:
    * `JUDGE_PROMPT_SCORE` - Main scoring evaluation prompt (see Attachment section)
    * `JUDGE_PROMPT_FOLLOWUP_MISSING_TOOLS` - Missing tools analysis prompt
  * Include placeholder support: `{{SESSION_CONVERSATION}}`, `{{ALERT_DATA}}`, `{{OUTPUT_SCHEMA}}`

* [ ] Implement SHA256 hashing logic for BOTH prompts concatenated
  * Concatenate: `JUDGE_PROMPT_SCORE + JUDGE_PROMPT_FOLLOWUP_MISSING_TOOLS`
  * Compute SHA256 hash (deterministic criteria versioning)
  * Hash computed once at TARSy startup (module load time)
  * Store as module-level variable for reuse

* [ ] Test hash determinism and reproducibility
  * Verify same prompts produce same hash
  * Test hash changes when prompts change

**Dependencies:** None (can be done in parallel with Phase 1)

**Deliverables:**

* Hardcoded judge prompt constants with placeholder syntax
* SHA256 hashing implementation with startup computation
* Unit tests for hash determinism

---

### Phase 3: Scoring Service & LLM Integration

**Goal:** Implement core scoring logic and judge LLM integration

* [ ] Implement session data retrieval from History Service
  * Fetch complete session conversation (equivalent to `/final-analysis` endpoint data)

* [ ] Build multi-turn judge prompt construction with placeholder substitution
  * **Turn 1 - Score Prompt:**
    * Start with `JUDGE_PROMPT_SCORE` constant
    * Replace `{{SESSION_CONVERSATION}}` with full conversation from History Service
    * Replace `{{ALERT_DATA}}` with original alert data
    * Replace `{{OUTPUT_SCHEMA}}` with: "You MUST end your response with a single line containing ONLY the total score as an integer (0-100)"
    * Send to LLM, receive score analysis response
  * **Score Extraction:**
    * Extract `total_score` from last line using regex: `r'(\d+)\s*$'`
    * Store full response (minus last line) as `score_analysis`
  * **Turn 2 - Missing Tools Prompt:**
    * Build prompt from `JUDGE_PROMPT_FOLLOWUP_MISSING_TOOLS` constant
    * Send as continuation of conversation (LLM has context of its own scoring)
    * Receive missing tools analysis response
  * **Store Missing Tools:**
    * Store full response as `missing_tools_analysis` (freeform text)

* [ ] Integrate LLM client for multi-turn conversation
  * Use TARSy's default LLM configuration via existing LLM client infrastructure
  * Support conversation history across turns
  * Use LLM client with conversation history support

* [ ] Implement score extraction logic
  * Regex pattern: `r'(\d+)\s*$'` (extracts integer from last line)
  * Validate score is 0-100 range
  * Handle extraction failures with detailed error logging

* [ ] Add retry logic with exponential backoff
  * Max 3 retries with delays: 1s, 2s, 4s
  * Retry on LLM API failures
  * Log retry attempts

* [ ] Implement circuit breaker pattern
  * Open circuit after 5 consecutive failures
  * Prevent cascading failures to LLM service

* [ ] Implement database storage logic
  * Insert single `session_scores` record with:
    * `total_score` (extracted integer)
    * `score_analysis` (freeform text, response minus last line)
    * `missing_tools_analysis` (freeform text from turn 3)
    * `criteria_hash` (from module-level hash)
    * `scored_triggered_by` (user identifier)
    * `scored_at` (timestamp)
  * Return populated `SessionScore` API model
  * Database retry: attempt once on failure, then return 500

* [ ] Implement error handling
  * Score extraction failure: Log raw LLM response, return 500 with details
  * Database failures: Retry once, then return 500
  * Missing session: Return 404
  * LLM API failures: Handled by retry + circuit breaker

* [ ] Test end-to-end scoring flow with mocked LLM responses
  * Mock multi-turn LLM conversation (4 turns)
  * Verify score extraction
  * Test database storage
  * Validate error handling paths

**Dependencies:** Phases 1-2 (needs models and prompts)

**Deliverables:**

* Complete scoring service with 4-turn conversation flow
* LLM integration with conversation history support
* Retry logic with exponential backoff
* Circuit breaker implementation
* Comprehensive error handling
* Integration tests with mocked multi-turn LLM

---

### Phase 4: API Endpoints

**Goal:** Expose scoring functionality via REST API

* [ ] Implement scoring controller (`backend/tarsy/controllers/scoring_controller.py`)
  * Create FastAPI router for scoring endpoints
  * Dependency injection for scoring service and repository

* [ ] Add POST /score endpoint with background task execution
  * Endpoint: `POST /api/v1/scoring/sessions/{session_id}/score`
  * Request body: `{"force_rescore": false}` (optional)
  * Implementation:
    * Check if score exists (unless `force_rescore=true`)
    * If exists and not forcing rescore, return existing score immediately
    * Otherwise, execute scoring via FastAPI `BackgroundTasks`
    * Return score result (immediate if exists, or after background task completion)
  * Error responses:
    * `400 Bad Request` - Session not completed or invalid state
    * `500 Internal Server Error` - LLM API failure or database error

* [ ] Add GET /score endpoint for retrieval
  * Endpoint: `GET /api/v1/scoring/sessions/{session_id}/score`
  * Implementation:
    * Retrieve score from repository
    * Compute `is_current_criteria` by comparing stored hash to current hash
    * Return score with all fields
  * Error responses:
    * `404 Not Found` - Session not found or not yet scored
    * `500 Internal Server Error` - Database error

* [ ] Implement error handling and validation
  * Session existence validation
  * Session completion state validation
  * Proper HTTP status codes for all error cases
  * Detailed error messages for debugging

* [ ] Add user attribution from oauth2-proxy headers
  * Extract user from `X-Forwarded-User` header
  * Pass to scoring service for `scored_triggered_by` field
  * Store in session_scores table for audit trail

* [ ] Register routes in main.py
  * Import scoring controller
  * Add router to FastAPI app
  * Ensure proper route prefix: `/api/v1/scoring`

* [ ] Test API endpoints (success and error cases)
  * Test POST /score with new session
  * Test POST /score with existing score (no force)
  * Test POST /score with force_rescore=true
  * Test GET /score for existing score
  * Test GET /score for non-existent score (404)
  * Test error handling for invalid sessions
  * Test user attribution from headers

**Dependencies:** Phase 3 (needs scoring service)

**Deliverables:**

* Scoring controller with POST and GET endpoints
* FastAPI BackgroundTasks integration
* User attribution from X-Forwarded-User header
* Comprehensive error handling with proper HTTP codes
* Route registration in main.py
* API integration tests covering all scenarios

---

### Phase 5: Testing & Documentation

**Goal:** Comprehensive testing and documentation

* [ ] Complete unit test coverage for all components
  * Model validation (SessionScore, SessionScoreDB)
  * Criteria hash computation (deterministic results for hardcoded prompts)
  * Prompt placeholder substitution (both prompts, all placeholders)
  * Score extraction regex (valid scores, invalid formats, edge cases)
  * Multi-turn conversation flow logic
  * Repository CRUD operations
  * **Coverage targets:**
    * Overall: 80% minimum for new components
    * Critical paths: 100% (scoring logic, score extraction, database operations)

* [ ] Complete integration tests for full scoring flow
  * Full end-to-end: session retrieval → multi-turn LLM conversation → database storage
  * Mock LLM responses for consistency (both scoring and missing tools turns)
  * Re-scoring with `force_rescore=true`
  * Criteria hash obsolescence detection (old vs new criteria)
  * Error handling scenarios:
    * Missing session (404)
    * Score extraction failure (500)
    * Database failures (500)
    * LLM API failures (retry + circuit breaker)

* [ ] Add API documentation (OpenAPI/Swagger via FastAPI)
  * Document all endpoints with request/response schemas
  * Include example requests and responses
  * Document error codes and scenarios

* [ ] Update CLAUDE.md with scoring system overview (if needed)
  * Overview of scoring functionality
  * Link to EP-0028 for details

* [ ] Document scoring criteria evolution workflow
  * How to update judge prompts
  * Impact of criteria hash changes
  * Re-scoring procedures

**Dependencies:** Phases 1-4 (all implementation complete)

**Deliverables:**

* Comprehensive unit test suite (80%+ coverage)
* Complete integration tests (100% critical path coverage)
* OpenAPI/Swagger documentation
* Updated user-facing documentation
* Scoring criteria evolution guide

---

### Phase 6: UI Integration

**Goal:** Provide basic scoring visualization in TARSy dashboard

* [ ] Create reusable ScoreBadge component with 3-tier color coding
* [ ] Add Score column to HistoricalAlertsList with click navigation
* [ ] Implement ScoreDetailView with score analysis and missing tools
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
     * 0-49: Red (failed investigation)
     * 50-74: Yellow (weak investigation)
     * 75-100: Green (good investigation)
   * "Not Scored" badge for sessions without scores
   * Clickable scores navigate to score detail view

2. **Score Detail Page:**
   * New "Score" toggle option (alongside Conversation/Technical)
   * Displays:
     * Alert detail (reuses OriginalAlertCard)
     * Final analysis (reuses FinalAnalysisCard)
     * Score analysis card (breakdown + reasoning)
     * Missing tools list (freeform text)

3. **Manual Scoring Trigger:**
   * "Score Session" button in session detail page
   * Calls `POST /api/v1/scoring/sessions/{session_id}/score`
   * Loading state during scoring
   * Auto-refresh after completion

## Attachment: Judge Prompts (Multi-Turn Conversation)

### Prompt 1: `judge_prompt_score`

```
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
- Be at least 200 words
- Use critical language ("however," "failed to," "should have," "never attempted")
- Explain point deductions explicitly for each category
- Include a score breakdown showing:
  * Logical Flow: X/25
  * Consistency: Y/25
  * Tool Relevance: Z/25
  * Synthesis Quality: W/25

{{OUTPUT_SCHEMA}}
```

### Prompt 2: `judge_prompt_followup_missing_tools`

```
Based on your analysis above, now identify MCP tools that should have been used but weren't.

## IDENTIFYING MISSING TOOLS

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
- **Tool name**: Specific tool that should have been used (e.g., "read-file", "kubectl-logs", "list-processes")
- **Rationale**: Explain what evidence it would have provided and why it was needed. Be specific about what gap this would have filled.

**Format your response as freeform text.** Number each missing tool and provide clear explanations.

If no critical tools are missing, simply state "No critical missing tools identified."
```
