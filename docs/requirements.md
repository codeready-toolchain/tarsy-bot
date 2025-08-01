# Tarsy-bot - Application Requirements

## Executive Summary

Tarsy-bot is an intelligent Site Reliability Engineering system that automates incident response by processing alerts, analyzing runbooks, and performing iterative system diagnostics using AI-powered decision making and Model Context Protocol (MCP) servers. The system implements a multi-layer agent architecture with an orchestrator layer that delegates alert processing to specialized agents based on configurable alert type mappings.

## Document Evolution

This requirements document is a living document that evolves through [Enhancement Proposals (EPs)](enhancements/README.md). All significant changes to system requirements are documented through the EP process, ensuring traceable evolution and AI-friendly implementation.

### Recent Changes
- **EP-0007 (IMPLEMENTED)**: Data Masking Service for Sensitive MCP Server Data - Added pattern-based masking service for secrets and credentials from MCP server responses, with built-in patterns for common secrets and configurable per-server masking rules
- **EP-0006 (IMPLEMENTED)**: Configuration-Based Agents - Added YAML-based agent configuration system allowing deployment of new agents without code changes, supporting both traditional hardcoded agents and configuration-driven agents simultaneously
- **EP-0005 (IMPLEMENTED)**: Flexible Alert Data Structure Support - Transformed rigid Kubernetes-specific alert model into flexible, agent-agnostic system supporting arbitrary JSON payloads with minimal validation
- **EP-0004 (IMPLEMENTED)**: Dashboard UI for Alert History - Added standalone React dashboard for SRE operational monitoring with real-time WebSocket integration and historical alert analysis
- **EP-0003 (IMPLEMENTED)**: Alert Processing History Service - Added comprehensive audit trail capture for all alert processing workflows with database persistence and API endpoints
- **EP-0002 (IMPLEMENTED)**: Multi-Layer Agent Architecture - Transformed monolithic alert processing into orchestrator + specialized agents architecture
- This document was established as the baseline requirements specification
- Future changes will be tracked through Enhancement Proposals in `docs/enhancements/`

For proposed changes or new requirements, see the [Enhancement Proposals directory](enhancements/README.md).

## 1. Core Functional Requirements

### 1.1 Alert Processing and Management

**REQ-1.1.1: Alert Ingestion**
- The system shall accept alerts with flexible JSON data structures
- The system shall require only two mandatory fields:
  - Alert type (from predefined list or agent registry)
  - Runbook URL (GitHub repository URL)
- The system shall support arbitrary additional fields in JSON format:
  - Any monitoring system specific data (Kubernetes, AWS, ArgoCD, Prometheus, etc.)
  - Nested objects, arrays, and complex data structures
  - YAML strings and configuration data
  - Custom metadata from any monitoring source
- The system shall apply default values for common fields:
  - Severity (defaults to "warning" if not provided)
  - Timestamp (auto-generated Unix microseconds if not provided)
  - Environment (defaults to "production" if not provided)

**REQ-1.1.2: Alert Validation**
- The system shall validate all incoming alerts against supported alert types
- The system shall reject alerts with missing mandatory fields
- The system shall validate LLM provider availability before processing alerts
- The system shall generate unique alert IDs for tracking purposes

**REQ-1.1.3: Alert Status Tracking**
- The system shall track alert processing status through states:
  - Queued: Alert received and waiting for processing
  - Processing: Alert being analyzed by specialized agent
  - Completed: Analysis finished successfully
  - Error: Processing failed
- The system shall provide progress percentage (0-100%) for each alert
- The system shall maintain current processing step information
- The system shall include agent identification in processing status

### 1.2 Agent Orchestration and Delegation

**REQ-1.2.1: Orchestrator Layer**
- The system shall implement an orchestrator layer that receives all alerts and delegates processing to specialized agents
- The orchestrator shall use a configurable registry to map alert types to appropriate agent classes
- The orchestrator shall handle agent instantiation and dependency injection
- The orchestrator shall provide unified error handling and progress reporting across all agents

**REQ-1.2.2: Agent Registry**
- The system shall maintain a registry mapping alert types to specialized agent class names
- The registry shall support static configuration-based mappings without requiring code changes
- The registry shall provide clear error messages when no agent is available for a given alert type
- The registry shall be extensible to support new alert types through configuration updates

**REQ-1.2.3: Specialized Agent Architecture**
- The system shall implement specialized agents inheriting from a common base agent class
- The system shall support both traditional hardcoded agents and YAML configuration-based agents simultaneously
- The system shall load agent configurations from filesystem-based YAML file without requiring code changes
- Each agent shall specify its required MCP server subset through abstract method implementation or configuration
- Agents shall process flexible alert data structures without preprocessing
- Agents shall receive complete JSON payloads for intelligent LLM interpretation
- Agents shall support diverse monitoring sources beyond Kubernetes through flexible data handling
- Agents shall implement domain-specific analysis logic while sharing common infrastructure
- Agents shall support three-tier instruction composition: general, MCP server-specific, and agent-specific

### 1.3 Runbook Integration

**REQ-1.3.1: Runbook Retrieval**
- The system shall automatically download runbooks from GitHub repositories
- The system shall authenticate with GitHub using access tokens
- The system shall support public and private repositories
- The system shall handle runbook download failures gracefully

**REQ-1.3.2: Runbook Processing**
- The system shall download runbooks as raw markdown content
- The system shall pass the complete runbook content directly to specialized agents without parsing or extraction
- The system shall preserve the original markdown formatting and structure for LLM analysis
- The system shall distribute runbook content to the selected specialized agent for processing

**REQ-1.3.3: Runbook Configuration**
- The system shall use the runbook URL provided with each alert submission
- The system shall validate that the runbook URL is accessible before processing
- The system shall handle cases where the provided runbook URL is invalid or inaccessible

### 1.4 Intelligent Analysis Engine

**REQ-1.4.1: Multi-LLM Support**
- The system shall support multiple Large Language Model providers:
  - Google Gemini (gemini-2.5-pro)
  - OpenAI GPT (gpt-4-1106-preview)
  - xAI Grok (grok-3)
- The system shall allow configuration of default LLM provider
- The system shall return an error if no LLM provider is available or accessible
- The system shall provide unified LLM access to all specialized agents

**REQ-1.4.2: Agent-Based Iterative Analysis Process**
- The system shall perform iterative analysis through specialized agents with the following phases:
  1. Alert type to agent mapping and agent instantiation
  2. Agent-specific tool selection based on alert and runbook
  3. Data collection using agent's assigned MCP server subset
  4. Partial analysis of collected data by specialized agent
  5. Agent determination of next steps (continue or stop)
  6. Additional tool selection for deeper investigation within agent's domain
  7. Final comprehensive analysis with all collected data

**REQ-1.4.3: Analysis Constraints**
- The system shall limit analysis to maximum 10 iterations by default per agent
- The system shall prevent infinite loops through safety mechanisms in each agent
- The system shall provide configurable iteration limits per agent type

### 1.5 System Data Collection

**REQ-1.5.1: MCP Server Registry and Management**
- The system shall maintain a global registry of all available MCP server configurations
- The system shall support MCP server configuration through environment-based settings
- The system shall validate MCP server configurations at startup
- The system shall provide MCP server lifecycle management (initialization, connection, cleanup)

**REQ-1.5.2: Agent-Specific MCP Server Integration**
- Each specialized agent shall specify its required subset of MCP servers from the global registry
- The system shall configure agents to access only their assigned MCP server subset
- The system shall prevent agents from accessing MCP servers outside their configured subset
- The system shall provide clear error messages when required MCP servers are unavailable for an agent

**REQ-1.5.3: Dynamic Tool Selection**
- The system shall provide only agent-specific available MCP tools to each agent's LLM for intelligent selection
- Specialized agents shall use LLM intelligence to select appropriate tools from their assigned MCP server subset
- Agents shall adapt tool selection based on:
  - Alert context and severity
  - Runbook content and recommendations
  - Agent's available MCP server capabilities
  - Previous iteration findings within the agent's domain

### 1.6 Real-time Communication

**REQ-1.6.1: WebSocket Support**
- The system shall provide real-time progress updates via WebSocket connections
- The system shall support multiple concurrent WebSocket connections
- The system shall handle WebSocket connection failures gracefully
- The system shall provide connection status indicators

**REQ-1.6.2: Agent-Aware Progress Reporting**
- The system shall report processing progress in real-time including agent identification
- The system shall provide detailed step-by-step progress information from specialized agents
- The system shall report completion status and results with agent-specific metadata
- The system shall report error conditions and recovery actions at both orchestrator and agent levels

### 1.7 Alert Processing History and Audit Trail

**REQ-1.7.1: Comprehensive Session Tracking**
- The system shall persistently store all alert processing sessions with complete lifecycle tracking
- The system shall capture session metadata including alert data, agent type, processing status, and timing information
- The system shall support configurable data retention policies through HISTORY_RETENTION_DAYS setting
- The system shall provide unique session identifiers for tracking and correlation

**REQ-1.7.2: LLM Interaction Logging**
- The system shall automatically capture all LLM interactions including prompts, responses, and tool calls
- The system shall record model usage information, token counts, and performance metrics
- The system shall maintain microsecond-precision timestamps for exact chronological ordering
- The system shall generate human-readable step descriptions for each interaction

**REQ-1.7.3: MCP Communication Tracking**
- The system shall automatically log all MCP communications including tool discovery, invocations, and results
- The system shall capture server information, success/failure status, and performance metrics
- The system shall maintain chronological ordering with LLM interactions using microsecond timestamps
- The system shall track tool availability and usage patterns across different MCP servers

**REQ-1.7.4: Historical Data Access**
- The system shall provide REST API endpoints for querying alert processing history
- The system shall support filtering by status, agent type, alert type, and date ranges
- The system shall provide pagination for large datasets
- The system shall support complex filter combinations using AND logic for precise queries

**REQ-1.7.5: Chronological Timeline Reconstruction**
- The system shall reconstruct complete chronological timelines of alert processing workflows
- The system shall merge LLM interactions and MCP communications in precise temporal order
- The system shall provide detailed session information with comprehensive audit trails
- The system shall support both active session monitoring and historical session analysis

## 2. User Interface Requirements

### 2.1 Dashboard UI (SRE Operational Monitoring)

**REQ-2.1.1: Real-time Alert Monitoring**
- The system shall provide a standalone React dashboard for SRE operational monitoring
- The dashboard shall display active alerts with real-time progress indicators and status updates
- The dashboard shall show historical alert processing sessions with comprehensive filtering capabilities
- The dashboard shall support efficient analysis of 1000+ alert sessions with virtual scrolling

**REQ-2.1.2: WebSocket Integration**
- The dashboard shall use multiplexed WebSocket connections for real-time updates
- The system shall provide subscription-based message routing for dashboard updates and session monitoring
- The dashboard shall handle connection failures gracefully with auto-reconnection

**REQ-2.1.3: Historical Analysis Interface**
- The dashboard shall provide timeline visualization of alert processing workflows
- The system shall support filtering by status, agent type, alert type, and date ranges
- The dashboard shall display chronological timelines with LLM interactions and MCP communications
- The system shall provide session detail views with complete audit trails

**REQ-2.1.4: Dashboard Independence**
- The dashboard shall operate as an independent React application in `dashboard/` directory
- The dashboard shall be deployable separately from the alert dev UI
- The system shall maintain clear separation between operational monitoring and development interfaces

### 2.2 Alert Dev UI (Development and Testing)

**REQ-2.2.1: Alert Submission Interface**
- The system shall provide a web-based alert submission form for development and testing purposes
- The form shall include all required alert fields with validation
- The form shall provide dropdown selections for predefined values
- The form shall include helpful placeholders and examples
- The interface shall be used for development, testing, and demonstration purposes only

**REQ-2.2.2: Processing Status Display**
- The system shall display real-time processing status for development and testing
- The system shall show progress bars and percentage completion
- The system shall display current processing step information
- The system shall provide visual indicators for different status states

**REQ-2.2.3: Results Presentation**
- The system shall display analysis results in a readable format for development and testing
- The system shall provide detailed investigation history
- The system shall show all collected data and tool outputs
- The system shall include recommendations and next steps

### 2.3 Production Integration

**REQ-2.3.1: External Client Integration**
- The system shall accept alerts from external monitoring systems (e.g., Alert Manager)
- The system shall provide REST API endpoints for production alert submission
- The system shall support integration with existing incident management workflows
- The system shall handle authentication and authorization for external clients
- The system shall maintain API compatibility while delegating processing to specialized agents

**REQ-2.3.2: API-Based Alert Processing**
- The system shall process alerts submitted via API in production environments through specialized agents
- The system shall provide status endpoints for external clients to query processing progress including agent information
- The system shall return structured responses suitable for automated systems with agent-specific results
- The system shall support webhook notifications for alert processing completion

### 2.4 User Experience

**REQ-2.4.1: Responsive Design**
- The development interface shall be responsive and work on different screen sizes
- The interface shall provide consistent user experience across devices
- The interface shall use modern UI components and styling

**REQ-2.4.2: Error Handling**
- The system shall display clear error messages for user actions in the development interface
- The system shall provide guidance for resolving common issues
- The system shall maintain user-friendly error descriptions

## 3. System Integration Requirements

### 3.1 External Service Integration

**REQ-3.1.1: GitHub Integration**
- The system shall integrate with GitHub API for runbook access
- The system shall support authentication using access tokens
- The system shall handle rate limiting and API errors gracefully
- The system shall provide runbook content to specialized agents without modification

**REQ-3.1.2: LLM Provider Integration**
- The system shall integrate with multiple LLM provider APIs through unified client interface
- The system shall handle API rate limits and quota management
- The system shall return an error when no LLM provider is available or accessible
- The system shall provide consistent LLM access to all specialized agents

### 3.2 Configuration Management

**REQ-3.2.1: Environment Configuration**
- The system shall support environment-based configuration
- The system shall validate required configuration parameters
- The system shall provide secure handling of API keys and tokens
- The system shall support agent registry configuration through environment variables

**REQ-3.2.2: Agent and MCP Server Configuration**
- The system shall maintain agent registry mappings through configuration
- The system shall support MCP server configuration with agent-specific assignments

**REQ-3.2.3: Alert Type Configuration**
- The system shall maintain a list of supported alert types mapped to specialized agents
- The system shall provide an endpoint to return available alert types for UI selection
- The system shall support adding new alert types through agent registry configuration

**REQ-3.2.4: History Service Configuration**
- The system shall support configurable history service through HISTORY_ENABLED setting
- The system shall support configurable database connection through HISTORY_DATABASE_URL setting
- The system shall support configurable data retention through HISTORY_RETENTION_DAYS setting
- The system shall provide graceful degradation when history service is disabled or unavailable

## 4. Performance and Scalability Requirements

### 4.1 Response Time

**REQ-4.1.1: Alert Processing Time**
- The system shall begin processing alerts promptly after submission and agent selection
- The system shall provide regular progress updates during processing by specialized agents
- The system shall strive to complete alert analysis efficiently while ensuring thorough investigation within agent domains

**REQ-4.1.2: Real-time Updates**
- The system shall provide regular progress updates during processing including agent status
- The system shall deliver WebSocket messages promptly with agent-specific information
- The system shall maintain responsive user interface during multi-agent processing

### 4.2 Concurrency

**REQ-4.2.1: Concurrent Alert Processing**
- The system shall support processing multiple alerts simultaneously using different specialized agents
- The system shall isolate processing for different alerts and agent types
- The system shall maintain separate progress tracking for each alert and its assigned agent

**REQ-4.2.2: Resource Management**
- The system shall implement basic resource controls to prevent runaway processing:
  - Maximum iterations per agent per alert (configurable, default: 10)
  - Maximum total tool calls per agent per alert (configurable, default: 20)
  - Maximum data points before stopping (configurable, default: 20, applied after minimum 3 iterations)
- The system shall provide agent-specific MCP server connection lifecycle management
- The system shall rely on default HTTP client and LLM provider configurations for rate limiting

## 5. Security Requirements

### 5.1 Authentication and Authorization

**REQ-5.1.1: API Key Security**
- The system shall securely store and manage API keys
- The system shall not expose API keys in logs or error messages
- The system shall check for API key presence during client initialization
- The system shall handle API key validation failures during actual usage

**REQ-5.1.2: Access Control**
- The system shall handle GitHub token authentication failures during runbook access
- The system shall restrict MCP server access to authorized operations
- The system shall implement secure communication channels

### 5.2 Data Masking and Sensitive Information Protection

#### REQ-5.2.1: MCP Response Masking
- The system shall automatically mask sensitive data in all MCP server responses before LLM processing, logging, or storage
- The system shall apply masking consistently across all MCP servers and agent types
- The system shall use pattern-based detection for common secret types (kubernetes_secret, api_key, password, certificate, token)

#### REQ-5.2.2: Configurable Masking Rules
- The system shall support server-specific masking configurations through YAML configuration and built-in server definitions
- The system shall support built-in pattern groups (basic, secrets, security, kubernetes, all) for common use cases
- The system shall support custom regex patterns for domain-specific sensitive data detection

#### REQ-5.2.3: Fail-Safe Security Behavior
- The system shall implement fail-safe masking behavior that favors over-masking rather than under-masking
- The system shall continue processing when masking encounters errors, applying comprehensive masking to prevent data leaks
- The system shall validate custom regex patterns to prevent configuration errors
## 6. Reliability and Error Handling

### 6.1 Fault Tolerance

**REQ-6.1.1: Graceful Degradation**
- The system shall continue operation when non-critical services fail
- The system shall return an error when LLM services are unavailable as they are critical for core functionality
- The system shall maintain basic functionality during partial system failures that do not affect LLM availability

**REQ-6.1.2: Recovery Mechanisms**
- The system shall automatically retry failed operations where appropriate
- The system shall provide manual recovery options for stuck processes
- The system shall maintain system state across service restarts

### 6.2 Monitoring and Logging

**REQ-6.2.1: Comprehensive Logging**
- The system shall log all major processing steps and decisions
- The system shall log errors with sufficient context for debugging
- The system shall maintain audit trails for security and compliance

**REQ-6.2.2: Health Monitoring**
- The system shall provide health check endpoints
- The system shall provide history service health monitoring through dedicated endpoints
- The system shall monitor database connectivity and service availability

**REQ-6.2.3: Persistent Audit Trails**
- The system shall maintain comprehensive audit trails through the history service
- The system shall store all processing interactions with microsecond precision timing
- The system shall provide complete session lifecycle tracking for debugging and analysis
- The system shall support audit trail queries for operational transparency

## 7. Extensibility Requirements

### 7.1 Agent Architecture Extensibility

**REQ-7.1.1: Agent Plugin Architecture**
- The system shall support adding new specialized agent classes through code deployment (traditional approach)
- The system shall support adding new agents through YAML configuration files without code changes (configuration-based approach)
- The system shall provide a base agent class with common functionality for extension
- The system shall support agent-specific customizations while maintaining common interfaces
- The system shall maintain full backward compatibility between traditional and configuration-based agents

**REQ-7.1.2: MCP Server Extensibility**
- The system shall support adding new MCP servers to the global registry through configuration
- The system shall allow assignment of new MCP servers to existing or new agents through configuration
- The system shall support MCP server-specific instructions embedded in server configurations

**REQ-7.1.3: LLM Provider Extensibility**
- The system shall support adding new LLM providers through configuration
- The system shall provide unified interface for different LLM providers accessible to all agents
- The system shall allow provider-specific optimizations and settings

## 8. Data Flow Requirements

### 8.1 Multi-Layer Alert Processing Flow

**REQ-8.1.1: Processing Sequence**
1. Alert submission and validation
2. Agent selection based on alert type registry mapping
3. Agent instantiation with dependency injection (LLM client, agent-specific MCP servers)
4. Runbook download (raw markdown content) and distribution to selected agent
5. Agent-specific MCP tool discovery from assigned server subset
6. Iterative LLM-driven analysis by specialized agent:
   - Agent-specific tool selection from assigned MCP servers
   - Data collection using agent's MCP server subset
   - Agent-specific partial analysis
   - Agent continuation decision
7. Final comprehensive analysis by specialized agent
8. Result presentation with agent metadata

**REQ-8.1.2: Agent Specialization Flow**
- The system shall route alerts to appropriate specialized agents based on alert type
- Agents shall only access their configured subset of MCP servers
- Agents shall apply domain-specific analysis logic and instructions
- Agents shall provide specialized error handling and recovery within their domain

**REQ-8.1.3: History Capture Flow**
- The system shall automatically create history sessions at alert processing initiation
- The system shall capture all LLM interactions and MCP communications through HookContext integration
- The system shall update session status throughout the processing lifecycle
- The system shall maintain chronological ordering of all interactions with microsecond precision
- The system shall provide real-time access to processing history for active sessions

## 9. Quality Attributes

### 9.1 Usability

**REQ-11.1.1: User Experience**
- The system shall provide intuitive user interface
- The system shall include helpful guidance and examples
- The system shall minimize user effort for common operations

### 9.2 Maintainability

**REQ-9.2.1: Code Quality**
- The system shall maintain clean, well-documented code
- The system shall provide comprehensive error messages
- The system shall support easy debugging and troubleshooting

## 10. Compliance and Standards

### 10.1 Technical Standards

**REQ-10.1.1: Protocol Compliance**
- The system shall comply with Model Context Protocol (MCP) standards
- The system shall use standard HTTP/WebSocket protocols
- The system shall follow REST API best practices

### 10.2 Documentation Standards

**REQ-10.2.1: Documentation Requirements**
- The system shall maintain comprehensive user documentation
- The system shall provide technical architecture documentation
- The system shall include deployment and operation guides