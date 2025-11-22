# EP-0028: Response Quality Scoring for TARSy Sessions

**Status:** Pending
**Created:** 2025-11-14

---

## Overview

Add automated quality scoring to TARSy sessions that calculates objective metrics for every investigation. The system automatically evaluates completeness, tool effectiveness, error rates, efficiency, and logical coherence to identify problematic patterns and enable data-driven optimization of prompts, tools, and agent configurations. Logical coherence is evaluated using an LLM-as-judge approach. User feedback collection is planned as a future enhancement but not required for initial implementation.

## Key Architectural Decisions

1. **Automated-First Approach:** Phase 1 focuses on automatic quality metrics calculated on every session completion
2. **Hybrid Metrics:** Combines objective system-calculated scores (completeness, tool effectiveness, error rate, efficiency) with LLM-as-judge assessment (logical coherence)
3. **Session-Level Granularity:** Primary scoring at session level with optional stage-level detail
4. **Automatic Calculation:** Scores computed via hook integration on session completion - zero manual intervention

## Goals (Phase 1: Automated Metrics)

1. **Automated Quality Measurement** - Automatically calculate objective quality metrics for every investigation
2. **Comparative Analysis** - Compare quality across agents, chains, and configurations
3. **Continuous Improvement** - Provide data-driven insights for prompt and configuration optimization
4. **Baseline Establishment** - Create quality baseline before introducing user feedback
5. **Quality Dashboard** - A dashboard to overview the quality metrics based on different criteria with the ability to drill down to individual sessions so that users can figure out what went wrong
6. **Tool Effectiveness Analysis** - Understand how different tools (or lack thereof) contribute to investigation quality, identify underutilized tools, and discover optimal tool usage patterns

## Future Goals (Phase 2: User Feedback)

1. **User Feedback Collection** - Enable SREs to rate and comment on investigation quality
2. **Correlation Analysis** - Compare automated scores with user perceptions
3. **Metric Validation** - Use user feedback to refine automated metric weights

## Use Cases

### Phase 1 Use Cases (Automated Metrics)

1. **Automated Quality Detection**

   ```
   Session completes
   → System automatically calculates metrics:
     - Response completeness (0-100)
     - Tool usage effectiveness (0-100)
     - Error rate score (0-100)
     - Efficiency score (0-100)
     - Logical coherence (0-100, LLM-as-judge)
     - Overall weighted score (0-100)
   → Stores metrics in database
   → Flags low-scoring sessions (< 60)
   → Updates quality trends
   ```

2. **Quality Metrics Dashboard**

   ```
   Manager views quality dashboard
   → Sees average automated scores by agent type
   → Identifies low-scoring patterns
   → Drills down into specific sessions
   → Views metric breakdowns (completeness, tools, errors, efficiency, coherence)
   → Exports quality reports
   ```

3. **Low-Quality Session Review**

   ```
   System identifies low-scoring sessions
   → Generates list sorted by overall score
   → Team investigates common issues
   → Reviews specific metric failures
   → Updates prompts or configurations
   → Re-runs similar alerts to validate improvements
   ```

### Phase 2 Use Cases (User Feedback - Future)

1. **Session Quality Rating**

   ```
   User completes investigation review
   → Clicks "Rate this investigation"
   → Selects 1-5 stars
   → Optionally adds comment
   → System records feedback with timestamp
   → Correlates with automated scores
   ```

2. **Metric Validation**

   ```
   Compare automated scores with user ratings
   → Identify discrepancies
   → Adjust metric weights based on correlation
   → Improve automated scoring accuracy
   ```

### Phase 1d Use Cases (Tool Effectiveness Analysis)

1. **Tool Impact Analysis**

   ```
   Team wants to understand which tools contribute to quality
   → Views Tool Effectiveness Dashboard
   → Sees tools ranked by quality impact
   → Identifies high-impact tools: kubectl.get_logs (+15 quality)
   → Identifies underutilized tools: prometheus.query (used 27% of the time)
   → Reviews sessions that didn't use high-impact tools
   → Updates agent prompts to prioritize effective tools
   ```

2. **Missing Tool Detection**

   ```
   Session completes with low quality score
   → System analyzes tool usage patterns
   → Identifies missing critical tools
   → LLM-as-judge flags: "Should have checked logs but didn't"
   → Session detail shows: ⚠️ Missing recommended tools
   → Team reviews why tools weren't used
   → Adjusts agent instructions to ensure critical tools are considered
   ```

3. **Tool Usage Pattern Discovery**

   ```
   Team reviews quality trends
   → Discovers high-quality pattern (avg 87):
     kubectl.get_pods → kubectl.describe → kubectl.get_logs → prometheus.query
   → Discovers low-quality pattern (avg 45):
     kubectl.get_pods (only)
   → Encodes successful pattern in agent prompts
   → Monitors improvement in subsequent sessions
   ```

4. **Runbook Adherence Tracking**

   ```
   Runbook recommends specific tools: [kubectl.get_logs, prometheus.query]
   → Session investigation only uses kubectl.get_pods
   → Runbook adherence score: 0% (0/2 recommended tools used)
   → Quality score: 52 🔴
   → System flags low adherence
   → Team investigates why runbook wasn't followed
   ```

5. **Tool Retirement Candidates (Low-Value/Harmful Tools)**

   ```
   Team reviews Tool Effectiveness Dashboard
   → Identifies tools with negative quality impact:
     - kubectl.patch_resource: -12 quality impact, 40% failure rate
     - database.slow_query_dump: -8 quality impact, sessions timeout when used
   → Filters by agent type:
     - Tool works well for KubernetesAgent (+5 impact)
     - But hurts DatabaseAgent (-15 impact) ← Configuration issue
   → Filters by alert type:
     - Useful for HighMemory alerts (+10 impact)
     - Harmful for PodCrashLoop alerts (-18 impact) ← Wrong use case
   → Decision paths:
     - Remove tool entirely (if universally harmful)
     - Fix tool implementation (if high failure rate)
     - Restrict to specific agents/alerts (if context-dependent)
     - Update agent prompts to avoid misuse
   ```

---

## Architecture Design

### High-Level Flow (Phase 1: Automated Metrics)

```
┌─────────────────────────────────────────────────┐
│ 1. Session Completion                           │
│    Alert Processing → Final Analysis            │
│    Session reaches terminal state               │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│ 2. Automatic Quality Calculation (Hook)         │
│    Triggered on session completion              │
│    Zero manual intervention                     │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│ 3. Calculate Quality Metrics                    │
│    - Completeness score (0-100)                 │
│    - Tool effectiveness (0-100)                 │
│    - Error rate score (0-100)                   │
│    - Efficiency score (0-100)                   │
│    - Coherence score (0-100, LLM-as-judge)      │
│    - Overall weighted score                     │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│ 4. Store Quality Score                          │
│    Save to session_quality_scores table         │
│    Include calculation metadata                 │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│ 5. Dashboard & Trend Updates                    │
│    Score available via API immediately          │
│    Updated in quality trends                    │
│    Flagged if below low-quality threshold       │
└─────────────────────────────────────────────────┘
```

### Future Flow (Phase 2: User Feedback)

```
┌─────────────────────────────────────────────────┐
│ User Reviews Investigation                      │
│    Clicks "Rate this investigation"             │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│ Submit Rating & Comments                        │
│    1-5 star rating + optional comment           │
│    Optional detailed ratings                    │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│ Store User Feedback                             │
│    Correlate with automated scores              │
│    Use for metric validation                    │
└─────────────────────────────────────────────────┘
```

### Data Model

#### New Database Tables

```python
class SessionQualityScore(SQLModel, table=True):
    """Quality scores and metrics for a completed session."""

    __tablename__ = "session_quality_scores"

    __table_args__ = (
        Index('ix_quality_scores_session_id', 'session_id'),
        Index('ix_quality_scores_created_at', 'created_at_us'),
        Index('ix_quality_scores_overall', 'overall_score'),
    )

    # Identity
    score_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        primary_key=True,
        description="Unique score record identifier"
    )

    # Session relationship
    session_id: str = Field(
        sa_column=Column(String, ForeignKey("alert_sessions.session_id"), index=True),
        description="Session this score applies to"
    )

    # Timestamp
    created_at_us: int = Field(
        default_factory=now_us,
        sa_column=Column(BIGINT),
        description="When this score was recorded"
    )

    # Overall composite score (0-100)
    overall_score: Optional[float] = Field(
        default=None,
        description="Composite quality score (0-100), weighted combination of all metrics"
    )

    # Automated Metrics (0-100 scale)
    completeness_score: Optional[float] = Field(
        default=None,
        description="How complete/thorough the investigation was (0-100)"
    )

    tool_effectiveness_score: Optional[float] = Field(
        default=None,
        description="How effectively tools were used (0-100)"
    )

    error_rate_score: Optional[float] = Field(
        default=None,
        description="Inverse of error rate - higher is better (0-100)"
    )

    efficiency_score: Optional[float] = Field(
        default=None,
        description="Time/iteration efficiency (0-100)"
    )

    coherence_score: Optional[float] = Field(
        default=None,
        description="Logical coherence of the analysis (0-100, LLM-as-judge)"
    )

    # Metadata about scoring
    metrics_version: str = Field(
        default="1.0",
        description="Version of quality metrics algorithm used"
    )

    calculation_metadata: Optional[dict] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Details about how scores were calculated"
    )


class SessionUserFeedback(SQLModel, table=True):
    """
    User-provided feedback and ratings for sessions.

    NOTE: Table created in Phase 1 but NOT USED until Phase 2.
    Schema is defined now to avoid future migrations.
    """

    __tablename__ = "session_user_feedback"

    __table_args__ = (
        Index('ix_user_feedback_session_id', 'session_id'),
        Index('ix_user_feedback_created_at', 'created_at_us'),
        Index('ix_user_feedback_rating', 'rating'),
    )

    # Identity
    feedback_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        primary_key=True,
        description="Unique feedback record identifier"
    )

    # Session relationship
    session_id: str = Field(
        sa_column=Column(String, ForeignKey("alert_sessions.session_id"), index=True),
        description="Session being rated"
    )

    # User rating (1-5 stars)
    rating: int = Field(
        description="User rating: 1 (poor) to 5 (excellent)"
    )

    # Optional feedback categories
    accuracy: Optional[int] = Field(
        default=None,
        description="How accurate was the analysis? (1-5)"
    )

    usefulness: Optional[int] = Field(
        default=None,
        description="How useful was the investigation? (1-5)"
    )

    clarity: Optional[int] = Field(
        default=None,
        description="How clear was the explanation? (1-5)"
    )

    # Text feedback
    comment: Optional[str] = Field(
        default=None,
        description="Optional user comment"
    )

    # Attribution
    author: Optional[str] = Field(
        default=None,
        description="User who provided feedback (null for anonymous)"
    )

    # Timestamp
    created_at_us: int = Field(
        default_factory=now_us,
        sa_column=Column(BIGINT),
        description="When feedback was submitted"
    )

    # Helpful flags (for future use)
    marked_helpful: bool = Field(
        default=False,
        description="Whether this feedback was marked as helpful by team"
    )


class QualityTrend(SQLModel, table=True):
    """Pre-calculated quality trends for efficient dashboard queries."""

    __tablename__ = "quality_trends"

    __table_args__ = (
        Index('ix_quality_trends_time_range', 'time_range_start', 'time_range_end'),
        Index('ix_quality_trends_scope', 'scope_type', 'scope_value'),
    )

    # Identity
    trend_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        primary_key=True,
        description="Unique trend record identifier"
    )

    # Time range for this aggregation
    time_range_start: int = Field(
        sa_column=Column(BIGINT),
        description="Start of time range (microseconds)"
    )

    time_range_end: int = Field(
        sa_column=Column(BIGINT),
        description="End of time range (microseconds)"
    )

    # Scope (what this trend applies to)
    scope_type: str = Field(
        description="Type of scope: 'global', 'chain', 'agent', 'alert_type'"
    )

    scope_value: Optional[str] = Field(
        default=None,
        description="Value for scope (e.g., chain_id, agent_name)"
    )

    # Aggregated statistics
    session_count: int = Field(
        description="Number of sessions in this trend"
    )

    avg_overall_score: Optional[float] = Field(
        default=None,
        description="Average overall quality score"
    )

    avg_user_rating: Optional[float] = Field(
        default=None,
        description="Average user rating (1-5)"
    )

    feedback_count: int = Field(
        default=0,
        description="Number of user feedback submissions"
    )

    # Score breakdowns
    avg_completeness: Optional[float] = Field(default=None)
    avg_tool_effectiveness: Optional[float] = Field(default=None)
    avg_error_rate: Optional[float] = Field(default=None)
    avg_efficiency: Optional[float] = Field(default=None)
    avg_coherence: Optional[float] = Field(default=None)

    # Timestamp
    calculated_at_us: int = Field(
        default_factory=now_us,
        sa_column=Column(BIGINT),
        description="When this trend was calculated"
    )


class ToolQualityMetrics(SQLModel, table=True):
    """
    Quality metrics aggregated per tool type.

    Phase 1d: Tool-level analytics to understand tool effectiveness.
    """

    __tablename__ = "tool_quality_metrics"

    __table_args__ = (
        Index('ix_tool_quality_tool_name', 'tool_name'),
        Index('ix_tool_quality_time_range', 'time_range_start', 'time_range_end'),
    )

    # Identity
    metric_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        primary_key=True,
        description="Unique metric record identifier"
    )

    # Tool identification
    tool_name: str = Field(
        index=True,
        description="Full tool name (e.g., kubectl.get_pods, prometheus.query)"
    )

    # Time range for aggregation
    time_range_start: int = Field(
        sa_column=Column(BIGINT),
        description="Start of aggregation period (microseconds)"
    )

    time_range_end: int = Field(
        sa_column=Column(BIGINT),
        description="End of aggregation period (microseconds)"
    )

    # Usage statistics
    total_calls: int = Field(
        default=0,
        description="Total number of times this tool was called"
    )

    successful_calls: int = Field(
        default=0,
        description="Number of successful tool calls"
    )

    failed_calls: int = Field(
        default=0,
        description="Number of failed tool calls"
    )

    avg_execution_time_ms: Optional[float] = Field(
        default=None,
        description="Average execution time in milliseconds"
    )

    # Quality correlation
    avg_session_quality_when_used: Optional[float] = Field(
        default=None,
        description="Average quality score of sessions that used this tool"
    )

    avg_session_quality_when_not_used: Optional[float] = Field(
        default=None,
        description="Average quality of sessions where tool was available but not used"
    )

    quality_impact: Optional[float] = Field(
        default=None,
        description="Calculated impact: (quality_when_used - quality_when_not_used)"
    )

    # Tool effectiveness indicators
    avg_result_size_bytes: Optional[float] = Field(
        default=None,
        description="Average size of tool results"
    )

    retry_rate: Optional[float] = Field(
        default=None,
        description="Rate of retry attempts (0-1)"
    )

    utilization_rate: Optional[float] = Field(
        default=None,
        description="Rate tool results were referenced in analysis (0-1)"
    )

    # Context
    sessions_with_tool: int = Field(
        default=0,
        description="Number of sessions that used this tool"
    )

    sessions_without_tool: int = Field(
        default=0,
        description="Number of sessions where tool was available but not used"
    )

    # Timestamp
    calculated_at_us: int = Field(
        default_factory=now_us,
        sa_column=Column(BIGINT),
        description="When metrics were calculated"
    )


class ToolSequencePattern(SQLModel, table=True):
    """
    Common tool usage sequences and their quality correlation.

    Phase 1d: Discover high-quality vs low-quality tool usage patterns.
    """

    __tablename__ = "tool_sequence_patterns"

    __table_args__ = (
        Index('ix_tool_sequence_occurrence', 'occurrence_count'),
        Index('ix_tool_sequence_quality', 'avg_quality_score'),
    )

    # Identity
    pattern_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        primary_key=True,
        description="Unique pattern identifier"
    )

    # Tool sequence
    tool_sequence: list[str] = Field(
        sa_column=Column(JSON),
        description="Ordered list of tools in sequence, e.g., ['kubectl.get_pods', 'kubectl.describe', 'kubectl.get_logs']"
    )

    # Pattern statistics
    occurrence_count: int = Field(
        default=0,
        description="Number of sessions using this exact sequence"
    )

    avg_quality_score: Optional[float] = Field(
        default=None,
        description="Average quality score for sessions using this pattern"
    )

    avg_duration_ms: Optional[float] = Field(
        default=None,
        description="Average duration for sessions using this pattern"
    )

    success_rate: Optional[float] = Field(
        default=None,
        description="Rate of successful completion (0-1)"
    )

    # Context
    alert_types: list[str] = Field(
        sa_column=Column(JSON),
        description="Alert types where this pattern appears"
    )

    agent_types: list[str] = Field(
        sa_column=Column(JSON),
        description="Agent types using this pattern"
    )

    # Timestamp
    first_seen_at_us: int = Field(
        sa_column=Column(BIGINT),
        description="First occurrence of this pattern"
    )

    last_seen_at_us: int = Field(
        sa_column=Column(BIGINT),
        description="Most recent occurrence"
    )

    calculated_at_us: int = Field(
        default_factory=now_us,
        sa_column=Column(BIGINT),
        description="When pattern metrics were last calculated"
    )


class MissingToolSuggestion(SQLModel, table=True):
    """
    Track tools that were identified as missing but would have improved investigations.

    Phase 1d: Identify gaps in agent toolsets that are causing low quality.
    """

    __tablename__ = "missing_tool_suggestions"

    __table_args__ = (
        Index('ix_missing_tool_name', 'suggested_tool_name'),
        Index('ix_missing_tool_agent', 'agent_type'),
        Index('ix_missing_tool_count', 'suggestion_count'),
    )

    # Identity
    suggestion_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        primary_key=True,
        description="Unique suggestion record identifier"
    )

    # What was suggested
    suggested_tool_name: str = Field(
        index=True,
        description="Name of the missing tool (e.g., 'database.explain_query')"
    )

    suggested_tool_description: str = Field(
        description="What capability is missing and why it's needed"
    )

    # Context
    agent_type: str = Field(
        index=True,
        description="Agent type that lacked this tool"
    )

    alert_type: str = Field(
        index=True,
        description="Alert type where this tool was needed"
    )

    # Frequency and impact
    suggestion_count: int = Field(
        default=1,
        description="Number of sessions that suggested this tool"
    )

    avg_quality_when_suggested: Optional[float] = Field(
        default=None,
        description="Average quality score of sessions that suggested this tool"
    )

    # Sample reasoning from LLM
    example_reasoning: Optional[str] = Field(
        default=None,
        description="Example reasoning from LLM-as-judge about why this tool was needed"
    )

    # Timestamp
    first_suggested_at_us: int = Field(
        sa_column=Column(BIGINT),
        description="First time this tool was suggested"
    )

    last_suggested_at_us: int = Field(
        sa_column=Column(BIGINT),
        description="Most recent suggestion"
    )

    calculated_at_us: int = Field(
        default_factory=now_us,
        sa_column=Column(BIGINT),
        description="When aggregation was last calculated"
    )
```

---

## Component Design

### 1. Quality Metrics Calculator

Service for calculating automated quality scores:

```python
class QualityMetricsCalculator:
    """
    Calculates automated quality metrics for completed sessions.

    Runs after session completion to generate quality scores based on
    session execution data and LLM-as-judge evaluation.
    """

    def __init__(
        self,
        history_service: HistoryService,
        llm_client: LLMClient
    ):
        self.history_service = history_service
        self.llm_client = llm_client
        self.metrics_version = "1.0"

    async def calculate_session_quality(
        self,
        session_id: str
    ) -> SessionQualityScore:
        """
        Calculate comprehensive quality metrics for a session.

        Returns:
            SessionQualityScore with all calculated metrics
        """
        session = await self.history_service.get_session_details(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        # Calculate individual metric scores
        completeness = self._calculate_completeness(session)
        tool_effectiveness = self._calculate_tool_effectiveness(session)
        error_rate = self._calculate_error_rate(session)
        efficiency = self._calculate_efficiency(session)
        coherence = await self._calculate_coherence(session)

        # Calculate weighted overall score
        overall = self._calculate_overall_score(
            completeness, tool_effectiveness, error_rate, efficiency, coherence
        )

        # Extract tools used in this session
        tools_used = []
        for stage in session.stages:
            for mcp_interaction in stage.mcp_interactions:
                tools_used.append(mcp_interaction.details.tool_name)

        # Get tools available to this session's agent
        # This captures what was available at the time the session ran,
        # allowing accurate historical analysis as toolsets evolve
        tools_available = await self._get_agent_available_tools(session)

        # Parse coherence response for missing tool suggestions
        # (Stored during coherence calculation)
        missing_tools = getattr(self, '_last_missing_tools', [])

        return SessionQualityScore(
            session_id=session_id,
            overall_score=overall,
            completeness_score=completeness,
            tool_effectiveness_score=tool_effectiveness,
            error_rate_score=error_rate,
            efficiency_score=efficiency,
            coherence_score=coherence,
            metrics_version=self.metrics_version,
            calculation_metadata={
                "calculated_at": datetime.utcnow().isoformat(),
                "session_status": session.status,
                "stage_count": len(session.stages),
                "tools_used": list(set(tools_used)),  # Deduplicate
                "tools_available": tools_available,  # Tools available at session time
                "suggested_missing_tools": missing_tools,
            }
        )

    async def _get_agent_available_tools(self, session) -> list[str]:
        """
        Get list of tools that were available to the agent at session time.

        This preserves historical context as agent toolsets evolve over time.
        Can be derived from:
        - Agent configuration
        - MCP server assignments
        - Session metadata if captured at runtime

        Returns:
            List of fully qualified tool names (e.g., "kubectl.get_pods")
        """
        # Implementation will query agent registry or session metadata
        # to determine which MCP tools were available
        # Placeholder for now - actual implementation depends on how
        # agent tool configurations are stored
        return []

    def _calculate_completeness(self, session) -> float:
        """
        Measure investigation completeness (0-100).

        This is a basic sanity check for session completion.
        More nuanced quality aspects (thoroughness, appropriate tool usage,
        analysis quality) are evaluated by the coherence score.

        Factors:
        - Session reached terminal state successfully
        - Final analysis is present (not empty)
        """
        score = 100.0

        # Did the session complete at all?
        if session.status == "failed":
            score -= 50

        # Is there ANY final analysis?
        if not session.final_analysis or len(session.final_analysis.strip()) == 0:
            score -= 50

        return max(0, min(100, score))

    def _calculate_tool_effectiveness(self, session) -> float:
        """
        Measure tool usage effectiveness (0-100).

        Factors:
        - Tool success rate
        - Appropriate tool selection
        - Tool results used in analysis
        - No excessive retries
        """
        score = 100.0
        total_tools = 0
        failed_tools = 0

        for stage in session.stages:
            for mcp_interaction in stage.mcp_interactions:
                total_tools += 1
                if not mcp_interaction.details.success:
                    failed_tools += 1

        if total_tools == 0:
            return 50.0  # Neutral score if no tools used

        # Calculate success rate
        success_rate = (total_tools - failed_tools) / total_tools
        score = success_rate * 100

        return max(0, min(100, score))

    def _calculate_error_rate(self, session) -> float:
        """
        Measure error rate (0-100, higher is better).

        Inverted error rate - fewer errors = higher score.
        """
        total_interactions = 0
        error_count = 0

        for stage in session.stages:
            for llm_interaction in stage.llm_interactions:
                total_interactions += 1
                if not llm_interaction.details.success:
                    error_count += 1

        if total_interactions == 0:
            return 100.0

        error_rate = error_count / total_interactions
        score = (1 - error_rate) * 100

        return max(0, min(100, score))

    def _calculate_efficiency(self, session) -> float:
        """
        Measure investigation efficiency (0-100).

        Factors:
        - Time to completion
        - LLM iterations used vs available
        - Token usage vs complexity
        """
        score = 100.0

        # Penalize very long durations
        if session.duration_ms:
            duration_minutes = session.duration_ms / 60000
            if duration_minutes > 5:
                score -= 20
            elif duration_minutes > 2:
                score -= 10

        # Check iteration efficiency
        total_iterations = sum(
            len(stage.llm_interactions) for stage in session.stages
        )

        # Penalize excessive iterations (likely spinning)
        if total_iterations > 50:
            score -= 30
        elif total_iterations > 30:
            score -= 15

        return max(0, min(100, score))

    async def _calculate_coherence(self, session) -> float:
        """
        Measure logical coherence of the analysis using LLM-as-judge (0-100).

        Uses an LLM to evaluate:
        - Logical flow of reasoning
        - Consistency between observations and conclusions
        - Relevance of tool selections to the problem
        - Quality of final analysis synthesis
        - Absence of contradictions or logical gaps

        The judging LLM receives the FULL investigation context for comprehensive evaluation.
        """
        # Prepare complete investigation context
        full_context = self._prepare_full_investigation_context(session)

        # Construct LLM-as-judge prompt
        evaluation_prompt = f"""You are evaluating the logical coherence of an SRE investigation. Analyze the complete investigation for logical consistency, reasoning quality, and coherence.

{full_context}

Evaluate the investigation on these criteria:

1. **Logical Flow** (0-25 points): Does the investigation follow a logical progression? Are steps ordered sensibly? Does each action logically follow from previous observations?

2. **Consistency** (0-25 points): Are observations and conclusions consistent with each other? Are there contradictions between what tools revealed and what was concluded? Does the reasoning remain consistent throughout?

3. **Tool Relevance** (0-25 points): Were appropriate tools selected for the problem? Do tool calls address the actual issue? Are tool inputs relevant to the stated reasoning? Were tool results properly interpreted?

4. **Synthesis Quality** (0-25 points): Does the final analysis coherently synthesize all findings? Are conclusions justified by the evidence gathered? Is the analysis complete and well-reasoned?

Additionally, identify any missing tool capabilities that would have significantly improved this investigation:

**MISSING_TOOL_CAPABILITIES:** List specific tools or capabilities that the agent lacked but clearly needed for this investigation. Only list capabilities that were obviously needed but absent - not nice-to-haves. Format as a JSON array of objects with "tool_name" and "reason" fields.

Examples of what to include:
- If investigating database issues but couldn't query slow query logs: {{"tool_name": "database.get_slow_queries", "reason": "Needed to identify slow queries causing performance issues"}}
- If investigating network issues but couldn't check firewall rules: {{"tool_name": "network.get_firewall_rules", "reason": "Needed to verify if traffic was being blocked"}}
- If investigating pod crashes but couldn't view previous container logs: {{"tool_name": "kubectl.get_previous_logs", "reason": "Needed to see logs from crashed container before restart"}}

Only list capabilities for tools that DO NOT EXIST in the agent's available toolset. Do not list tools that were available but not used.

Provide your evaluation in this exact format:
LOGICAL_FLOW: <score 0-25>
CONSISTENCY: <score 0-25>
TOOL_RELEVANCE: <score 0-25>
SYNTHESIS_QUALITY: <score 0-25>
TOTAL_SCORE: <sum of above, 0-100>
REASONING: <brief explanation of your scoring decisions>
MISSING_TOOL_CAPABILITIES: <JSON array or empty array []>
"""

        try:
            # Call LLM for evaluation with full context
            response = await self.llm_client.chat_completion(
                messages=[{"role": "user", "content": evaluation_prompt}],
                temperature=0.1,  # Low temperature for consistent evaluation
                max_tokens=1000
            )

            # Parse LLM response to extract score and missing tools
            score = self._parse_coherence_score(response.content)

            # Extract and store missing tool suggestions
            missing_tools = self._extract_missing_tool_suggestions(response.content)
            self._last_missing_tools = missing_tools

            return score

        except Exception as e:
            # If LLM evaluation fails, return neutral score
            logger.warning(f"Failed to calculate coherence score: {e}")
            self._last_missing_tools = []
            return 50.0

    def _prepare_full_investigation_context(self, session) -> str:
        """
        Prepare complete investigation context for coherence evaluation.

        Includes:
        - Full alert details and metadata
        - Complete reasoning chain (all thoughts/actions)
        - All tool calls with inputs and outputs
        - Final analysis
        """
        context_parts = []

        # Alert Information
        context_parts.append("=== ALERT INFORMATION ===")
        context_parts.append(f"Alert Type: {session.alert_type}")
        context_parts.append(f"Alert ID: {session.alert_id}")
        context_parts.append(f"Status: {session.status}")
        context_parts.append(f"Duration: {session.duration_ms}ms")

        # Include full alert payload if available
        if hasattr(session, 'alert_payload') and session.alert_payload:
            import json
            context_parts.append(f"\nAlert Payload:\n{json.dumps(session.alert_payload, indent=2)}")

        context_parts.append("\n=== INVESTIGATION PROCESS ===")

        # Iterate through all stages with complete details
        for stage_idx, stage in enumerate(session.stages, 1):
            context_parts.append(f"\n--- Stage {stage_idx}: {stage.stage_name} ---")

            # Include all LLM interactions (thoughts, actions, observations)
            for llm_idx, llm_interaction in enumerate(stage.llm_interactions, 1):
                context_parts.append(f"\nLLM Interaction {llm_idx}:")

                # Include the full reasoning/thought process
                if llm_interaction.details.response:
                    response_data = llm_interaction.details.response

                    if 'thought' in response_data:
                        context_parts.append(f"  Thought: {response_data['thought']}")

                    if 'action' in response_data:
                        context_parts.append(f"  Action: {response_data['action']}")
                        if 'action_input' in response_data:
                            context_parts.append(f"  Action Input: {response_data['action_input']}")

                    if 'observation' in response_data:
                        context_parts.append(f"  Observation: {response_data['observation']}")

                # Include error information if interaction failed
                if not llm_interaction.details.success and llm_interaction.details.error:
                    context_parts.append(f"  ERROR: {llm_interaction.details.error}")

            # Include all MCP tool calls with full inputs and outputs
            for mcp_idx, mcp_interaction in enumerate(stage.mcp_interactions, 1):
                context_parts.append(f"\nTool Call {mcp_idx}:")
                context_parts.append(f"  Tool: {mcp_interaction.details.tool_name}")

                # Include tool parameters
                if mcp_interaction.details.parameters:
                    import json
                    context_parts.append(f"  Parameters: {json.dumps(mcp_interaction.details.parameters, indent=4)}")

                # Include tool result
                if mcp_interaction.details.success:
                    result = mcp_interaction.details.result
                    # Truncate very long results but keep substantial content
                    result_str = str(result)
                    if len(result_str) > 2000:
                        result_str = result_str[:2000] + "... [truncated]"
                    context_parts.append(f"  Result: {result_str}")
                else:
                    context_parts.append(f"  ERROR: {mcp_interaction.details.error}")

        # Final Analysis
        context_parts.append("\n=== FINAL ANALYSIS ===")
        if session.final_analysis:
            context_parts.append(session.final_analysis)
        else:
            context_parts.append("No final analysis provided")

        return "\n".join(context_parts)

    def _parse_coherence_score(self, llm_response: str) -> float:
        """
        Parse coherence score from LLM evaluation response.

        Looks for TOTAL_SCORE: <number> in the response.
        Falls back to extracting individual scores if total not found.
        """
        import re

        # Try to find TOTAL_SCORE first
        total_match = re.search(r'TOTAL_SCORE:\s*(\d+(?:\.\d+)?)', llm_response)
        if total_match:
            score = float(total_match.group(1))
            return max(0, min(100, score))

        # Fallback: Extract and sum individual scores
        scores = {
            'LOGICAL_FLOW': 0,
            'CONSISTENCY': 0,
            'TOOL_RELEVANCE': 0,
            'SYNTHESIS_QUALITY': 0
        }

        for metric in scores.keys():
            match = re.search(rf'{metric}:\s*(\d+(?:\.\d+)?)', llm_response)
            if match:
                scores[metric] = float(match.group(1))

        total = sum(scores.values())
        return max(0, min(100, total))

    def _extract_missing_tool_suggestions(self, llm_response: str) -> list[dict]:
        """
        Extract missing tool suggestions from LLM evaluation response.

        Looks for MISSING_TOOL_CAPABILITIES: <JSON array> in the response.

        Returns:
            List of dicts with 'tool_name' and 'reason' fields
        """
        import re
        import json

        # Try to find MISSING_TOOL_CAPABILITIES JSON array
        match = re.search(r'MISSING_TOOL_CAPABILITIES:\s*(\[.*?\])', llm_response, re.DOTALL)

        if not match:
            return []

        try:
            suggestions_json = match.group(1)
            suggestions = json.loads(suggestions_json)

            # Validate structure
            if not isinstance(suggestions, list):
                logger.warning("MISSING_TOOL_CAPABILITIES is not a list")
                return []

            # Filter valid suggestions
            valid_suggestions = []
            for suggestion in suggestions:
                if isinstance(suggestion, dict) and 'tool_name' in suggestion and 'reason' in suggestion:
                    valid_suggestions.append({
                        'tool_name': suggestion['tool_name'],
                        'reason': suggestion['reason']
                    })

            return valid_suggestions

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse MISSING_TOOL_CAPABILITIES JSON: {e}")
            return []

    def _calculate_overall_score(
        self,
        completeness: float,
        tool_effectiveness: float,
        error_rate: float,
        efficiency: float,
        coherence: float
    ) -> float:
        """
        Calculate weighted overall score from individual metrics.

        Weights (updated to reflect simplified completeness):
        - Completeness: 10% (basic sanity check only)
        - Tool Effectiveness: 25%
        - Error Rate: 25%
        - Efficiency: 15%
        - Coherence: 25% (LLM-as-judge handles thoroughness)
        """
        overall = (
            completeness * 0.10 +
            tool_effectiveness * 0.25 +
            error_rate * 0.25 +
            efficiency * 0.15 +
            coherence * 0.25
        )

        return round(overall, 2)
```

### 2. Quality Scoring Service

Service for managing quality scores and feedback:

```python
class QualityService:
    """
    Service for managing session quality scores.

    Phase 1: Automated quality metric calculation only
    Phase 2: User feedback collection (methods below marked as Phase 2)
    """

    def __init__(
        self,
        history_service: HistoryService,
        metrics_calculator: QualityMetricsCalculator
    ):
        self.history_service = history_service
        self.metrics_calculator = metrics_calculator

    # Phase 1 Methods

    async def calculate_and_store_quality_scores(
        self,
        session_id: str
    ) -> SessionQualityScore:
        """
        Calculate quality scores for a session and store in database.

        Called automatically when session reaches terminal state.
        """
        # Calculate metrics
        scores = await self.metrics_calculator.calculate_session_quality(session_id)

        # Store in database
        await self.history_service.create_quality_score(scores)

        return scores

    async def get_session_quality_score(
        self,
        session_id: str
    ) -> Optional[SessionQualityScore]:
        """
        Get quality scores for a session.

        Returns:
            SessionQualityScore if exists, None otherwise
        """
        return await self.history_service.get_quality_score_by_session(session_id)

    # Phase 2 Methods (User Feedback - NOT IMPLEMENTED IN PHASE 1)

    async def submit_user_feedback(
        self,
        session_id: str,
        rating: int,
        author: Optional[str] = None,
        accuracy: Optional[int] = None,
        usefulness: Optional[int] = None,
        clarity: Optional[int] = None,
        comment: Optional[str] = None
    ) -> SessionUserFeedback:
        """
        Submit user feedback for a session.

        Args:
            session_id: Session being rated
            rating: Overall rating (1-5)
            author: User providing feedback (None for anonymous)
            accuracy: Optional accuracy rating (1-5)
            usefulness: Optional usefulness rating (1-5)
            clarity: Optional clarity rating (1-5)
            comment: Optional text comment

        Returns:
            Created feedback record
        """
        # Validate rating
        if rating < 1 or rating > 5:
            raise ValueError("Rating must be between 1 and 5")

        # Validate session exists
        session = await self.history_service.get_alert_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        # Create feedback record
        feedback = SessionUserFeedback(
            session_id=session_id,
            rating=rating,
            author=author,
            accuracy=accuracy,
            usefulness=usefulness,
            clarity=clarity,
            comment=comment
        )

        # Store in database
        await self.history_service.create_user_feedback(feedback)

        return feedback

    async def get_session_quality_summary(
        self,
        session_id: str
    ) -> dict:
        """
        Get complete quality summary for a session.

        Includes automated scores and user feedback.
        """
        scores = await self.history_service.get_quality_score_by_session(session_id)
        feedback_list = await self.history_service.get_session_feedback(session_id)

        # Calculate average user rating
        avg_rating = None
        if feedback_list:
            avg_rating = sum(f.rating for f in feedback_list) / len(feedback_list)

        return {
            "session_id": session_id,
            "automated_scores": scores,
            "user_feedback_count": len(feedback_list),
            "average_user_rating": avg_rating,
            "feedback": feedback_list
        }

    async def calculate_quality_trends(
        self,
        time_range_days: int = 30,
        scope_type: str = "global",
        scope_value: Optional[str] = None
    ) -> QualityTrend:
        """
        Calculate quality trends for a time period and scope.

        Args:
            time_range_days: Number of days to analyze
            scope_type: 'global', 'chain', 'agent', 'alert_type'
            scope_value: Value for scope (e.g., chain_id)

        Returns:
            Aggregated quality trend data
        """
        # Calculate time range
        end_time = now_us()
        start_time = end_time - (time_range_days * 24 * 60 * 60 * 1_000_000)

        # Get sessions in range
        sessions = await self.history_service.get_sessions_in_range(
            start_time, end_time, scope_type, scope_value
        )

        # Aggregate scores
        total_sessions = len(sessions)
        scores = []
        feedback = []

        for session in sessions:
            score = await self.history_service.get_quality_score_by_session(session.session_id)
            if score:
                scores.append(score)

            session_feedback = await self.history_service.get_session_feedback(
                session.session_id
            )
            feedback.extend(session_feedback)

        # Calculate averages
        avg_overall = None
        if scores:
            avg_overall = sum(s.overall_score for s in scores if s.overall_score) / len(scores)

        avg_rating = None
        if feedback:
            avg_rating = sum(f.rating for f in feedback) / len(feedback)

        return QualityTrend(
            time_range_start=start_time,
            time_range_end=end_time,
            scope_type=scope_type,
            scope_value=scope_value,
            session_count=total_sessions,
            avg_overall_score=avg_overall,
            avg_user_rating=avg_rating,
            feedback_count=len(feedback)
        )
```

### 3. Quality Hook Integration

Integrate quality scoring into session lifecycle:

```python
# In backend/tarsy/hooks/session_hooks.py

async def on_session_completed(session_id: str):
    """Hook called when session reaches completed status."""

    # Existing completion logic...

    # NEW: Calculate quality scores automatically
    if quality_service:
        try:
            await quality_service.calculate_and_store_quality_scores(session_id)
            logger.info(f"Quality scores calculated for session {session_id}")
        except Exception as e:
            logger.warning(f"Failed to calculate quality scores: {e}")
```

---

## API Endpoints

### Quality Scores

```python
# POST /api/v1/quality/sessions/{session_id}/calculate
# Manually trigger quality score calculation
# Returns: SessionQualityScore

# GET /api/v1/quality/sessions/{session_id}/scores
# Get quality scores for a session
# Returns: SessionQualityScore

# GET /api/v1/quality/sessions/{session_id}/summary
# Get complete quality summary (scores + feedback)
# Returns: { automated_scores, user_feedback_count, average_user_rating, feedback }
```

### User Feedback

```python
# POST /api/v1/quality/sessions/{session_id}/feedback
# Submit user feedback
# Body: { rating: 1-5, accuracy?: 1-5, usefulness?: 1-5, clarity?: 1-5, comment?: string }
# Returns: SessionUserFeedback

# GET /api/v1/quality/sessions/{session_id}/feedback
# Get all feedback for a session
# Returns: List[SessionUserFeedback]

# PATCH /api/v1/quality/feedback/{feedback_id}
# Update existing feedback
# Body: { rating?, comment?, ... }
# Returns: SessionUserFeedback
```

### Quality Trends

```python
# GET /api/v1/quality/trends
# Get quality trends
# Query params: ?days=30&scope=global&scope_value=chain_id
# Returns: QualityTrend

# GET /api/v1/quality/dashboard
# Get quality dashboard data
# Returns: { overall_trends, by_chain, by_agent, recent_low_scores }
```

### Tool Effectiveness (Phase 1d)

```python
# GET /api/v1/quality/tools/effectiveness
# Get tool effectiveness metrics with optional filtering
# Query params:
#   - days=30 (time range)
#   - agent_type=KubernetesAgent (filter by agent type)
#   - alert_type=PodCrashLoop (filter by alert type)
#   - sort_by=quality_impact (sort by: quality_impact, usage_count, failure_rate)
#   - min_impact=-50 (minimum quality impact to include)
#   - max_impact=50 (maximum quality impact to include)
# Returns: List[ToolQualityMetrics] with quality impact per tool
#
# Example use cases:
#   - ?days=30&sort_by=quality_impact&max_impact=-5  (retirement candidates)
#   - ?days=30&agent_type=DatabaseAgent&sort_by=quality_impact  (agent-specific analysis)
#   - ?days=30&alert_type=HighMemory&min_impact=10  (high-impact tools for specific alerts)

# GET /api/v1/quality/tools/{tool_name}/impact
# Get detailed quality impact analysis for specific tool
# Query params:
#   - days=30 (time range)
#   - agent_type=KubernetesAgent (filter by agent type)
#   - alert_type=PodCrashLoop (filter by alert type)
# Returns: {
#   tool_name,
#   avg_quality_when_used,
#   avg_quality_when_not_used,
#   quality_impact,
#   by_agent_type: { KubernetesAgent: {...}, DatabaseAgent: {...} },
#   by_alert_type: { PodCrashLoop: {...}, HighMemory: {...} },
#   usage_stats
# }

# GET /api/v1/quality/tools/missing
# Get aggregated missing tool suggestions
# Query params:
#   - days=30 (time range)
#   - agent_type=DatabaseAgent (filter by agent type)
#   - alert_type=SlowQuery (filter by alert type)
#   - min_suggestion_count=3 (minimum times suggested)
# Returns: List[MissingToolSuggestion] sorted by suggestion_count

# GET /api/v1/quality/tools/patterns
# Get common tool usage patterns
# Query params:
#   - days=30 (time range)
#   - min_quality=80 (minimum average quality)
#   - agent_type=KubernetesAgent (filter by agent type)
#   - alert_type=PodCrashLoop (filter by alert type)
# Returns: List[ToolSequencePattern] with quality correlations

# GET /api/v1/quality/sessions/{session_id}/missing-tools
# Get missing tools identified for a specific session
# Returns: List[{ tool_name, reason }] from calculation_metadata
```

---

## UI/UX Design

### Phase 1 UI (Automated Metrics Only)

#### Session Detail Page - Quality Metrics Display

```
┌───────────────────────────────────────────────────────┐
│ Session Detail - COMPLETED                            │
│                                                       │
│ [Session Header]                                      │
│ [Final Analysis Card]                                 │
│                                                       │
│ ┌─────────────────────────────────────────────────┐   │
│ │ 📊 Quality Metrics (Automated)                  │   │
│ │─────────────────────────────────────────────────│   │
│ │ Overall Score: 87/100 (Excellent) 🟢            │   │
│ │                                                 │   │
│ │ Completeness    ████████████████░░░░  85/100   │   │
│ │ Tool Use        ██████████████████░░  90/100   │   │
│ │ Error Rate      ████████████████████  95/100   │   │
│ │ Efficiency      ████████████░░░░░░░░  75/100   │   │
│ │                                                 │   │
│ │ [View Details ▼]                                │   │
│ │                                                 │   │
│ │ Calculated: 2025-11-14 10:23 UTC                │   │
│ │ Metrics Version: 1.0                            │   │
│ └─────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────┘
```

**Color Coding:**

- 🟢 Green (85-100): Excellent quality
- 🟡 Yellow (60-84): Medium quality
- 🔴 Red (<60): Low quality - needs review

#### Session List with Quality Scores

```
┌───────────────────────────────────────────────────────┐
│ Sessions                                              │
│                                                       │
│ ┌─ Session ────────────────────────────────────────┐  │
│ │ PodCrashLoop • COMPLETED  Quality: 87 🟢         │  │
│ │ my-app-pod crashed in production                 │  │
│ │ 4 stages • 45s • 2 hours ago                     │  │
│ └──────────────────────────────────────────────────┘  │
│                                                       │
│ ┌─ Session ────────────────────────────────────────┐  │
│ │ DatabaseSlow • COMPLETED  Quality: 42 🔴         │  │
│ │ Database queries timing out                      │  │
│ │ 3 stages • 120s • 5 hours ago                    │  │
│ └──────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────┘
```

#### Quality Dashboard (Phase 1c)

```
┌───────────────────────────────────────────────────────┐
│ Quality Dashboard - Last 30 Days                      │
│                                                       │
│ ┌─ Overall Trends ─────────────────────────────────┐ │
│ │ Avg Quality Score: 82/100 (↑ 5% vs last month)  │ │
│ │ Sessions Analyzed: 247                           │ │
│ │ Low Quality Sessions: 23 (9.3%)                  │ │
│ └──────────────────────────────────────────────────┘ │
│                                                       │
│ ┌─ By Chain ───────────────────────────────────────┐ │
│ │ kubernetes-alert: 85/100 🟢                      │ │
│ │ database-alert: 78/100 🟡                        │ │
│ │ network-alert: 91/100 🟢                         │ │
│ └──────────────────────────────────────────────────┘ │
│                                                       │
│ ┌─ By Agent ───────────────────────────────────────┐ │
│ │ KubernetesAgent: 87/100 🟢                       │ │
│ │ DatabaseAgent: 76/100 🟡                         │ │
│ │ NetworkAgent: 92/100 🟢                          │ │
│ └──────────────────────────────────────────────────┘ │
│                                                       │
│ ┌─ Recent Low Scores ──────────────────────────────┐ │
│ │ Session abc123: 42/100 🔴 - Review needed        │ │
│ │ Session def456: 55/100 🔴 - Tool failures        │ │
│ └──────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────┘
```

#### Tool Effectiveness Dashboard (Phase 1d)

```
┌───────────────────────────────────────────────────────┐
│ Tool Effectiveness - Last 30 Days                     │
│                                                       │
│ ┌─ High-Impact Tools ──────────────────────────────┐ │
│ │ kubectl.get_logs          +15 quality    █████   │ │
│ │ prometheus.query          +12 quality    ████    │ │
│ │ kubectl.describe_pod      +10 quality    ████    │ │
│ └──────────────────────────────────────────────────┘ │
│                                                       │
│ ┌─ Tools to Review 🔴 ─────────────────────────────┐ │
│ │ kubectl.patch_resource    -12 quality    40% fail│ │
│ │   [Filter by Agent ▼] [Filter by Alert ▼]       │ │
│ │   • KubernetesAgent: +5 impact 🟢               │ │
│ │   • DatabaseAgent: -15 impact 🔴 ← CONFIG ISSUE │ │
│ │                                                  │ │
│ │ database.slow_query_dump  -8 quality     timeout│ │
│ │   Sessions frequently timeout when using this   │ │
│ │   [View 12 affected sessions →]                 │ │
│ └──────────────────────────────────────────────────┘ │
│                                                       │
│ ┌─ Missing Tools (LLM Suggestions) ────────────────┐ │
│ │ database.explain_query    Suggested 15 times    │ │
│ │   "Needed to identify query performance issues" │ │
│ │   Avg quality when suggested: 52/100 🔴         │ │
│ │                                                  │ │
│ │ kubectl.get_previous_logs  Suggested 8 times    │ │
│ │   "Needed to see logs before container restart" │ │
│ └──────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────┘
```

### Phase 2 UI (User Feedback - Future)

#### Session Detail Page - User Feedback Form

```
┌───────────────────────────────────────────────────────┐
│ Session Detail - COMPLETED                            │
│                                                       │
│ [Quality Metrics Card - shown above]                  │
│                                                       │
│ ┌─────────────────────────────────────────────────┐   │
│ │ ⭐ Rate this Investigation                      │   │
│ │─────────────────────────────────────────────────│   │
│ │ How would you rate this investigation?          │   │
│ │ ☆☆☆☆☆ (hover to select)                        │   │
│ │                                                 │   │
│ │ [Expand for detailed ratings ▼]                 │   │
│ │                                                 │   │
│ │ Optional comment:                               │   │
│ │ ┌───────────────────────────────────────────┐   │   │
│ │ │ Your feedback here...                     │   │   │
│ │ └───────────────────────────────────────────┘   │   │
│ │                                                 │   │
│ │ [Submit] [Cancel]                               │   │
│ └─────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────┘
```

#### Quality Metrics with User Ratings

```
┌───────────────────────────────────────────────────────┐
│ 📊 Quality Metrics                                    │
│─────────────────────────────────────────────────────  │
│ Overall Score: 87/100 (Excellent) 🟢                  │
│                                                       │
│ Completeness    ████████████████░░░░  85/100         │
│ Tool Use        ██████████████████░░  90/100         │
│ Error Rate      ████████████████████  95/100         │
│ Efficiency      ████████████░░░░░░░░  75/100         │
│                                                       │
│ User Rating: ⭐⭐⭐⭐☆ 4.2/5 (3 ratings)              │
│ [View Feedback Comments →]                            │
└───────────────────────────────────────────────────────┘
```

---

## Implementation Plan

### Phase 1a: Automated Quality Scoring (Core Infrastructure)

**Backend:**

1. **Database Migrations:**
   - Create `session_quality_scores` table with all metric fields
   - Create `session_user_feedback` table (schema only, not implemented)
   - Add indexes for efficient querying on scores and session_id

2. **Data Models:**
   - Create `SessionQualityScore` SQLModel with all metric fields
   - Create `SessionUserFeedback` SQLModel (for future use)

3. **Quality Metrics Calculator:**
   - Implement `QualityMetricsCalculator` service
   - Implement individual metric calculations:
     - `_calculate_completeness()` - measures investigation thoroughness
     - `_calculate_tool_effectiveness()` - measures tool success rate
     - `_calculate_error_rate()` - inverted error rate (higher is better)
     - `_calculate_efficiency()` - time and iteration efficiency
   - Implement weighted overall score calculation (configurable weights)

4. **Quality Service:**
   - Implement `QualityService` with core methods:
     - `calculate_and_store_quality_scores()` - main scoring method
     - `get_session_quality_score()` - retrieve scores for session
   - NO user feedback methods in Phase 1

5. **Repository Extensions:**
   - Add quality score CRUD to `HistoryRepository`:
     - `create_quality_score()`
     - `get_quality_score_by_session()`
     - `get_quality_scores_in_range()`

6. **Hook Integration:**
   - Add quality score calculation to session completion hook
   - Ensure automatic calculation on all terminal states (completed, failed, cancelled)
   - Handle errors gracefully - don't block session completion if scoring fails

### Phase 1b: API & Basic Dashboard

**Backend:**

1. **Quality Controller:**
   - Implement REST endpoints for automated scores:
     - `GET /api/v1/quality/sessions/{session_id}/scores` - get scores
     - `POST /api/v1/quality/sessions/{session_id}/calculate` - manual trigger
     - `GET /api/v1/quality/scores/low` - list low-scoring sessions
   - NO feedback endpoints in Phase 1

2. **API Models:**
   - Create request/response Pydantic models for scores
   - Add OpenAPI documentation

**Frontend:**

1. **TypeScript Types:**
   - Add `SessionQualityScore` interface
   - Update `Session` type to include optional quality score
   - Add quality metric display types

2. **Components:**
   - Create `QualityMetrics` display component (read-only)
   - Show metric breakdown (completeness, tools, errors, efficiency)
   - Display overall score with visual indicator (color-coded)

3. **Session Detail Integration:**
   - Add quality metrics display to session detail page
   - Show metric breakdown in expandable section
   - Display calculation metadata (version, timestamp)

4. **Dashboard Integration:**
   - Add quality score column to session list (overall score)
   - Add color coding for low/medium/high quality
   - Add filter for low-quality sessions

### Phase 1c: Trend Analysis & Reporting

**Backend:**

1. **Database Migrations:**
   - Create `quality_trends` table for pre-calculated aggregations

2. **Trend Service:**
   - Implement `calculate_quality_trends()` for time-based aggregations
   - Add periodic trend aggregation background task
   - Support aggregation by: global, chain, agent, alert_type

3. **Analytics Queries:**
   - Implement quality score filtering
   - Add quality-based session search
   - Create quality comparison queries (compare agents, chains)

**Frontend:**

1. **Quality Dashboard:**
   - Create dedicated quality dashboard page
   - Show overall trends (line chart over time)
   - Show breakdown by chain/agent (bar charts)
   - List recent low-scoring sessions
   - Show metric distribution histograms

2. **Reporting:**
   - Export quality reports (CSV)
   - Quality trend graphs
   - Low-quality session alerts

### Phase 2: User Feedback (Future Enhancement)

**Backend:**

1. **Implement User Feedback:**
   - Add `submit_user_feedback()` to `QualityService`
   - Add feedback CRUD to `HistoryRepository`
   - Create feedback REST endpoints

**Frontend:**

1. **Feedback Components:**
   - Create `QualityRating` component (star rating)
   - Create `FeedbackForm` component
   - Add feedback submission to session detail

2. **Feedback Analysis:**
   - Compare automated scores with user ratings
   - Identify discrepancies
   - Use feedback to refine metric weights

---

## Configuration

### Environment Variables

```bash
# Quality scoring configuration (Phase 1)
QUALITY_SCORING_ENABLED=true                    # Enable/disable quality scoring
QUALITY_AUTO_CALCULATE=true                     # Auto-calculate on session completion
QUALITY_METRICS_VERSION=1.0                     # Metrics algorithm version

# Quality thresholds
QUALITY_LOW_SCORE_THRESHOLD=60                  # Threshold for low quality alerts
QUALITY_MEDIUM_SCORE_THRESHOLD=75               # Threshold for medium quality
QUALITY_HIGH_SCORE_THRESHOLD=85                 # Threshold for high quality

# Future (Phase 2) - User feedback configuration
# QUALITY_FEEDBACK_ANONYMOUS=true               # Allow anonymous feedback
# QUALITY_MIN_FEEDBACK_RATING=1                 # Minimum feedback rating
# QUALITY_MAX_FEEDBACK_RATING=5                 # Maximum feedback rating
```

### Metrics Configuration

Quality metrics can be customized via configuration:

```yaml
# config/quality_metrics.yaml
quality_metrics:
  version: "1.0"

  overall_weights:
    completeness: 0.10        # Basic sanity check only
    tool_effectiveness: 0.25
    error_rate: 0.25
    efficiency: 0.15
    coherence: 0.25           # LLM-as-judge handles thoroughness

  thresholds:
    low_quality: 60
    medium_quality: 75
    high_quality: 85

  efficiency:
    max_acceptable_duration_minutes: 5
    warning_duration_minutes: 2
    max_acceptable_iterations: 30
```

---

## Benefits

### Phase 1 Benefits (Automated Metrics)

1. **Objective Quality Measurement:** Quantify investigation quality using consistent, measurable criteria
2. **Automatic Problem Detection:** Identify low-quality investigations without manual review
3. **Performance Monitoring:** Track quality trends over time automatically
4. **Configuration Validation:** Validate impact of agent/prompt changes with objective data
5. **Agent Comparison:** Compare quality across different agents, chains, and alert types
6. **Zero Manual Effort:** Quality scoring happens automatically - no user action required
7. **Historical Baseline:** Establish quality baseline before introducing user feedback

### Future Benefits (User Feedback - Phase 2)

1. **User Satisfaction Tracking:** Measure and improve SRE satisfaction with investigations
2. **Metric Validation:** Correlate automated scores with user perceptions
3. **Continuous Learning:** Build dataset for future ML-based quality improvements

---

## Future Enhancements

### Beyond Phase 2

- **Machine learning-based quality prediction** - Predict investigation quality before completion
- **Automated low-quality investigation retry** - Automatically re-run low-scoring investigations with different configurations
- **Quality-based agent routing** - Route alerts to agents with best quality scores for that alert type
- **Comparative A/B testing** - Built-in A/B testing framework for agent configurations
- **Quality score sharing via external APIs** - Expose quality data to incident management platforms
- **Integration with incident management platforms** - Push quality scores to PagerDuty, Opsgenie, etc.
- **Real-time quality alerts** - Alert team when quality scores drop below thresholds
- **Quality-based model selection** - Automatically select best LLM model based on quality/cost trade-offs
