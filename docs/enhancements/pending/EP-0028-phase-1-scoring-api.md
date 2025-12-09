# EP-0028 Phase 1: Alert Session Scoring API

**Status:** Pending
**Created:** 2025-12-05
**Phase:** Design

---

## Overview

This EP describes Phase 1 of the alert session scoring system: implementing a core API for scoring individual TARSy alert analysis sessions using an LLM-based "judge" that critically evaluates analysis quality.

**Scope:** On-demand scoring API for individual sessions. UI integration, scheduled scoring, and insights aggregation are covered in separate future EPs.

## Experimental Background

**Note**: Initial prototype exists at https://github.com/metlos/TARSy-response-score (Go implementation). This EP proposes native integration into TARSy backend.

**Prototype Findings**:
- Judge LLM provides critical scoring even for self-produced analyses
- Input: Complete session conversation from `/final-analysis` endpoint (~25k tokens)
- Output: JSON score report (~6-7KB)
- Context window: Comfortably fits in 1M token window (Pro models) or 32k window (Flash models)
- Scoring consistency: Reliable results across multiple test sessions

## Goals

- Provide API endpoints for scoring individual alert analysis sessions
- Store scores persistently in database
- Enable manual quality assessment of TARSy analyses
- Establish foundation for future UI integration and automation

## Non-Goals (Future Phases)

- UI integration for displaying scores
- Automated/scheduled batch scoring
- Insights aggregation and pattern analysis
- Real-time scoring during alert processing

## System Architecture

### Components

**New Components:**
- **Scoring Service** (`backend/tarsy/services/scoring_service.py`): Core service for session scoring
- **Scoring Models** (`backend/tarsy/models/scoring_models.py`): Pydantic models for scores and judge responses
- **Scoring API Controller** (`backend/tarsy/controllers/scoring_controller.py`): REST endpoints for scoring operations
- **Scoring Repository** (`backend/tarsy/repositories/scoring_repository.py`): Database operations for scores

**Modified Components:**
- **Main Application** (`backend/tarsy/main.py`): Register scoring API routes

**Existing Dependencies:**
- **LLM Client** (`backend/tarsy/integrations/llm_client.py`): Reused for judge LLM calls
- **History Service** (`backend/tarsy/services/history_service.py`): Retrieve complete session data

### Data Flow

1. API receives scoring request for session_id
2. Check if score already exists:
   - If exists: Return existing score (with related missing_tools and alternative_approaches)
   - If not: Continue to step 3
3. Retrieve complete session data from History Service (via `/final-analysis` endpoint logic)
4. Construct judge prompt:
   - Load `judge_prompt` template from config
   - Replace `{{SESSION_CONVERSATION}}` with full conversation (includes tool usage)
   - Replace `{{ALERT_DATA}}` with original alert
   - Replace `{{OUTPUT_SCHEMA}}` with JSON schema specification (from `JudgeOutputSchema`)
5. Send to judge LLM (configurable provider/model)
6. Parse JSON response into structured score model
7. Store score in database:
   - Insert `session_scores` record with score_id, total_score, score_breakdown, etc.
   - Insert `score_missing_tools` records (one per missing tool)
   - Insert `score_alternative_approaches` records (one per alternative)
   - Insert `score_alternative_approach_steps` records (one per step in each alternative)
8. Convert database models to API models (Repository layer)
9. Return score to caller

## Data Design

### Database Schema

**New Table: `scoring_criteria_definitions`**

Stores immutable criteria definitions, content-addressed by hash:

```sql
CREATE TABLE scoring_criteria_definitions (
    criteria_hash VARCHAR(64) PRIMARY KEY,
    criteria_content JSONB NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_scoring_criteria_created ON scoring_criteria_definitions(created_at);
```

**New Table: `session_scores`**

Stores session scores with flexible breakdown structure:

```sql
CREATE TABLE session_scores (
    score_id UUID PRIMARY KEY,
    session_id UUID NOT NULL UNIQUE,
    criteria_hash VARCHAR(64) NOT NULL,

    -- Only total_score is guaranteed to exist
    total_score INTEGER NOT NULL CHECK (total_score >= 0 AND total_score <= 100),

    -- Score dimensions stored flexibly in JSONB (allows criteria evolution)
    score_breakdown JSONB NOT NULL,
    score_reasoning TEXT NOT NULL,

    scored_at TIMESTAMP NOT NULL DEFAULT NOW(),

    FOREIGN KEY (session_id) REFERENCES alert_sessions(session_id) ON DELETE CASCADE,
    FOREIGN KEY (criteria_hash) REFERENCES scoring_criteria_definitions(criteria_hash)
);

CREATE INDEX idx_session_scores_session_id ON session_scores(session_id);
CREATE INDEX idx_session_scores_criteria_hash ON session_scores(criteria_hash);
CREATE INDEX idx_session_scores_total_score ON session_scores(total_score);
CREATE INDEX idx_session_scores_scored_at ON session_scores(scored_at);
```

**New Table: `score_missing_tools`**

Stores tools that should have been used but weren't (normalized for analytics):

```sql
CREATE TABLE score_missing_tools (
    id UUID PRIMARY KEY,
    score_id UUID NOT NULL,
    tool_name VARCHAR(255) NOT NULL,
    rationale TEXT NOT NULL,

    FOREIGN KEY (score_id) REFERENCES session_scores(score_id) ON DELETE CASCADE
);

CREATE INDEX idx_score_missing_tools_score_id ON score_missing_tools(score_id);
CREATE INDEX idx_score_missing_tools_tool_name ON score_missing_tools(tool_name);  -- For aggregation queries
```

**New Table: `score_alternative_approaches`**

Stores alternative investigation approaches suggested by the judge:

```sql
CREATE TABLE score_alternative_approaches (
    id UUID PRIMARY KEY,
    score_id UUID NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,

    FOREIGN KEY (score_id) REFERENCES session_scores(score_id) ON DELETE CASCADE
);

CREATE INDEX idx_score_alt_approaches_score_id ON score_alternative_approaches(score_id);
CREATE INDEX idx_score_alt_approaches_name ON score_alternative_approaches(name);  -- For pattern analysis
```

**New Table: `score_alternative_approach_steps`**

Stores ordered steps for alternative approaches:

```sql
CREATE TABLE score_alternative_approach_steps (
    id UUID PRIMARY KEY,
    approach_id UUID NOT NULL,
    step_order INTEGER NOT NULL,
    step_description TEXT NOT NULL,

    FOREIGN KEY (approach_id) REFERENCES score_alternative_approaches(id) ON DELETE CASCADE
);

CREATE INDEX idx_score_alt_steps_approach_id ON score_alternative_approach_steps(approach_id);
```

**Design Rationale:**

- **Flexible scoring dimensions**: `score_breakdown` JSONB allows criteria to evolve without schema migrations
- **Normalized feedback**: Missing tools and alternative approaches stored relationally for efficient aggregation
- **Future analytics**: Easy queries for "most frequently missing tools" and pattern analysis across sessions
- **Content-addressed criteria**: SHA256 hash uniquely identifies each criteria version
- **Historical preservation**: Full criteria definition stored for each hash
- **Automatic obsolescence**: Compare `criteria_hash` to current config hash to identify outdated scores
- **No manual versioning**: Hash eliminates human error in version management

### Data Models

The system uses a two-layer model architecture:
- **Database Models (SQLModel)**: Map directly to database tables with foreign key relationships
- **API Models (Pydantic)**: Clean response models for REST endpoints with nested objects
- **Conversion**: Repository layer converts database models to API models when reading data

```python
# backend/tarsy/models/scoring_models.py
from sqlmodel import SQLModel, Field, Relationship, Column
from sqlalchemy.dialects.postgresql import JSONB
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from uuid import UUID, uuid4
from datetime import datetime

# ==================== Database Models (SQLModel) ====================

class ScoringCriteriaDefinitionDB(SQLModel, table=True):
    """Immutable criteria definition stored in database."""
    __tablename__ = "scoring_criteria_definitions"

    criteria_hash: str = Field(primary_key=True, max_length=64)
    criteria_content: Dict[str, Any] = Field(sa_column=Column(JSONB))
    created_at: datetime = Field(default_factory=datetime.utcnow)

class SessionScoreDB(SQLModel, table=True):
    """Database model for session scores."""
    __tablename__ = "session_scores"

    score_id: UUID = Field(default_factory=uuid4, primary_key=True)
    session_id: UUID = Field(unique=True)
    criteria_hash: str = Field(foreign_key="scoring_criteria_definitions.criteria_hash")

    total_score: int
    score_breakdown: Dict[str, Any] = Field(sa_column=Column(JSONB))
    score_reasoning: str

    scored_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships (for eager loading)
    missing_tools: List["MissingToolDB"] = Relationship(back_populates="score", cascade_delete=True)
    alternative_approaches: List["AlternativeApproachDB"] = Relationship(back_populates="score", cascade_delete=True)

class MissingToolDB(SQLModel, table=True):
    """Database model for missing tools."""
    __tablename__ = "score_missing_tools"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    score_id: UUID = Field(foreign_key="session_scores.score_id")
    tool_name: str = Field(max_length=255)
    rationale: str

    # Relationship
    score: Optional[SessionScoreDB] = Relationship(back_populates="missing_tools")

class AlternativeApproachDB(SQLModel, table=True):
    """Database model for alternative approaches."""
    __tablename__ = "score_alternative_approaches"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    score_id: UUID = Field(foreign_key="session_scores.score_id")
    name: str = Field(max_length=255)
    description: str

    # Relationships
    score: Optional[SessionScoreDB] = Relationship(back_populates="alternative_approaches")
    steps: List["AlternativeApproachStepDB"] = Relationship(back_populates="approach", cascade_delete=True)

class AlternativeApproachStepDB(SQLModel, table=True):
    """Database model for approach steps."""
    __tablename__ = "score_alternative_approach_steps"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    approach_id: UUID = Field(foreign_key="score_alternative_approaches.id")
    step_order: int
    step_description: str

    # Relationship
    approach: Optional[AlternativeApproachDB] = Relationship(back_populates="steps")

# ==================== API Models (Pydantic) ====================

class MissingTool(BaseModel):
    """API model for missing tools."""
    tool_name: str
    rationale: str

class AlternativeApproach(BaseModel):
    """API model for alternative approaches."""
    name: str
    description: str
    steps: List[str]

class ScoringCriteriaDefinition(BaseModel):
    """API model for criteria definition."""
    criteria_hash: str
    criteria_content: Dict[str, Any]
    created_at: datetime

class SessionScore(BaseModel):
    """API response model for session scores."""
    score_id: UUID
    session_id: UUID
    criteria_hash: str

    total_score: int  # 0-100
    score_breakdown: Dict[str, Any]
    score_reasoning: str
    missing_tools: List[MissingTool]
    alternative_approaches: List[AlternativeApproach]

    scored_at: datetime
    is_current_criteria: Optional[bool] = None  # Computed, not stored

# ==================== Judge LLM Output Schema ====================

class JudgeOutputSchema(BaseModel):
    """
    Strict schema for judge LLM output - defined in code for parsing reliability.
    This schema is injected into the judge prompt at the {{OUTPUT_SCHEMA}} placeholder.
    """
    total_score: int  # 0-100, REQUIRED
    score_breakdown: Dict[str, Any]  # Flexible dimension scores
    score_reasoning: str
    missing_tools: List[Dict[str, str]]  # [{"tool_name": str, "rationale": str}, ...]
    alternative_approaches: List[Dict[str, Any]]  # [{"name": str, "description": str, "steps": List[str]}, ...]

# ==================== Configuration Model ====================

class ScoringConfig(BaseModel):
    """Scoring configuration loaded from YAML."""
    enabled: bool = True
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    judge_prompt: str  # Contains {{OUTPUT_SCHEMA}} placeholder
```

## API Design

### Endpoints

#### 1. Score Session

**Endpoint:** `POST /api/v1/scoring/sessions/{session_id}/score`

**Purpose:** Trigger scoring for a specific session

**Request Body:**
```json
{
  "force_rescore": false  // optional, re-score even if score exists
}
```

**Response (200 OK):**
```json
{
  "score_id": "uuid",
  "session_id": "uuid",
  "criteria_hash": "a3f5b2c1d4e7f9a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9",
  "total_score": 77,
  "score_breakdown": {
    "logical_flow": 18,
    "consistency": 23,
    "tool_relevance": 16,
    "synthesis_quality": 20
  },
  "score_reasoning": "The investigation's overall direction was sound...",
  "missing_tools": [
    {"tool_name": "list-processes-in-pod", "rationale": "..."}
  ],
  "alternative_approaches": [
    {"name": "Systematic File Discovery", "description": "...", "steps": [...]}
  ],
  "scored_at": "2025-12-05T10:00:00Z",
  "is_current_criteria": true
}
```

**Note:** The `score_breakdown` structure is flexible and depends on the criteria definition used. The example above shows a typical breakdown, but the structure may vary as scoring criteria evolve.

**Error Responses:**
- `404 Not Found`: Session not found
- `400 Bad Request`: Invalid session state (not completed)
- `500 Internal Server Error`: LLM API failure or database error

#### 2. Get Session Score

**Endpoint:** `GET /api/v1/scoring/sessions/{session_id}/score`

**Purpose:** Retrieve existing score for a session

**Response (200 OK):** Same as Score Session endpoint

**Error Responses:**
- `404 Not Found`: Session not found or not yet scored

## Scoring Criteria

**Note:** Scoring criteria are defined in the freeform `judge_prompt` field of `config/scoring_config.yaml`. The criteria structure is flexible and can evolve without code changes.

**Example Initial Criteria (from prototype):**

1. **Logical Flow** (0-25 points)
   - Systematic investigation approach
   - Appropriate tool ordering
   - Minimal trial-and-error
   - Precision in operations

2. **Consistency** (0-25 points)
   - Conclusion aligns with evidence
   - No contradictions in reasoning
   - Appropriate confidence levels
   - Corroboration of findings

3. **Tool Relevance** (0-25 points)
   - Optimal tool selection
   - Discovery before assumptions
   - Runtime verification where applicable
   - Comprehensive evidence gathering

4. **Synthesis Quality** (0-25 points)
   - Clear conclusion
   - Acknowledgment of limitations
   - Actionable recommendations
   - Nuanced analysis

**Total Score:** 100 points (sum of all criteria)

**Important:** The only requirement is that the LLM must output `total_score` (0-100). Individual score breakdowns can vary as the criteria evolve.

## Judge Prompt Structure

The judge prompt template is stored in `config/scoring_config.yaml` as a complete, freeform text block with placeholder variables. This design allows maximum flexibility in prompt structure while maintaining consistent output format.

### Placeholder System

The implementation supports the following placeholders in the `judge_prompt`:

**Data Placeholders** (injected with session-specific data):
- `{{SESSION_CONVERSATION}}`: Complete conversation from `/final-analysis` endpoint (includes all MCP tool usage)
- `{{ALERT_DATA}}`: Original alert data for reference

**Output Schema Placeholder** (injected with code-defined JSON schema):
- `{{OUTPUT_SCHEMA}}`: JSON output specification (defined in `JudgeOutputSchema` class)

**Note:** The session conversation already contains the complete list of available MCP tools and their usage throughout the investigation, so no separate tool list placeholder is needed.

### Prompt Structure Flexibility

The placeholder approach enables optimal prompt engineering:
1. **Preamble**: Define evaluation criteria and context upfront
2. **Session Data**: Inject large conversation data via `{{SESSION_CONVERSATION}}`
3. **Post-Session Instructions**: Refocus the LLM after consuming session data
4. **Output Format**: Inject schema specification via `{{OUTPUT_SCHEMA}}`

**Example Prompt Flow:**
```
[Criteria and instructions]
  ↓
{{SESSION_CONVERSATION}} [Large data block]
  ↓
[Refocusing instructions: "Now that you've reviewed the session..."]
  ↓
{{OUTPUT_SCHEMA}} [JSON schema auto-injected by code]
```

### Output Format (Code-Defined)

The `{{OUTPUT_SCHEMA}}` placeholder is automatically replaced with a JSON specification based on `JudgeOutputSchema`:

```json
{
  "total_score": 0-100,
  "score_breakdown": {
    "dimension_name": 0-25,
    ...
  },
  "score_reasoning": "Detailed explanation...",
  "missing_tools": [
    {"tool_name": "tool-name", "rationale": "Why it should have been used..."}
  ],
  "alternative_approaches": [
    {
      "name": "Approach Name",
      "description": "Description...",
      "steps": ["Step 1", "Step 2", ...]
    }
  ]
}
```

**Design Rationale:**
- **Separation of Concerns**: Configuration defines *what* to evaluate, code defines *how* to report it
- **Parsing Reliability**: Output format is guaranteed to match code expectations
- **Prompt Control**: Config authors control narrative flow and refocusing without worrying about schema
- **Consistent Hashing**: Prompt changes are tracked via `criteria_hash`, schema changes require code updates

### Content Hashing

The entire YAML configuration (including the complete prompt template) is hashed to create a unique `criteria_hash`. This hash tracks all changes to evaluation criteria, ensuring full auditability.

## Configuration

**Configuration File:** `config/scoring_config.yaml`

The scoring system uses a YAML configuration file following TARSy's established configuration patterns (similar to `agents.yaml` and `llm_providers.yaml`). This file contains the judge prompt template and scoring parameters. The entire configuration is content-addressed using a hash to track criteria evolution.

**Example Configuration:**

```yaml
# config/scoring_config.yaml

# Scoring service settings (supports template variable substitution)
scoring:
  enabled: ${SCORING_ENABLED:-true}
  llm_provider: ${SCORING_LLM_PROVIDER:-${DEFAULT_LLM_PROVIDER}}
  llm_model: ${SCORING_LLM_MODEL:-}  # Empty = use provider default

# Judge prompt template with placeholders
# The entire configuration (including prompt) is hashed to track criteria evolution
judge_prompt: |
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

**Environment Variables** (optional overrides only):

```bash
# Enable/disable scoring feature (default: true)
SCORING_ENABLED=true

# LLM provider for scoring (default: falls back to DEFAULT_LLM_PROVIDER)
SCORING_LLM_PROVIDER=google-default

# Model for scoring (default: provider-specific default)
SCORING_LLM_MODEL=gemini-2.0-flash-exp
```

**Content Hash Approach:**

The scoring system computes a SHA256 hash of the entire `scoring_config.yaml` file (after template variable resolution). This hash:
- Uniquely identifies each version of scoring criteria
- Enables automatic obsolescence detection
- Eliminates manual version management
- Preserves historical criteria definitions in database

## Security

### Authentication & Authorization

**Authentication**: Handled at infrastructure level by oauth2-proxy (reverse proxy)
- Users authenticated via OAuth (GitHub, Google, etc.) or JWT tokens
- Application trusts `X-Forwarded-User` and `X-Forwarded-Email` headers from oauth2-proxy
- No application-level authentication middleware required

**Authorization**: Not implemented at application level
- All authenticated users have full access to all endpoints
- No role-based access control (RBAC) currently exists
- Authorization is a future enhancement (referenced in EP-0004 as "may be added in future phases")

**User Attribution**:
- User identification extracted from oauth2-proxy headers via `extract_author_from_request()` helper
- Used for audit trails and tracking who triggered scoring operations
- Follows same pattern as alert submission (see `alert_controller.py`)

### Security Controls

- Input validation on all API endpoints (session_id format, request body schema)
- Rate limiting on scoring endpoints to prevent LLM API abuse (implemented at oauth2-proxy/infrastructure level)
- Judge LLM prompts sanitized to prevent prompt injection
- Score data treated with same sensitivity as session data (no additional PII)
- HTTPS/WSS enforced for all communication (infrastructure level)

## Performance & Scalability

### Performance Requirements

- Individual session scoring: < 30 seconds per session (LLM-dependent)
- Score retrieval: < 100ms (database query)
- Support for concurrent scoring requests (up to 10 simultaneous)

### Design Considerations

- Asynchronous scoring using background tasks (FastAPI background tasks)
- Database indexes for efficient score queries

## Error Handling

### Error Handling Strategy

- **LLM API failures**: Retry with exponential backoff (max 3 retries, 1s/2s/4s delays)
- **Invalid JSON responses**: Log raw response, return 500 error with details
- **Missing session data**: Return 404 error
- **Database write failures**: Retry once, then return 500 error

### Resilience Patterns

- Circuit breaker for LLM API calls (open after 5 consecutive failures)
- Graceful degradation: Scoring failures don't affect other system operations
- Comprehensive error logging for debugging

## Testing Strategy

### Unit Tests

- Scoring service score parsing and validation
- LLM prompt construction for scoring
- API endpoint request/response handling
- Database repository CRUD operations
- Error handling for invalid JSON responses

### Integration Tests

- Complete scoring flow from API request to database storage
- LLM integration (mocked responses for consistency)
- History Service integration for session retrieval
- Re-scoring existing session with force_rescore flag

### Test Coverage Target

- Minimum 80% code coverage for new components
- 100% coverage for critical paths (scoring logic, database operations)

## Migration & Deployment

### Database Migration

**Alembic migration script:**

1. Create `scoring_criteria_definitions` table with:
   - Primary key: `criteria_hash`
   - Fields: `criteria_content` (JSONB), `created_at`
   - Index on `created_at`

2. Create `session_scores` table with:
   - Primary key: `score_id` (UUID)
   - Unique constraint on `session_id`
   - Fields: `criteria_hash`, `total_score`, `score_breakdown` (JSONB), `score_reasoning`, `scored_at`
   - Foreign keys to `alert_sessions` and `scoring_criteria_definitions`
   - Indexes on `session_id`, `criteria_hash`, `total_score`, `scored_at`

3. Create `score_missing_tools` table with:
   - Primary key: `id` (UUID)
   - Fields: `score_id`, `tool_name`, `rationale`
   - Foreign key to `session_scores`
   - Indexes on `score_id` and `tool_name`

4. Create `score_alternative_approaches` table with:
   - Primary key: `id` (UUID)
   - Fields: `score_id`, `name`, `description`
   - Foreign key to `session_scores`
   - Indexes on `score_id` and `name`

5. Create `score_alternative_approach_steps` table with:
   - Primary key: `id` (UUID)
   - Fields: `approach_id`, `step_order`, `step_description`
   - Foreign key to `score_alternative_approaches`
   - Index on `approach_id`

**Rollback:**
1. Drop `score_alternative_approach_steps` table
2. Drop `score_alternative_approaches` table
3. Drop `score_missing_tools` table
4. Drop `session_scores` table
5. Drop `scoring_criteria_definitions` table

### Deployment Steps

1. Deploy database schema migration (Alembic)
2. Deploy backend code with scoring service and API endpoints
3. Update environment variables (SCORING_ENABLED, provider, model)
4. Test with sample sessions via API
5. Verify score storage and retrieval
6. Monitor for errors and LLM API usage

### Backward Compatibility

- No breaking changes to existing APIs
- Existing session data unmodified
- Feature flag (SCORING_ENABLED) allows disabling if issues arise
- Scoring is fully optional and doesn't affect alert processing

## Future Analytics Capabilities

The normalized database schema enables analytics queries for future phases. While Phase 1 focuses on the core scoring API, the schema is designed to support insights aggregation and pattern analysis.

### Phase 1 Analytics (Available Immediately)

**Score Trends Over Time:**
```sql
-- Track scoring trends across sessions
SELECT
    DATE(scored_at) as score_date,
    AVG(total_score) as avg_score,
    MIN(total_score) as min_score,
    MAX(total_score) as max_score,
    COUNT(*) as sessions_scored
FROM session_scores
WHERE criteria_hash = '<current_criteria_hash>'
GROUP BY DATE(scored_at)
ORDER BY score_date DESC;
```

**Score Distribution Analysis:**
```sql
-- Analyze score distributions and breakdown patterns
SELECT
    CASE
        WHEN total_score < 50 THEN 'Low (0-49)'
        WHEN total_score < 75 THEN 'Medium (50-74)'
        ELSE 'High (75-100)'
    END as score_range,
    COUNT(*) as session_count,
    AVG((score_breakdown->>'logical_flow')::int) as avg_logical_flow,
    AVG((score_breakdown->>'consistency')::int) as avg_consistency,
    AVG((score_breakdown->>'tool_relevance')::int) as avg_tool_relevance,
    AVG((score_breakdown->>'synthesis_quality')::int) as avg_synthesis_quality
FROM session_scores
WHERE criteria_hash = '<current_criteria_hash>'
GROUP BY score_range
ORDER BY score_range;
```

### Future Phase Analytics (Deferred)

**Semantic Pattern Analysis:**
- Missing tool category clustering (LLM names vary for similar tools)
- Alternative approach pattern discovery (LLM descriptions vary for similar strategies)
- Discovery of most frequently missing tool types
- Common investigation gaps by score range
- **Note:** Deferred to future EP due to need for LLM-based semantic clustering

These analytics will inform:
- **Agent Improvements**: Common investigation gaps and scoring patterns
- **Runbook Quality**: Patterns in alternative approaches that should be documented (future phase)
- **Training Data**: High-quality sessions for fine-tuning future models
- **MCP Server Development**: Which tool categories to prioritize (future clustering phase)

## Monitoring & Observability

### Logging

- Structured logging for all scoring operations (session_id, score, duration)
- LLM request/response logging (truncated to 1000 chars for large responses)
- Error logging for failed scoring attempts with full context

### Metrics

- Total sessions scored (counter)
- Average scoring duration (histogram)
- Scoring success/failure rate (gauge)
- Distribution of scores (histogram)
- API endpoint usage (counter per endpoint)
- LLM API call duration and cost (if available)

## Documentation Requirements

### Code Documentation

- Comprehensive docstrings for ScoringService class and all methods
- Judge prompt template with inline comments
- Scoring criteria version history in CHANGELOG
- API endpoint documentation with request/response examples

### API Documentation

- OpenAPI/Swagger documentation for scoring endpoints (auto-generated via FastAPI)
- Integration guide for future UI developers
- Examples of score JSON structure

### Architecture Documentation

- Updated system architecture diagram including scoring service
- Data flow diagram for scoring process
- Database schema diagram with session_scores table

## Open Questions & Decisions

### Resolved

1. **Scoring Criteria Evolution**: How to handle criteria changes over time?
   - **Decision**: Use content-addressed hashing (SHA256 of `scoring_config.yaml`) to automatically track criteria versions
   - **Rationale**: Eliminates manual version management, provides automatic obsolescence detection, preserves full historical criteria definitions

2. **Criteria Structure**: Should criteria be structured (individual fields) or freeform (text prompt)?
   - **Decision**: Freeform judge prompt with flexible `score_breakdown` JSONB field
   - **Rationale**: Maximum flexibility to iterate on scoring criteria without schema migrations; experimental phase needs adaptability

3. **Score Caching**: Should we cache scores or always allow re-scoring?
   - **Decision**: Store scores permanently with `criteria_hash`, allow re-scoring via `force_rescore` flag
   - **Rationale**: Enables historical tracking and comparison across criteria versions

4. **Cost Controls**: How to prevent runaway LLM costs?
   - **Decision**: Rate limiting on API endpoints, operator-only access (no public endpoint), manual scoring trigger
   - **Rationale**: Phase 1 is manual-trigger only; automation comes in later phases with better cost controls

5. **Database Schema**: Hardcoded score fields vs flexible JSONB?
   - **Decision**: JSONB `score_breakdown` with only `total_score` guaranteed; normalize `missing_tools` and `alternative_approaches`
   - **Rationale**: Criteria dimensions will evolve during experimentation (flexible JSONB), but feedback data (missing tools, alternatives) should be queryable for analytics (normalized tables)

6. **Output Format Location**: Should output format be in config or code?
   - **Decision**: Output format defined in code (`JudgeOutputSchema`), injected via `{{OUTPUT_SCHEMA}}` placeholder
   - **Rationale**: Separation of concerns - config defines evaluation criteria, code defines parsing contract; ensures parsing reliability while allowing prompt flexibility for refocusing after large session data

### Future Considerations (for later phases)

- Bulk scoring capabilities (Phase 3: Scheduled scoring)
- Score display in UI (Phase 2: UI integration)
- Insights aggregation and pattern analysis (Phase 4)
- Materialized views for analytics if structured querying is needed

## Success Criteria

- [ ] Scoring API endpoints deployed and functional
- [ ] Database schema created and migrated
- [ ] Successful scoring of test sessions with realistic data
- [ ] API documentation complete and published
- [ ] Test coverage >= 80%
- [ ] Zero production errors in first week after deployment
- [ ] Scoring latency < 30 seconds (95th percentile)

---

## Implementation Status

**Status:** Pending
**Created:** 2025-12-05
**Next Steps:**
1. Review and approve Phase 1 design
2. Create Alembic migration for all scoring tables (criteria_definitions, session_scores, missing_tools, alternative_approaches, approach_steps)
3. Implement scoring service and models (database and API layers)
4. Implement API endpoints and controller
5. Implement placeholder injection system for judge prompt
6. Write unit and integration tests
7. Deploy to staging environment
8. Conduct user acceptance testing
9. Deploy to production
