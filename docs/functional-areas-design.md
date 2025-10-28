# TARSy System Design - Functional Areas Overview

**Version**: 1.0  
**Last Updated**: 2025-08-19  
**Purpose**: Modular system understanding guide for targeted improvements

---

## Introduction

This document provides a functional area breakdown of the TARSy system, enabling engineers to understand and work on specific parts of the system without needing to comprehend the entire codebase. Each section focuses on a distinct functional area with clear boundaries and responsibilities.

**How to Use This Document:**
- Start with the [High-Level System Overview](#high-level-system-overview) for context
- Jump to specific functional areas based on what you're working on
- Each area includes core concepts, key components, and integration points
- Cross-references help you understand dependencies between areas

---

## High-Level System Overview

TARSy is an AI-powered incident analysis system that processes alerts through sequential chains of specialized agents. The system automatically selects appropriate chains, executes multiple stages where agents build upon each other's work, and provides comprehensive analysis and recommendations.

**Core Flow**: Alert → Chain Selection → Sequential Agent Execution → Analysis & Recommendations → Dashboard Display

---

## Table of Contents

### Foundation Layer
- [1. Alert Processing & Orchestration](#1-alert-processing--orchestration)
  - [Background Processing & Concurrency Management](#background-processing--concurrency-management)
- [2. Configuration Management](#2-configuration-management)

### Core Processing Pipeline  
- [3. Chain Management & Execution](#3-chain-management--execution)
- [4. Agent Architecture & Strategy System](#4-agent-architecture--strategy-system)
- [5. MCP Integration & Tool Management](#5-mcp-integration--tool-management)
- [6. LLM Integration & Multi-Provider Support](#6-llm-integration--multi-provider-support)

### Event Capture & Observability
- [7. Hook System & Event-Driven Architecture](#7-hook-system--event-driven-architecture)
- [8. History & Audit Trail](#8-history--audit-trail)
- [9. Dashboard & Real-time Monitoring](#9-dashboard--real-time-monitoring)
  - [WebSocket & Real-time Communication Architecture](#websocket--real-time-communication-architecture)

### Cross-Cutting Concerns
- [10. Security & Data Protection](#10-security--data-protection)
- [11. Authentication & Access Control](#11-authentication--access-control)

---

## Functional Areas

### 1. Alert Processing & Orchestration
**Purpose**: Core workflow management from alert receipt to completion  
**Key Responsibility**: Coordinating the entire alert processing pipeline

TARSy accepts alerts from any monitoring system through a flexible REST API, validates them, and coordinates the entire processing workflow. The system uses async background processing with sophisticated concurrency control. Multi-replica deployments are supported via PostgreSQL LISTEN/NOTIFY eventing and pod-level session tracking.

#### Core Alert Flow

```mermaid
sequenceDiagram
    participant Client as Monitoring System
    participant API as FastAPI (/alerts)
    participant Val as Validation Layer
    participant BG as Background Processor
    participant AS as AlertService
    
    Client->>API: POST /alerts (JSON payload)
    API->>Val: Validate & sanitize
    Val->>API: Alert model + ChainContext
    API->>API: Generate session_id (UUID)
    API->>BG: Create background task
    API-->>Client: 200 OK (session_id, status: "queued")
    
    BG->>AS: async process_alert()
    AS->>AS: Select chain & execute stages
    AS-->>BG: Processing complete
```

#### Key Components

**📍 Main Entry Point**: `backend/tarsy/main.py`
- **Alert endpoint**: `POST /alerts` with comprehensive validation
- **Alert model**: Simple, flexible structure (see `backend/tarsy/models/alert.py`)
```python
class Alert(BaseModel):
    alert_type: str               # Required - determines chain selection
    runbook: Optional[str]        # Optional - GitHub runbook URL (uses built-in default if not provided)
    data: Dict[str, Any]          # Flexible JSON payload
    severity: Optional[str]       # Defaults to "warning"
    timestamp: Optional[int]      # Defaults to current time (microseconds)
```

**📍 Core Service**: `backend/tarsy/services/alert_service.py`
- Orchestrates all system components (Chain Registry, Agent Factory, MCP Client, LLM Manager)
- Handles chain selection and stage execution
- Manages runbook downloading and distribution

#### Background Processing & Concurrency Management

**Concurrency Control**:
```python
# From main.py startup
alert_processing_semaphore = asyncio.Semaphore(settings.max_concurrent_alerts)

# In background processor
async with alert_processing_semaphore:
    await alert_service.process_alert(alert, session_id=session_id)
```

**Session Identification**:
- Each alert is assigned a unique `session_id` (UUID) when submitted
- The `session_id` is returned immediately in the response
- Clients use `session_id` to track processing via WebSocket
- Database and events use `session_id` as the universal identifier

**Alert Response Model**:
```python
class AlertResponse(BaseModel):
    """Response model for alert submission."""
    session_id: str  # Universal identifier for tracking
    status: str      # "queued"
    message: str     # "Alert submitted for processing"
```

**Timeout Management**: 
- **10-minute processing limit** with `asyncio.wait_for()`
- **Graceful error handling** for timeouts, validation errors, connection errors
- **Service lifecycle coordination** during startup/shutdown
- **Pod-level session tracking** for multi-replica deployments

**📍 Background Processing**: `process_alert_background()` in `backend/tarsy/main.py`

### 2. Configuration Management
**Purpose**: System configuration and extensibility  
**Key Responsibility**: Flexible system configuration without code changes

TARSy supports both built-in components and YAML-based configuration, enabling system extension without code changes. Configuration defines agents, chains, MCP servers, and their relationships.

#### Configuration Architecture

```mermaid
graph TB
    ENV[Environment Variables<br/>.env file] --> Template[Template Resolution]
    YAML[agents.yaml] --> Loader[ConfigurationLoader]
    LLMYaml[llm_providers.yaml<br/>Optional] --> LLMLoader[LLM Config Loader]
    BuiltIn[Built-in Definitions<br/>builtin_config.py] --> Registry[Component Registries]
    
    Template --> Loader
    Loader --> Validation[Pydantic Validation]
    Validation --> Registry
    LLMLoader --> LLMManager[LLM Manager]
    
    Registry --> Chain[ChainRegistry]
    Registry --> Agent[AgentFactory] 
    Registry --> MCP[MCPServerRegistry]
    
    style YAML fill:#e8f5e8
    style LLMYaml fill:#fff3e0
    style BuiltIn fill:#f0f8ff
```

#### Key Configuration Types

**📍 Built-in Configuration**: `backend/tarsy/config/builtin_config.py`
- **Single source of truth** for built-in agents and MCP servers
- **No circular imports** - data structures only
- **Example built-in agent**:
```python
BUILTIN_AGENTS = {
    "KubernetesAgent": {
        "import": "tarsy.agents.kubernetes_agent.KubernetesAgent",
        "iteration_strategy": "react",
        "description": "Kubernetes-specialized agent using ReAct pattern"
    }
}
```

**📍 YAML Configuration**: `config/agents.yaml` (see `config/agents.yaml.example`)
- **Template variables**: `${VARIABLE_NAME}` resolved from environment
- **Agent definitions**: Custom agents with MCP servers and instructions (can override built-in agents)
- **Chain definitions**: Multi-stage workflows with alert type mappings (can override built-in chains)
- **MCP server configurations**: Custom tool servers (can override built-in MCP servers)

**Example YAML Configuration**:
```yaml
mcp_servers:
  # Custom MCP server
  security-scanner:
    server_id: "security-scanner"
    enabled: true
    transport:
      type: "stdio"
      command: "npx"
      args: ["@security/scanner-mcp-server@latest"]
  
  # Override built-in kubernetes-server with custom kubeconfig
  kubernetes-server:
    server_id: "kubernetes-server"
    enabled: true
    transport:
      type: "stdio"
      command: "npx"
      args: ["-y", "kubernetes-mcp-server@latest", "--kubeconfig", "${MCP_KUBECONFIG}"]
    
agents:
  security-analyst:
    mcp_servers: ["security-scanner", "kubernetes-server"]  # Mix of custom + built-in
    iteration_strategy: "react"
    custom_instructions: "Focus on security implications and threat analysis..."
    
chains:
  security-incident-chain:
    alert_types: ["SecurityBreach", "SuspiciousActivity"]
    stages:
      - name: "evidence-collection"
        agent: "security-analyst"
        iteration_strategy: "react-stage"
      - name: "final-analysis" 
        agent: "security-analyst"
        iteration_strategy: "react-final-analysis"
```

**📍 LLM Provider Configuration**: `config/llm_providers.yaml` (optional, see `config/llm_providers.yaml.example`)
- **Built-in default providers** work out-of-the-box with just API keys
- **Optional YAML overrides** for custom models, proxy configurations, temperature settings
- **Multi-provider support** with OpenAI, Google Gemini, xAI Grok, Anthropic Claude, Google Vertex AI
- **Content truncation controls** with provider-specific `max_tool_result_tokens` limits to prevent context overflow

**Built-in Default Providers**:
```python
# From builtin_config.py - work with just API keys
BUILTIN_LLM_PROVIDERS = {
    "openai-default": {
        "type": "openai", "model": "gpt-5",
        "max_tool_result_tokens": 250000  # Conservative for 272K context
    },
    "google-default": {
        "type": "google", "model": "gemini-2.5-flash",  # DEFAULT
        "max_tool_result_tokens": 950000  # Conservative for 1M context
    },
    "xai-default": {
        "type": "xai", "model": "grok-4-latest",
        "max_tool_result_tokens": 200000  # Conservative for 256K context
    },
    "anthropic-default": {
        "type": "anthropic", "model": "claude-4-sonnet",
        "max_tool_result_tokens": 150000  # Conservative for 200K context
    },
    "vertexai-default": {
        "type": "vertexai", "model": "claude-sonnet-4-5@20250929",
        "max_tool_result_tokens": 150000  # Conservative for 200K context
    }
}
```

**Example LLM YAML Configuration**:
```yaml
llm_providers:
  # Override built-in provider model
  openai-default:
    type: openai
    model: gpt-4  # Override default gpt-5
    api_key_env: OPENAI_API_KEY
    max_tool_result_tokens: 200000  # Override default limit
    
  # Custom proxy provider
  openai-proxy:
    type: openai
    model: custom-model
    api_key_env: OPENAI_API_KEY
    base_url: https://my-proxy.domain.com/v1
    temperature: 0.0
    max_tool_result_tokens: 150000  # Custom limit for proxy
```

#### Configuration Loading Process

**📍 Configuration Loader**: `backend/tarsy/config/agent_config.py`
1. **File validation** - YAML syntax and structure validation
2. **Pydantic validation** - Type checking and constraint validation
3. **Override detection** - Logs when YAML configurations override built-in agents, MCP servers, or chains
4. **Reference validation** - Ensures MCP server references exist
5. **Template resolution** - Resolves `${VAR}` from environment variables

**📍 Settings Management**: `backend/tarsy/config/settings.py`
- **Environment-based configuration** using Pydantic BaseSettings
- **LLM provider management** with built-in defaults and YAML merging
- **API keys, timeouts, concurrency limits**
- **Database and service configuration** (dual SQLite/PostgreSQL support)
- **Template variable defaults**

**📍 Deployment Modes**: TARSy supports multiple deployment approaches:
- **Development Mode**: `make dev` - Direct backend + dashboard (SQLite)
- **Container Mode**: `make containers-deploy` - Full stack with authentication (PostgreSQL)
- **Hybrid Testing**: Mix of local and containerized components as needed

**📍 LLM Configuration Process**:
1. **Load built-in providers** from `builtin_config.py`
2. **Load YAML overrides** if `config/llm_providers.yaml` exists
3. **Merge configurations** (YAML takes priority over built-ins)
4. **Validate provider types** and required fields
5. **Map API keys** based on provider type (google → GOOGLE_API_KEY, etc.)

### 3. Chain Management & Execution
**Purpose**: Chain definition, selection, and sequential stage execution  
**Key Responsibility**: Managing multi-stage agent workflows

Chains enable multi-stage workflows where specialized agents build upon each other's work. Each chain consists of sequential stages executed by domain-expert agents, with data accumulating as it flows through stages.

#### Chain Architecture

```mermaid
sequenceDiagram
    participant AS as AlertService
    participant CR as ChainRegistry
    participant CC as ChainContext
    participant A1 as Stage 1 Agent
    participant A2 as Stage 2 Agent
    
    AS->>CR: get_chain_for_alert_type("kubernetes")
    CR->>AS: kubernetes-agent-chain definition
    AS->>CC: Initialize with alert data
    
    loop For Each Stage
        AS->>A1: execute_analysis(context)
        A1->>A1: Run with iteration strategy
        A1->>CC: Store stage results
        AS->>A2: execute_analysis(context + previous results)
        A2->>CC: Store stage results
    end
    
    AS->>AS: Extract final analysis
```

#### Key Components

**📍 Chain Registry**: `backend/tarsy/services/chain_registry.py`
- **O(1) chain lookup** by alert type
- **Conflict detection** - ensures each alert type maps to exactly one chain
- **Built-in + YAML chain merging**

**Current Built-in Chain**:
```python
# From builtin_config.py
"kubernetes-agent-chain": {
    "alert_types": ["kubernetes", "NamespaceTerminating"],
    "stages": [{"name": "analysis", "agent": "KubernetesAgent"}],
    "description": "Single-stage Kubernetes analysis"
}
```

**Multi-stage Chain Example**:
```yaml
# In agents.yaml
chains:
  incident-investigation-chain:
    alert_types: ["CriticalIncident"]
    stages:
      - name: "data-collection"
        agent: "data-collector"
        iteration_strategy: "react-stage"
      - name: "root-cause-analysis" 
        agent: "incident-analyst"
        iteration_strategy: "react-stage"
      - name: "recommendations"
        agent: "incident-analyst"  
        iteration_strategy: "react-final-analysis"
```

#### Chain Context & Data Flow

**📍 Unified Data Model**: `backend/tarsy/models/processing_context.py`
```python
class ChainContext(BaseModel):
    processing_alert: ProcessingAlert  # Composed alert with metadata + pristine client data
    session_id: str                    # Links to history tracking
    current_stage_name: str            # Currently executing stage
    stage_outputs: Dict[str, AgentExecutionResult]  # Accumulated stage results
    runbook_content: Optional[str]     # Downloaded once per chain
    chain_id: Optional[str]            # Executing chain identifier

# ProcessingAlert separates internal metadata from client data
class ProcessingAlert(BaseModel):
    alert_type: str                    # Determines chain selection
    severity: str                      # Alert severity level
    timestamp: int                     # Microsecond timestamp
    environment: str                   # Target environment
    runbook_url: Optional[str]         # Optional runbook URL
    alert_data: Dict[str, Any]         # Pristine client data (not polluted with metadata)
```

**Stage Data Accumulation**: Each stage sees all previous stage outputs, enabling progressive analysis and building upon previous work.

**📍 Chain Execution**: `AlertService._execute_chain_stages()` in `backend/tarsy/services/alert_service.py`

### 4. Agent Architecture & Strategy System
**Purpose**: Agent framework and processing strategies  
**Key Responsibility**: Agent behavior and reasoning patterns

Agents are specialized AI-powered components that analyze alerts using domain expertise and configurable reasoning strategies. The system supports both hardcoded agents (like KubernetesAgent) and YAML-configured agents.

#### Agent Framework Architecture

```mermaid
graph TB
    subgraph "Agent Types"
        BA[BaseAgent<br/>Abstract Framework]
        KA[KubernetesAgent<br/>Built-in]
        CA[ConfigurableAgent<br/>YAML-defined]
    end
    
    subgraph "Iteration Strategies (Any agent can use any strategy)"
        React[ReAct<br/>Full Analysis]
        ReactStage[ReAct Stage<br/>Chain Step]
        ReactFinal[ReAct Final<br/>Synthesis Only]
    end
    
    subgraph "Instruction Sources"
        General[General Instructions]
        MCP[MCP Server Instructions]
        Custom[Agent Custom Instructions]
    end
    
    BA --> KA
    BA --> CA
    
    KA -.-> React
    KA -.-> ReactStage
    KA -.-> ReactFinal
    CA -.-> React
    CA -.-> ReactStage
    CA -.-> ReactFinal
    
    BA --> General
    BA --> MCP
    BA --> Custom
    
    style BA fill:#e8f5e8
    style React fill:#fff3e0
    style ReactStage fill:#fff3e0
    style ReactFinal fill:#fff3e0
```

#### BaseAgent Framework

**📍 Abstract Base**: `backend/tarsy/agents/base_agent.py`
All agents inherit from BaseAgent and implement:
```python
class BaseAgent(ABC):
    @abstractmethod
    def mcp_servers(self) -> List[str]:
        """Define which MCP servers this agent uses"""
        
    @abstractmethod  
    def custom_instructions(self) -> str:
        """Agent-specific instructions for the LLM"""
        
    async def execute_analysis(self, context: ChainContext) -> str:
        """Main execution method using configured iteration strategy"""
```

#### Iteration Strategies

**Three distinct processing approaches**:

1. **ReAct (Standard)**: Think→Action→Observation cycles for complete analysis
2. **ReAct Stage**: Stage-specific analysis within multi-stage chains  
3. **ReAct Final Analysis**: Synthesis without tools, uses accumulated data

**📍 Strategy Controllers**: `backend/tarsy/agents/iteration_controllers/`

**ReAct Example Flow**:
```
Question: Analyze this Kubernetes alert
Thought: I need to check the namespace status first
Action: kubernetes_get_namespace
Action Input: {"namespace": "production"}
[Tool Call Executed]
Observation: {
  "apiVersion": "v1",
  "kind": "Namespace", 
  "metadata": {"name": "production"},
  "status": {"phase": "Terminating"}
}
Thought: The namespace is terminating. Now I need to see which pods are affected
Action: kubernetes_list_pods  
Action Input: {"namespace": "production"}
[Tool Call Executed]
Observation: {
  "items": [
    {"metadata": {"name": "app-1"}, "status": {"phase": "Pending"}},
    {"metadata": {"name": "app-2"}, "status": {"phase": "Pending"}},
    {"metadata": {"name": "worker-1"}, "status": {"phase": "Terminating"}}
  ]
}
Final Answer: The namespace 'production' is terminating, causing 2 pods to be stuck in Pending state and 1 pod actively terminating. The namespace termination is preventing new pod scheduling...
```

#### Instruction Composition

**Three-tier instruction system**:
```python
final_instructions = (
    general_instructions +           # Universal SRE guidance
    mcp_server_instructions +        # Tool-specific guidance - Optional
    agent.custom_instructions        # Agent domain expertise - Optional
)
```

**📍 Agent Factory**: `backend/tarsy/services/agent_factory.py`
- **Dependency injection** for LLM client, MCP client, registries
- **Strategy configuration** per stage
- **Both hardcoded and configured agent support**

### 5. MCP Integration & Tool Management
**Purpose**: External tool server integration and tool orchestration  
**Key Responsibility**: Connecting agents to external systems and tools

MCP (Model Context Protocol) servers provide agents with external tools and system access. TARSy integrates with MCP servers using the official SDK, supporting both built-in servers and custom configurations with automatic data masking.

#### MCP Architecture

```mermaid
graph TB
    subgraph "Agent Layer"
        Agent[Agent Execution]
        Tools[Available Tools]
    end
    
    subgraph "MCP Integration"
        Client[MCP Client]
        Registry[MCP Server Registry]
        Masking[Data Masking Service]
        Summarizer[Result Summarizer]
        TokenCounter[Token Counter]
    end
    
    subgraph "MCP Servers"
        K8s[kubernetes-server<br/>Built-in]
        Custom[Custom MCP Servers from config/agents.yaml]
        Future[Future Servers...]
    end
    
    Agent --> Tools
    Tools --> Client
    Client --> Registry
    Client --> Masking
    Client --> Summarizer
    Client --> TokenCounter
    Agent --> Summarizer
    
    Registry --> K8s
    Registry --> Custom
    Registry --> Future
    
    Client <--> K8s
    Client <--> Custom
    
    style Client fill:#e8f5e8
    style Registry fill:#f0f8ff
    style Masking fill:#fff0f5
```

#### Key Components

**📍 MCP Client Factory**: `backend/tarsy/services/mcp_client_factory.py`
- **On-demand client instantiation** for per-session isolation
- **Dependency injection** of settings and registry
- **Clean separation** between factory and client lifecycle

**📍 MCP Client**: `backend/tarsy/integrations/mcp/client.py`
- **Official MCP SDK integration** supporting stdio, HTTP, and SSE transports
- **Multi-transport architecture** with automatic transport selection based on configuration
- **Per-session lifecycle** tied to single async task context
- **Tool discovery** and execution coordination
- **Integrated data masking** on all tool responses
- **Immediate timeout failure** without retries (60s tool call timeout)

#### MCP Client Lifecycle Architecture

**Per-Session Client Isolation**: Each alert processing session gets its own dedicated MCP client instance to prevent async context interference:

```python
# In AlertService.process_alert()
async with self.mcp_client_factory.create_client() as session_mcp_client:
    # Client scoped to this specific alert session
    # Agent gets this isolated client
    agent = self.agent_factory.get_agent(agent_name, mcp_client=session_mcp_client)
    result = await agent.process_alert(context)
    # Client cleanup happens automatically when session completes
```

**Three Independent MCP Client Contexts**:

1. **Health Monitor Client** (global, long-lived)
   - Created once at `AlertService.__init__()`
   - Stored as `self.health_check_mcp_client`
   - Used ONLY for health checks/ping operations
   - Lives for entire application lifetime

2. **Alert Session Clients** (per-session, short-lived)
   - Created fresh in each `process_alert()` call via factory
   - Used for all agent tool execution in that specific alert
   - Cleanup when alert completes (success or failure)
   - Each concurrent alert gets completely isolated client

3. **Zero Sharing**
   - Health checks use only `health_check_mcp_client`
   - Alert sessions never share clients
   - Each operates in isolated async context

**Benefits**:
- **Eliminates `CancelledError` propagation** between async contexts
- **Session isolation** - timeout in one session doesn't affect others
- **Natural cleanup** - client dies with task (no cross-context cleanup)
- **Simplified error handling** - timeouts fail immediately, LLM can retry with different approach

**Tool Execution**:
```python
# MCP client tool execution with automatic masking
async with mcp_interaction_context(session_id, server_name, tool_name, parameters) as ctx:
    result = await session.call_tool(tool_name, parameters)
    # Automatic data masking applied before returning
```

**📍 MCP Server Registry**: `backend/tarsy/services/mcp_server_registry.py`
- **Single source of truth** for all MCP server configurations
- **Built-in + YAML server merging** with override support (YAML takes precedence)
- **Template variable resolution** for environment-specific values

**MCP Server Transport Examples**:

**Stdio Transport (Built-in)**:
```python
# From builtin_config.py - Traditional command-line MCP server
"kubernetes-server": {
    "server_id": "kubernetes-server",
    "enabled": True,
    "transport": {
        "type": "stdio",
        "command": "npx",
        "args": ["-y", "kubernetes-mcp-server@latest", "--read-only", 
                "--disable-destructive", "--kubeconfig", "${KUBECONFIG}"]
    },
    "instructions": "For Kubernetes operations: Be careful with cluster-scoped...",
    "data_masking": {
        "enabled": True,
        "pattern_groups": ["kubernetes"],
        "patterns": ["certificate", "token"]
    }
}
```

**HTTP Transport Configuration**:
```yaml
# In agents.yaml - HTTP endpoint MCP server
mcp_servers:
  http-api-server:
    server_id: "http-api-server"
    enabled: true
    transport:
      type: "http"
      url: "https://api.example.com/mcp"
      bearer_token: "${MCP_API_TOKEN}"
      timeout: 30
      verify_ssl: true
      headers:
        User-Agent: "tarsy/1.0"
    instructions: "HTTP-based MCP server for API integrations"
    data_masking:
      enabled: true
      pattern_groups: ["basic", "secrets"]
```

**SSE Transport Configuration**:
```yaml
# In agents.yaml - Server-Sent Events MCP server  
mcp_servers:
  streaming-server:
    server_id: "streaming-server"
    enabled: true
    transport:
      type: "sse"
      url: "https://streaming-api.example.com/sse"
      bearer_token: "${SSE_API_TOKEN}"
      timeout: 15
      sse_read_timeout: 300
      verify_ssl: true
      headers:
        Accept: "text/event-stream"
    instructions: "SSE-based MCP server for real-time data streams"
    data_masking:
      enabled: true
      pattern_groups: ["security"]
```

#### MCP Transport Types

**Transport Selection**: TARSy supports three MCP transport protocols:

- **`stdio`**: Traditional command-line MCP servers (most common)
  - **Configuration**: `command` and `args` fields

- **`http`**: HTTP endpoint MCP servers using JSON-RPC over HTTP
  - **Configuration**: `url`, optional `bearer_token`, `timeout`, `headers`

- **`sse`**: Server-Sent Events MCP servers for real-time streaming
  - **Configuration**: `url`, `sse_read_timeout`, optional `bearer_token`

**Transport Auto-Detection**: The MCP client automatically selects the appropriate transport based on the `transport.type` field in server configuration.

#### Agent-Server Assignment

**Server Assignment Pattern**: Agents declare required servers via `mcp_servers()` method:
```python
class KubernetesAgent(BaseAgent):
    def mcp_servers(self) -> List[str]:
        return ["kubernetes-server"]  # Only has access to k8s tools
```

**Tool Discovery Flow**:
1. **Agent requests tools** → `client.list_tools(session_id, server_name)`
2. **MCP client queries servers** → Discovers available tools per server
3. **Tools formatted** → `AvailableTools` model with server context
4. **Agent executes tools** → `client.call_tool(server, tool, params)`

#### Data Masking Integration

**📍 Automatic Response Filtering**: `backend/tarsy/services/data_masking_service.py`
- **Pattern-based masking** applied to all MCP tool responses
- **Server-specific patterns** (kubernetes secrets, API keys, certificates)
- **Fail-safe approach** - better to over-mask than expose sensitive data

**📍 Configuration**: Built-in servers include masking patterns, custom servers can define their own patterns in YAML configuration.

**📍 Agent Factory Integration**: `backend/tarsy/services/agent_factory.py` ensures agents only access their declared MCP servers.

#### Result Summarization Integration

**📍 Intelligent Size Management**: `backend/tarsy/integrations/mcp/summarizer.py`
- **Context-aware summarization** using agent-provided LLM client and investigation context
- **Token-based thresholds** with tiktoken integration for accurate size detection
- **Security-first design** - summarization occurs after data masking
- **Provider-level token control** using LangChain's native `max_tokens` parameter

**Summarization Flow**:
```python
# Automatic summarization in MCP client
async with mcp_interaction_context(...) as ctx:
    raw_response = await session.call_tool(tool_name, parameters)
    masked_response = self.data_masking_service.mask_response(raw_response, server_name)
    
    # Size check and summarization
    if investigation_conversation and self._should_summarize(server_name, tool_name, masked_response):
        summarized_response = await self.summarizer.summarize_result(
            server_name, tool_name, masked_response, investigation_conversation, 
            session_id, stage_execution_id, max_summary_tokens
        )
        return summarized_response
    
    return masked_response
```

**📍 Server-Specific Configuration**: 
```yaml
# In agents.yaml
mcp_servers:
  kubectl:
    summarization:
      enabled: true                    # Default: true
      size_threshold_tokens: 5000      # Default: 5K tokens
      summary_max_token_limit: 1000    # Default: 1K tokens
```

**📍 Token Counter Utility**: `backend/tarsy/utils/token_counter.py`
- **tiktoken integration** for accurate token estimation
- **Model-aware encoding** with fallbacks for unknown models
- **Observation format simulation** to predict actual context usage

### 6. LLM Integration & Multi-Provider Support
**Purpose**: AI/LLM provider abstraction and management  
**Key Responsibility**: Unified LLM access across multiple providers

TARSy provides comprehensive multi-provider LLM support with built-in defaults for immediate use and optional custom configurations for advanced setups. The system uses LangChain for provider abstraction and includes detailed communication logging.

#### LLM Architecture

```mermaid
graph TB
    subgraph "Configuration Layer"
        BuiltIn[Built-in Providers<br/>builtin_config.py]
        YAML[llm_providers.yaml<br/>Optional Overrides]
        ENV[Environment API Keys]
    end
    
    subgraph "LLM Management"
        Settings[Settings Manager]
        Manager[LLM Manager]
        Client[LLM Client]
    end
    
    subgraph "Provider Integration"
        LC[LangChain Abstraction]
        OpenAI[OpenAI Provider]
        Google[Google Gemini]
        XAI[xAI Grok]
        Anthropic[Anthropic Claude]
    end
    
    BuiltIn --> Settings
    YAML --> Settings
    ENV --> Settings
    Settings --> Manager
    Manager --> Client
    Client --> LC
    
    LC --> OpenAI
    LC --> Google
    LC --> XAI
    LC --> Anthropic
    
    style Settings fill:#e8f5e8
    style Manager fill:#fff3e0
    style LC fill:#f0f8ff
```

#### Key Components

**📍 Built-in Provider Defaults**: `backend/tarsy/config/builtin_config.py`
- **Out-of-the-box providers**: OpenAI (gpt-5), Google (gemini-2.5-flash), xAI (grok-4-latest), Anthropic (claude-4-sonnet), Vertex AI (claude-sonnet-4-5)
- **Default selection**: google-default for immediate use with just GOOGLE_API_KEY
- **Zero configuration required** for basic operation

```python
BUILTIN_LLM_PROVIDERS = {
    "openai-default": {
        "type": "openai", "model": "gpt-5", 
        "api_key_env": "OPENAI_API_KEY"
    },
    "google-default": {  # DEFAULT
        "type": "google", "model": "gemini-2.5-flash",
        "api_key_env": "GOOGLE_API_KEY"  
    },
    # ... xai-default, anthropic-default, vertexai-default
}
```

**📍 LLM Manager**: `backend/tarsy/integrations/llm/client.py`
- **Multi-provider initialization** with automatic availability detection
- **Provider selection** via LLM_PROVIDER environment variable
- **Unified client interface** using LangChain abstraction layer
- **Automatic retry logic** with exponential backoff for rate limiting
- **Enhanced token control** with optional `max_tokens` parameter for provider-level enforcement

**Provider Integration Pattern**:
```python
# All providers use unified LangChain integration
LLM_PROVIDERS = {
    "openai": _create_openai_client,     # ChatOpenAI
    "google": _create_google_client,     # ChatGoogleGenerativeAI
    "xai": _create_xai_client,          # ChatXAI
    "anthropic": _create_anthropic_client # ChatAnthropic
}
```

#### Content Truncation Controls

**Provider-Specific Tool Result Limits**: Each LLM provider has different context window limits, and large MCP tool results can cause context overflow. The `max_tool_result_tokens` configuration provides dual-layer protection:

1. **Pre-LLM truncation**: MCPResultSummarizer truncates tool results before sending to LLM
2. **Provider-aware limits**: Conservative defaults based on each provider's context window:
   - **OpenAI GPT-5**: 250K tokens (272K context window)
   - **Google Gemini 2.5**: 950K tokens (1M context window)  
   - **xAI Grok-4**: 200K tokens (256K context window)
   - **Anthropic Claude-4**: 150K tokens (200K context window)

**Benefits**: Prevents LLM API failures, ensures reliable processing regardless of tool result size, maintains performance across all components.

#### Configuration & Customization

**Three-tier configuration system**:

1. **Built-in defaults** (zero config) - Just set GOOGLE_API_KEY
2. **Environment overrides** - Set LLM_PROVIDER to use different built-in provider
3. **YAML customization** - Override models, add proxies, custom base URLs, content truncation limits

**Advanced Configuration Examples**:
```yaml
# config/llm_providers.yaml
llm_providers:
  # Override built-in model
  openai-default:
    type: openai
    model: gpt-4  # Override gpt-5 default
    max_tool_result_tokens: 200000  # Override default limit
    
  # Custom proxy configuration  
  openai-internal-proxy:
    type: openai
    model: gpt-4
    api_key_env: OPENAI_API_KEY
    base_url: https://internal-proxy.company.com/v1
    temperature: 0.1
    max_tool_result_tokens: 150000  # Custom limit for proxy
```

#### Communication & Error Handling

**📍 LLM Communication Logging**: Separate logger (`llm.communications`) captures all LLM interactions
**📍 Hook Integration**: All LLM interactions trigger typed hooks for history and dashboard updates
**📍 Error Handling**: Automatic retry for rate limiting, empty response detection, graceful degradation

#### Advanced LLM Features

**📍 Provider-Level Token Control**: Enhanced `generate_response()` method supports optional `max_tokens` parameter
```python
# Used by summarization system for guaranteed length limits
response_conversation = await self.llm_client.generate_response(
    summarization_conversation, 
    session_id, 
    stage_execution_id, 
    max_tokens=max_summary_tokens  # Provider enforces limit
)
```

**Benefits**:
- **Guaranteed token limits** - provider enforces max_tokens, not just prompt suggestions  
- **Universal support** - works with OpenAI, Anthropic, xAI, Google providers via LangChain
- **Cost control** - prevents excessive token generation and associated costs

**📍 Real-time Response Streaming**: LLM responses are streamed in real-time via WebSocket for enhanced user experience
```python
# Streaming publishes chunks via transient events (not persisted to DB)
# - Detects "Thought:" and "Final Answer:" markers in ReAct responses
# - Thoughts streamed at 2-token intervals, Final Answers at 5-token intervals
# - Events published to session:{session_id} channel as llm.stream.chunk
```

**Streaming Features**:
- **Progressive content delivery** - users see LLM thinking process in real-time
- **Non-blocking** - streaming failures don't affect LLM call success
- **Marker detection** - automatically identifies and categorizes content (thought vs final_answer)
- **Transient events** - chunks not persisted to database, only sent via WebSocket

#### Provider Support

**All providers use LangChain abstraction** with support for:
- **Custom base URLs** (OpenAI, xAI) for proxy configurations
- **SSL verification control** (OpenAI) 
- **Provider-specific optimizations** (Google Gemini flash models, Anthropic Claude latest models)

#### API Key Management

**Flexible API key configuration**:
- **Environment variable mapping**: provider type determines API key field
- **Built-in security**: API keys never logged or stored in plaintext
- **Validation**: Configuration validates API key presence at startup
- **Zero-configuration defaults**: GOOGLE_API_KEY works out-of-the-box

```python
# Automatic API key mapping by provider type
provider_type_to_key = {
    "google": settings.google_api_key,      # GOOGLE_API_KEY
    "openai": settings.openai_api_key,      # OPENAI_API_KEY  
    "xai": settings.xai_api_key,           # XAI_API_KEY
    "anthropic": settings.anthropic_api_key # ANTHROPIC_API_KEY
}
```

### 7. Hook System & Event-Driven Architecture
**Purpose**: Event-driven component decoupling and real-time system coordination  
**Key Responsibility**: Enabling loose coupling through typed event handling

The hook system enables event-driven architecture where processing components emit events that are consumed by history, dashboard, and monitoring systems without tight coupling. Multiple hook handlers can process the same events concurrently.

#### Hook Architecture

```mermaid
graph LR
    subgraph "Event Sources"
        LLM[LLM Client]
        MCP[MCP Client] 
        Agent[Agent Execution]
    end
    
    subgraph "Hook System"
        TM[TypedHookManager]
        HH[History Hooks]
        DH[Dashboard Hooks]
    end
    
    subgraph "Event Consumers"
        DB[(History Database)]
        WS[WebSocket Broadcasts]
    end
    
    LLM -->|LLMInteraction| TM
    MCP -->|MCPInteraction| TM
    Agent -->|StageExecution| TM
    
    TM --> HH
    TM --> DH
    
    HH --> DB
    DH --> WS
    
    style TM fill:#fff3e0
```

#### Key Components

**📍 Typed Hook Manager**: `backend/tarsy/hooks/typed_context.py`
- **Type-safe event handling** with generic types (`BaseTypedHook[TInteraction]`)
- **Concurrent execution** - multiple hooks process same events
- **Error isolation** - hook failures don't affect processing

**Event Types**:
```python
# Three main interaction types
LLMInteraction    # LLM requests/responses, timing, errors (including summarization LLM calls)
MCPInteraction    # MCP tool calls, results, errors  
StageExecution    # Stage lifecycle, status, metadata
```

**📍 Hook Registration**: `backend/tarsy/hooks/hook_registry.py`
```python
# Example hook registration at startup
typed_hook_registry = get_typed_hook_registry()
typed_hook_registry.register_llm_hook(HistoryLLMHook())
typed_hook_registry.register_llm_hook(DashboardLLMHook())
```

#### Hook Integration Pattern

**Event Emission**: Processing components emit events at key points:
```python
# In LLM client - automatic event emission
interaction = LLMInteraction(session_id=session_id, messages=messages, ...)
await typed_hook_manager.trigger_llm_hooks(interaction)
```

**Event Consumption**: Hook handlers process events independently:
```python
class HistoryLLMHook(BaseTypedHook[LLMInteraction]):
    async def execute(self, interaction: LLMInteraction) -> None:
        # Store interaction in database for audit trail
        
class DashboardLLMHook(BaseTypedHook[LLMInteraction]):  
    async def execute(self, interaction: LLMInteraction) -> None:
        # Format and broadcast to WebSocket subscribers
```

**📍 Hook Implementations**: 
- `backend/tarsy/hooks/typed_history_hooks.py` (history capture)
- `backend/tarsy/hooks/typed_dashboard_hooks.py` (real-time updates)

### 8. History & Audit Trail
**Purpose**: Complete processing history capture and timeline reconstruction  
**Key Responsibility**: Providing comprehensive audit trails and operational visibility

The history system captures the complete lifecycle of alert processing, providing detailed audit trails for debugging, monitoring, and compliance. All interactions, timings, and data flow are preserved with microsecond precision.

#### History Architecture

```mermaid
graph LR
    subgraph "Event Sources (via Hooks)"
        LLM[LLM Interactions]
        MCP[MCP Communications]
        Stage[Stage Executions]
    end
    
    subgraph "History Service"
        HS[HistoryService]
        Repo[HistoryRepository]
    end
    
    subgraph "Storage & API"
        DB[(History Database<br/>SQLite: Development<br/>PostgreSQL: Containers)]
        API[REST API Endpoints]
    end
    
    subgraph "Timeline Reconstruction"
        Timeline[Chronological Timeline]
        Details[Detailed Session View]
    end
    
    LLM --> HS
    MCP --> HS
    Stage --> HS
    
    HS --> Repo
    Repo --> DB
    
    HS --> API
    API --> Timeline
    API --> Details
    
    style HS fill:#e8f5e8
    style DB fill:#f0f8ff
    style Timeline fill:#fff3e0
```

#### Key Components

**📍 History Service**: `backend/tarsy/services/history_service.py`
- **Complete session lifecycle management** from creation to completion
- **Graceful degradation** when database unavailable (history capture disabled)
- **Retry mechanisms** with exponential backoff for database operations

#### Database Configuration

**📍 Dual Database Support**: TARSy supports both SQLite and PostgreSQL based on deployment mode:

- **Development Mode**: SQLite (`history.db`) - zero configuration, file-based
- **Container Mode**: PostgreSQL - production-ready with connection pooling
- **Configuration**: Determined by `DATABASE_URL` environment variable
- **Migration**: Database-agnostic SQLModel allows switching without code changes

**Database Selection Examples**:
```bash
# Development (auto-default)
DATABASE_URL=""  # → sqlite:///history.db

# Container deployment (set by podman-compose.yml)  
DATABASE_URL="postgresql://tarsy:password@database:5432/tarsy"

# Custom configurations
DATABASE_URL="sqlite:///./data/custom.db"
DATABASE_URL="postgresql+psycopg2://user:pass@localhost/tarsy"
```

**📍 Database Engine Creation**: `backend/tarsy/database/init_db.py`
- **Automatic type detection** from connection string format
- **PostgreSQL optimizations**: Connection pooling, BIGINT timestamps, JSONB support
- **SQLite optimizations**: WAL mode, thread safety, file-based persistence

**Session Lifecycle**:
```python
# Session creation (linked to chain execution)
session = AlertSession(
    session_id=chain_context.session_id,
    alert_id=alert_id,
    alert_data=chain_context.alert_data,
    agent_type=f"chain:{chain_definition.chain_id}",
    chain_definition=chain_definition.model_dump()
)
```

**📍 Database Models**: `backend/tarsy/models/unified_interactions.py`
- **LLMInteraction**: Complete LLM request/response tracking with timing
- **MCPInteraction**: MCP tool calls with parameters, results, and errors
- **StageExecution**: Chain stage tracking with status and metadata

**Timeline Data Structure**:
```python
class DetailedSession(BaseModel):
    # Core session info
    session_id: str
    alert_data: dict
    chain_definition: dict
    
    # Chronological timeline
    stages: List[DetailedStage]  # Each stage contains interactions
    
    @computed_field
    def chronological_interactions(self) -> List[Interaction]:
        # All LLM + MCP interactions sorted by timestamp_us
```

#### History API Endpoints

**📍 REST API**: `backend/tarsy/controllers/history_controller.py`

**Core Endpoints**:
- **`GET /api/v1/history/sessions`** - Paginated session list with filtering
- **`GET /api/v1/history/sessions/{id}`** - Detailed session with complete timeline  
- **`GET /api/v1/history/active-sessions`** - Currently processing sessions
- **`GET /api/v1/history/health`** - History service health check

**Advanced Filtering Support**:
```http
# Multiple filter examples
GET /api/v1/history/sessions?status=completed&alert_type=kubernetes
GET /api/v1/history/sessions?search=namespace+terminating&page=2
GET /api/v1/history/sessions?start_date_us=1734476400000000&end_date_us=1734562799999999
```

#### Timeline Reconstruction

**Microsecond Precision**: All timestamps use Unix microseconds for accurate sequencing

**Chronological Assembly**: 
1. **Stage executions** provide structure 
2. **LLM interactions** show reasoning process
3. **MCP communications** show tool usage  
4. **Combined timeline** enables complete workflow reconstruction

**📍 Hook Integration**: History hooks automatically capture events from processing components, ensuring no data loss and consistent timing information.

**📍 Dashboard Integration**: History API powers both the SRE dashboard timeline view and provides data for real-time progress updates.

#### System Health & Warnings API

**📍 REST API**: `backend/tarsy/controllers/system_controller.py`

**Core Endpoints**:
- **`GET /health`** - Comprehensive health check with service status and system warnings
  - Returns HTTP 200 for healthy status
  - Returns HTTP 503 for degraded/unhealthy status (Kubernetes probes use this)
  - Checks: database connectivity, event system health, history service, system warnings
  - Provides detailed service status for all components in a single endpoint
- **`GET /api/v1/system/warnings`** - Active system warnings (MCP/LLM init failures, etc.)

The system warnings API surfaces critical but non-fatal initialization errors (MCP server failures, LLM provider issues, missing runbook service configuration) that don't prevent startup but affect functionality. Warnings are displayed in the dashboard UI and included in the main health endpoint response.

**MCP Health Monitoring**: A background service (`MCPHealthMonitor`) continuously monitors MCP server health, automatically attempts recovery for failed servers, and manages warning lifecycle. The service checks servers every 15 seconds, attempts to reinitialize failed servers when they become available, and automatically clears warnings upon successful recovery.

**Multi-Replica Health Monitoring:**
- Health check validates database connectivity required for cross-pod coordination
- Event system health includes PostgreSQL LISTEN connection status
- Pod-specific issues (like event listener failures) properly trigger readiness probe failures

### 9. Dashboard & Real-time Monitoring
**Purpose**: User interface and live system monitoring  
**Key Responsibility**: Providing real-time visibility and historical analysis

TARSy provides a comprehensive SRE dashboard for operational monitoring with optional integrated manual alert submission capability. Real-time updates flow through a sophisticated WebSocket system integrated with the hook architecture.

#### UI Architecture

```mermaid
graph TB
    subgraph "Frontend Application"
        Dashboard[SRE Dashboard<br/>localhost:5173]
    end
    
    subgraph "Backend Services"
        API[FastAPI Backend<br/>localhost:8000]
        WS["WebSocket Endpoint<br/>/api/v1/ws"]
        WSManager[WebSocket Manager]
        EventListener[Event Listener<br/>PostgreSQL/SQLite]
    end
    
    subgraph "Event System"
        EventPublisher[Event Publisher]
        DB[(Events Database<br/>PostgreSQL/SQLite)]
    end
    
    subgraph "Data Sources"
        History[History API]
        Hooks[Hook Events]
    end
    
    Dashboard --> WS
    Dashboard --> API
    
    WS --> WSManager
    Hooks --> EventPublisher
    EventPublisher --> DB
    DB --> EventListener
    EventListener --> WSManager
    WSManager --> WS
    
    History --> API
    
    style Dashboard fill:#e1f5fe
    style WS fill:#fff3e0
    style EventListener fill:#e8f5e8
    style DB fill:#f0f8ff
```

**📍 SRE Dashboard**: `dashboard/src/` (React TypeScript)
- **Session list view** with filtering and real-time updates
- **Timeline visualization** for processing stages
- **Active session monitoring** with live progress

**📍 Manual Alert Submission**: Integrated into dashboard at `/submit-alert` (React TypeScript)  
- **Alert submission interface** for manual alert testing
- **Payload validation and preview** with flexible key-value pairs
- **Processing status monitoring** with real-time WebSocket updates
- **Unified user experience** within main dashboard application

#### WebSocket & Real-time Communication Architecture

**Event-Driven WebSocket System with Cross-Pod Distribution**:

TARSy uses PostgreSQL LISTEN/NOTIFY (with SQLite polling fallback for development) for cross-pod event distribution, enabling multi-replica Kubernetes deployments. Events are persisted to the database and broadcast to all backend pods, which then forward them to their connected WebSocket clients.

**Architecture Overview**:
```text
Event Published → Database (INSERT + NOTIFY) → All Backend Pods → WebSocket Clients
                     ↓
              Event Persistence (catchup support)
```

##### Multi-Replica Event Flow with Automatic Failover

This demonstrates how the eventing system works in production with multi-replica deployments, including automatic failover and zero event loss:

```mermaid
sequenceDiagram
    participant Client as Dashboard Client
    participant R1 as Replica 1 (Pod 1)
    participant R2 as Replica 2 (Pod 2)
    participant R3 as Replica 3 (Pod 3)
    participant DB as PostgreSQL

    Note over Client,DB: Phase 1: Initial Connection
    Client->>R1: WebSocket Connect: /api/v1/ws
    R1-->>Client: WebSocket Connection Established
    Client->>R1: {"action":"subscribe","channel":"sessions"}
    R1->>DB: LISTEN sessions
    R2->>DB: LISTEN sessions
    R3->>DB: LISTEN sessions
    R1-->>Client: {"type":"subscription.confirmed","channel":"sessions"}
    
    Note over Client,DB: Phase 2: Normal Event Flow
    Note over R2: Alert processing starts
    R2->>DB: 1. INSERT INTO events (id=42)
    R2->>DB: 2. NOTIFY "sessions", {...}
    DB-->>R1: Notification received
    DB-->>R2: Notification received
    DB-->>R3: Notification received
    R1->>R1: dispatch_to_callbacks()<br/>broadcast_to_channel()
    R1-->>Client: {"type":"session.started","id":42,...}
    Note over Client: UI updates

    Note over Client,DB: Phase 3: Replica Failure
    Note over R1: 💥 Replica 1 crashes
    Note over Client: ⚠️ Connection lost detected
    
    Note over R2: Events continue (client disconnected)
    R2->>DB: Event 43: INSERT + NOTIFY
    R3->>DB: Event 44: INSERT + NOTIFY
    
    Note over Client,DB: Phase 4: Auto-Reconnection & Catchup
    Client->>R2: WebSocket Connect: /api/v1/ws
    R2-->>Client: WebSocket Connection Established
    Client->>R2: {"action":"subscribe","channel":"sessions"}
    Client->>R2: {"action":"catchup","channel":"sessions","last_event_id":42}
    R2->>DB: SELECT * FROM events<br/>WHERE channel='sessions' AND id>42
    DB-->>R2: Returns: [Event 43, Event 44]
    R2-->>Client: {"type":"...","id":43,...}
    R2-->>Client: {"type":"...","id":44,...}
    R2-->>Client: {"type":"subscription.confirmed","channel":"sessions"}
    
    Note over Client,DB: Phase 5: Resume Live Events
    R2->>DB: Event 45: INSERT + NOTIFY
    DB-->>R2: Notification received
    R2-->>Client: {"type":"...","id":45,...}
    Note over Client: ✅ All events received<br/>Zero event loss
```

**Timeline: Replica Failover with Zero Event Loss**

| Time | Event | Client State | Database State |
|------|-------|--------------|----------------|
| **10:00:00** | Client connects to Replica 1<br/>`WebSocket /api/v1/ws` | ✅ Connected<br/>WS → Replica 1<br/>Subscribed to "sessions" | Empty events table |
| **10:00:15** | Event 41 published<br/>(session.started) | ✅ Receives event 41<br/>`last_event_id=41` | `id=41` persisted<br/>NOTIFY → All pods |
| **10:00:30** | Event 42 published<br/>(llm.interaction) | ✅ Receives event 42<br/>`last_event_id=42` | `id=42` persisted<br/>NOTIFY → All pods |
| **10:00:45** | 💥 **Replica 1 crashes**<br/>(pod killed by k8s) | ⚠️ **Connection lost**<br/>Disconnected | Database intact<br/>Events 41-42 safe |
| **10:00:46** | Event 43 published<br/>(by Replica 2) | ❌ Not received<br/>Still disconnected | `id=43` persisted<br/>NOTIFY (no listeners) |
| **10:00:47** | Event 44 published<br/>(by Replica 3) | ❌ Not received<br/>Still disconnected | `id=44` persisted<br/>NOTIFY (no listeners) |
| **10:00:48** | **Browser auto-reconnects**<br/>`WebSocket /api/v1/ws` | 🔄 Reconnecting...<br/>Routes to Replica 2 | Query: `WHERE id>42` |
| **10:00:49** | **CATCHUP:** Sends events 43-44<br/>(from database) | ✅ Receives event 43<br/>✅ Receives event 44<br/>`last_event_id=44` | Returns: `[43, 44]`<br/>from database |
| **10:00:50** | WebSocket connection ready<br/>with Replica 2 | ✅ Connected<br/>WS → Replica 2<br/>Subscribed to "sessions" | Ready for live events |
| **10:01:00** | Event 45 published<br/>(stage.completed) | ✅ Receives event 45<br/>`last_event_id=45` | `id=45` persisted<br/>NOTIFY → All pods |
| **10:01:15** | Event 46 published<br/>(session.completed) | ✅ Receives event 46<br/>`last_event_id=46` | `id=46` persisted<br/>NOTIFY → All pods |
| **Result** | **Zero events lost**<br/>Seamless failover | ✅ All events received<br/>UI stays synchronized | All events stored<br/>Database consistent |

#### Key Observations

**Event Loss Prevention:**
- ✅ Events 43-44 published while client disconnected
- ✅ Events persisted to database immediately
- ✅ Catchup query retrieves missed events on reconnection
- ✅ Client receives ALL events in correct order: 41, 42, 43, 44, 45, 46

**Replica Independence:**
- ✅ Event 43 published by Replica 2 → Replica 3 receives via NOTIFY
- ✅ Event 44 published by Replica 3 → Replica 2 receives via NOTIFY
- ✅ Any replica can publish, all replicas broadcast to their clients

**Automatic Failover:**
- ✅ Browser detects disconnection (~1-2 seconds)
- ✅ Auto-reconnects with last known event ID
- ✅ Kubernetes routes to healthy replica
- ✅ No manual intervention required

**Database as Source of Truth:**
- ✅ All events persisted BEFORE broadcast
- ✅ Catchup always possible (events table = event log)
- ✅ Works even if ALL replicas crash (events safe in DB)

##### Core Components

**📍 WebSocket Endpoint**: `backend/tarsy/controllers/websocket_controller.py`
```python
# Single WebSocket connection per browser tab
@websocket_router.websocket("/api/v1/ws")
async def websocket_endpoint(websocket: WebSocket):
    # Client sends subscription messages over the connection
    # {"action": "subscribe", "channel": "sessions"}
    # {"action": "catchup", "channel": "sessions", "last_event_id": 42}
```

**Event Channels**:
- **`sessions`**: Global session lifecycle events (session.created, session.started, session.completed, session.failed)
- **`session:{session_id}`**: Per-session detail events (llm.interaction, llm.stream.chunk, mcp.tool_call, stage.started, stage.completed)

**📍 Connection Management**: `backend/tarsy/services/websocket_connection_manager.py`
- **Connection tracking** - manages active WebSocket connections per connection_id
- **Channel subscriptions** - tracks which channels each connection subscribes to
- **Broadcast routing** - forwards events to all subscribers of a channel

**📍 Event System Integration**: `backend/tarsy/services/events/`
- **Event Listener** - subscribes to database notifications (PostgreSQL LISTEN or SQLite polling)
- **Event Publisher** - publishes events to database with NOTIFY broadcast
- **Event Repository** - type-safe database operations for event persistence and catchup
- **Event Cleanup** - automatic cleanup of old events based on retention policy

**Event Integration Flow**:
```text
Hook Event → Event Publisher → Database (INSERT + NOTIFY) → 
  Event Listener → WebSocket Manager → WebSocket Clients → UI Update
```

**📍 Frontend WebSocket Service**: `dashboard/src/services/websocketService.ts`
- **Single connection per tab** - one WebSocket connection handles all subscriptions
- **Automatic reconnection** with exponential backoff and catchup
- **Channel-based subscriptions** - subscribe to specific event streams as needed
- **Message routing** - events routed to appropriate UI components based on type

### 10. Security & Data Protection
**Purpose**: Sensitive data protection and secure operations  
**Key Responsibility**: Preventing sensitive data exposure

TARSy implements comprehensive data masking to prevent sensitive information (API keys, passwords, certificates, Kubernetes secrets) from reaching LLM providers, logs, or persistent storage. The system follows a fail-safe approach: better to over-mask than expose sensitive data.

#### Security Architecture

```mermaid
graph TB
    subgraph "MCP Integration"
        MCP[MCP Server Response]
        Client[MCP Client]
    end
    
    subgraph "Data Masking Layer"
        Masker[DataMaskingService]
        Patterns[Pattern Library]
        Config[Server-Specific Config]
    end
    
    subgraph "Protected Destinations"
        LLM[LLM Providers]
        Logs[System Logs]
        DB[History Database]
    end
    
    MCP --> Client
    Client --> Masker
    Masker --> Patterns
    Masker --> Config
    
    Masker --> LLM
    Masker --> Logs
    Masker --> DB
    
    style Masker fill:#fff0f5
    style Patterns fill:#f0f8ff
    style Config fill:#e8f5e8
```

#### Data Masking Service

**📍 Core Service**: `backend/tarsy/services/data_masking_service.py`
- **Automatic integration** with MCP client - all tool responses are masked
- **Pattern-based detection** using configurable regex patterns
- **Server-specific configuration** allowing granular control per MCP server
- **Fail-safe operation** - continues processing even if masking fails

**Masking Workflow**:
```python
# Automatic masking in MCP client
async with mcp_interaction_context(...) as ctx:
    raw_response = await session.call_tool(tool_name, parameters)
    masked_response = self.data_masking_service.mask_response(raw_response, server_name)
    return masked_response  # Only masked data reaches LLM/logs/storage
```

#### Built-in Masking Patterns

**📍 Pattern Library**: `backend/tarsy/config/builtin_config.py`

**Pattern Categories**:
```python
BUILTIN_PATTERN_GROUPS = {
    "basic": ["api_key", "password"],
    "secrets": ["api_key", "password", "token"], 
    "security": ["api_key", "password", "token", "certificate"],
    "kubernetes": ["kubernetes_data_section", "kubernetes_stringdata_json", 
                  "api_key", "password"],
    "all": ["base64_secret", "base64_short", "api_key", "password", 
           "certificate", "token"]
}
```

**Example Patterns**:
- **Kubernetes Secrets**: Masks entire `data:` sections in YAML
- **API Keys**: `api_key: sk-abc123...` → `api_key: "__MASKED_API_KEY__"`
- **Certificates**: `-----BEGIN CERTIFICATE-----...` → `__MASKED_CERTIFICATE__`
- **Base64 Values**: Long base64 strings → `__MASKED_BASE64_VALUE__`

#### Server-Specific Configuration

**Built-in Server Example**:
```python
# kubernetes-server with built-in masking
"data_masking": {
    "enabled": True,
    "pattern_groups": ["kubernetes"],  # Expands to multiple patterns
    "patterns": ["certificate", "token"]  # Additional individual patterns
}
```

**YAML Configuration Example**:
```yaml
mcp_servers:
  security-scanner:
    server_id: "security-scanner"
    # ... connection config ...
    data_masking:
      enabled: true
      pattern_groups: ["security"]
      custom_patterns:
        - name: "custom_token"
          pattern: "CUSTOM-[A-Z0-9]{16}"
          replacement: "__MASKED_CUSTOM_TOKEN__"
```

#### Security Integration Points

**📍 MCP Response Filtering**: All MCP tool responses automatically masked before reaching any destination

**📍 History Database Protection**: All stored interactions contain only masked data

**📍 LLM Communication Security**: Sensitive data never sent to external LLM providers

**📍 Logging Security**: System logs contain masked versions of sensitive data

**Configuration Validation**: 
- **Pattern testing** during startup to catch invalid regex patterns
- **Server reference validation** ensures masking configs reference valid servers
- **Graceful degradation** if masking service unavailable

---

### 11. Authentication & Access Control
**Purpose**: Optional OAuth2-based authentication for enhanced security  
**Key Responsibility**: Protecting dashboard and API access in development and production environments

TARSy supports flexible authentication through [OAuth2-Proxy](https://github.com/oauth2-proxy/oauth2-proxy) integration, enabling organization-level access control while maintaining simple local development workflows.

#### Authentication Architecture

```mermaid
graph TB
    subgraph "Client Access"
        Browser[Browser/Dashboard]
        API_Client[Direct API Client]
    end
    
    subgraph "Authentication Layer (Optional)"
        OAuth2[OAuth2-Proxy<br/>:4180]
        Config[OAuth2 Config]
    end
    
    subgraph "OAuth Providers"
        GitHub[GitHub OAuth]
        Google[Google OAuth]
        Custom[Custom Provider]
    end
    
    subgraph "Tarsy Core"
        FastAPI[Tarsy API<br/>:8000]
        Dashboard[Dashboard Assets]
    end
    
    Browser --> OAuth2
    OAuth2 --> Config
    OAuth2 --> GitHub
    OAuth2 --> Google
    OAuth2 --> Custom
    OAuth2 --> FastAPI
    OAuth2 --> Dashboard
    
    API_Client -.-> OAuth2
    API_Client --> FastAPI
    
    style OAuth2 fill:#f0f8ff
    style Config fill:#e8f5e8
    style GitHub stroke-dasharray: 5 5
    style Google stroke-dasharray: 5 5
    style Custom stroke-dasharray: 5 5
```

#### OAuth2-Proxy Integration

**📍 Configuration**: `config/oauth2-proxy.cfg`
- **Upstream Configuration**: Proxies requests to Tarsy API (`:8000`)
- **Provider Integration**: GitHub, Google, and others
- **Session Management**: Cookie-based authentication with configurable expiration
- **Access Control**: Organization, team, or domain-based restrictions

**Protected Endpoints**:
- **Dashboard Access**: All dashboard routes require authentication
- **API Endpoints**: All `/api/` routes protected by default
- **WebSocket Connections**: Real-time updates require authenticated session
- **Health Endpoints**: Unprotected for monitoring purposes

#### Authentication Flow

**Browser-Based Authentication**:
```mermaid
sequenceDiagram
    participant U as User
    participant D as Dashboard
    participant O as OAuth2-Proxy
    participant P as OAuth Provider
    participant A as Tarsy API
    
    U->>D: Access dashboard
    D->>O: Request protected resource
    O->>P: Redirect for authentication
    P->>U: Present login form
    U->>P: Submit credentials
    P->>O: Return auth code
    O->>P: Exchange for access token
    O->>O: Create session cookie
    O->>A: Forward request with headers
    A->>O: Return response
    O->>D: Return authenticated response
    D->>U: Show protected content
```

**API Authentication Headers**:
```http
X-Auth-Request-User: username@organization.com
X-Auth-Request-Email: username@organization.com
X-Forwarded-For: original.client.ip
Authorization: Bearer <token>
```

**📖 For oauth2-proxy setup instructions**: See [OAuth2-Proxy Setup Guide](oauth2-proxy-setup.md)

---