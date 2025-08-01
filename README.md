# TARSy-bot 🤖

An intelligent Site Reliability Engineering agent that automatically processes alerts, retrieves runbooks, and uses MCP (Model Context Protocol) servers to gather system information for comprehensive incident analysis.

Inspired by the spirit of sci-fi AI, TARSy is your reliable SRE operations companion for SRE operations. 🚀

## Documentation

- **[README.md](README.md)**: This file - project overview and quick start
- **[Makefile](Makefile)**: Development workflow automation (run this first!)
- **[DEPLOYMENT.md](DEPLOYMENT.md)**: Advanced deployment, production setup, and development
- **[backend/DEVELOPMENT.md](backend/DEVELOPMENT.md)**: Development setup guide and testing workflow
- **[docs/requirements.md](docs/requirements.md)**: Application requirements and specifications  
- **[docs/design.md](docs/design.md)**: System design and architecture documentation

> **New Users**: Run `make setup` to get started quickly! 🎯

## Quick Start

```bash
# 1. Initial setup (one-time only)
make setup

# 2. Start all services  
make dev
```

**Services will be available at:**
- 🖥️ **TARSy Dashboard**: http://localhost:5173 (operational monitoring)
- 🛠️ **Alert Dev UI**: http://localhost:3001 (alert testing)  
- 🔧 **Backend API**: http://localhost:8000 (docs at /docs)

**Stop all services:** `make stop`

> **Note**: Edit `backend/.env` with your API keys before starting services. See [DEPLOYMENT.md](DEPLOYMENT.md) for details.

## Key Features

### 🛠️ Configuration-Based Agents (EP-0006)
Deploy new agents without code changes:
- **YAML Configuration**: Define agents and MCP servers in simple YAML files
- **Template Variables**: Use `${VAR}` syntax for environment-specific values with built-in defaults
- **No Code Changes**: Add new agent types through configuration alone
- **Full Compatibility**: Traditional hardcoded agents and configured agents work simultaneously
- **Automatic Registry**: Agent configurations auto-populate alert type mappings
- **Mixed MCP Access**: Configured agents can use both built-in and configured MCP servers
- **Secure Configuration**: Keep sensitive values in environment variables, not config files

### 🔧 Flexible Alert Data Structure (EP-0005)
Support for diverse monitoring sources beyond Kubernetes:
- **Agent-Agnostic Design**: Accept arbitrary JSON payloads from any monitoring system
- **Minimal Validation**: Only alert_type and runbook URL required, everything else flexible
- **LLM-First Processing**: Agents receive complete JSON payloads for intelligent interpretation
- **Dynamic UI Rendering**: Dashboard and dev UI dynamically display any alert data fields
- **Enhanced Database**: JSON indexing for optimized queries on flexible data structures

### 🧠 Multi-Layer Agent Architecture (EP-0002)
The system implements a sophisticated multi-layer architecture:
- **Orchestrator Layer**: Routes alerts to specialized agents based on alert type
- **Specialized Agents**: Domain-specific agents (KubernetesAgent) with focused MCP server subsets
- **Intelligent Tool Selection**: LLM-driven selection of appropriate MCP tools from agent's assigned servers
- **Inheritance-Based Design**: Common processing logic shared across all specialized agents

### 📊 Comprehensive Audit Trail (EP-0003)
Complete visibility into alert processing workflows:
- **Session Tracking**: Persistent storage of all alert processing sessions with lifecycle management
- **Interaction Logging**: Automatic capture of all LLM interactions and MCP communications
- **Chronological Timeline**: Microsecond-precision reconstruction of complete processing workflows
- **Advanced Querying**: REST API with filtering, pagination, and complex query support
- **Dashboard Ready**: Foundation for SRE monitoring dashboards with comprehensive historical data

### 🖥️ SRE Dashboard (EP-0004)
Standalone React dashboard for operational monitoring:
- **Real-time Monitoring**: Live view of active alert processing with progress indicators
- **Historical Analysis**: Comprehensive filtering of alert sessions
- **Timeline Visualization**: Interactive chronological view of complete processing workflows
- **Multiplexed WebSocket**: Efficient real-time updates with subscription-based architecture
- **Performance Optimized**: Advanced pagination for large datasets

## Architecture

Tarsy implements a modern, multi-layer architecture:

- **Multi-Layer Backend**: FastAPI-based service with orchestrator and specialized agent layers
- **Flexible Alert Processing**: Agent-agnostic system supporting arbitrary JSON payloads from diverse monitoring sources
- **Agent Specialization**: Domain-specific agents (KubernetesAgent) with focused MCP server subsets
- **History Service**: Comprehensive audit trail capture with SQLModel database persistence
- **SRE Dashboard**: Standalone React dashboard for operational monitoring with real-time WebSocket integration
- **Alert Dev UI**: React TypeScript development interface for testing and demonstration
- **MCP Integration**: Official `mcp` library with agent-specific server assignments and hook context
- **LLM Support**: Unified LLM client supporting multiple providers (OpenAI, Google, xAI) with automatic interaction logging

## Features

### 🤖 Core Processing
- **Multi-Layer Agent Architecture**: Orchestrator delegates to specialized agents based on alert type
- **Flexible Alert Ingestion**: Accept arbitrary JSON payloads from any monitoring system with minimal validation
- **LLM-First Processing**: Agents receive complete alert data for intelligent interpretation without rigid field extraction
- **Intelligent Tool Selection**: Agents use LLM to select appropriate tools from their assigned MCP server subset
- **Runbook Integration**: Automatic GitHub runbook download and distribution to specialized agents
- **Agent Specialization**: Domain-specific agents (KubernetesAgent) with focused capabilities

### 📈 History & Monitoring
- **Comprehensive Audit Trail**: Persistent capture of all alert processing workflows
- **SRE Dashboard**: Standalone React dashboard with real-time monitoring and historical analysis
- **Timeline Visualization**: Interactive chronological view with LLM interactions and MCP communications
- **Advanced Query API**: REST endpoints with filtering, pagination, and complex queries
- **Multiplexed WebSocket**: Efficient real-time updates with subscription-based architecture
- **Performance Optimized**: Virtual scrolling for 1000+ sessions with responsive UI

### ⚡ Technical Features
- **Multi-LLM Support**: Configurable providers (OpenAI, Google, xAI) with unified client interface
- **Real-time Updates**: WebSocket-based progress tracking with agent identification
- **Database Flexibility**: SQLite with PostgreSQL migration support
- **Extensible Design**: Configuration-driven addition of new agents and MCP servers
- **Graceful Degradation**: Robust error handling with service-level fault tolerance

## How It Works

### 🔄 Multi-Layer Processing Pipeline
1. **Alert Received**: System receives an alert (e.g., "Namespace stuck in Terminating")
2. **Agent Selection**: Orchestrator uses agent registry to select appropriate specialized agent (KubernetesAgent)
3. **History Session Created**: System creates persistent session for complete audit trail
4. **Runbook Downloaded**: Fetches the relevant runbook from GitHub and provides to selected agent
5. **Agent Initialization**: Agent configures with its assigned MCP server subset (kubernetes-server)
6. **Iterative Analysis**: Agent uses LLM to intelligently select and call tools from its server subset
7. **Comprehensive Logging**: All LLM interactions and MCP communications automatically captured
8. **Real-time Updates**: Dashboard receives live updates via multiplexed WebSocket with subscription channels
9. **Final Analysis**: Agent provides specialized domain analysis with complete processing history

### 📝 Audit Trail Capture
- **Automatic Logging**: HookContext system transparently captures all interactions
- **Microsecond Precision**: Exact chronological ordering of all processing steps
- **Complete Visibility**: Full audit trail available for debugging and monitoring
- **API Access**: Historical data accessible via REST endpoints for dashboard integration

## Project Structure

```
tarsy-bot/
├── backend/                # FastAPI backend with multi-layer agent architecture
│   ├── tarsy/
│   │   ├── agents/         # Specialized agent classes (KubernetesAgent, ConfigurableAgent, BaseAgent)
│   │   ├── controllers/    # API controllers and REST endpoints
│   │   ├── database/       # Database initialization and schema management
│   │   ├── hooks/          # Event hooks for automatic interaction capture
│   │   ├── models/         # Data models (Alert, History, API schemas, Agent configs)
│   │   ├── repositories/   # Database access layer with SQLModel
│   │   ├── services/       # Business logic (AlertService, HistoryService, AgentRegistry)
│   │   ├── integrations/   # External integrations (LLM providers, MCP servers)
│   │   ├── config/         # Configuration management (Settings, Agent config loading)
│   │   └── utils/          # Utility functions and logging
│   ├── tests/              # Comprehensive test suite (unit, integration, e2e)
│   ├── pyproject.toml      # Python dependencies and project configuration
│   └── env.template        # Environment variables template
├── dashboard/              # React TypeScript SRE dashboard
│   ├── src/
│   │   ├── components/     # Dashboard components (ActiveAlertsPanel, SessionDetailPage, etc.)
│   │   ├── services/       # API clients and WebSocket managers
│   │   ├── hooks/          # Custom React hooks for state management
│   │   └── types/          # TypeScript type definitions
│   └── package.json        # Node.js dependencies
├── alert-dev-ui/           # React TypeScript development interface
│   ├── src/
│   │   ├── components/     # React components (AlertForm, ProcessingStatus, ResultDisplay)
│   │   ├── services/       # API and WebSocket clients
│   │   └── types/          # TypeScript type definitions
│   └── package.json        # Node.js dependencies
├── docs/                   # Comprehensive documentation
│   ├── requirements.md     # Application requirements and specifications
│   ├── design.md           # Technical design and architecture documentation
│   └── enhancements/       # Enhancement proposal system
│       ├── implemented/    # Completed EPs (EP-0002 Multi-Layer Agents, EP-0003 History Service)
│       ├── pending/        # Pending enhancement proposals
│       └── templates/      # EP document templates
├── Makefile                 # Development workflow automation
├── DEPLOYMENT.md           # Production deployment guide
└── docker-compose.yml      # Docker development environment
```

## Usage

1. **Start All Services**: Run `make dev` to start backend, dashboard, and alert UI
2. **Submit an Alert**: Use the alert dev UI at http://localhost:3001 to simulate an alert
3. **Monitor via Dashboard**: Watch real-time progress updates and historical analysis at http://localhost:5173
4. **View Results**: See detailed processing timelines and comprehensive LLM analysis
5. **Stop Services**: Run `make stop` when finished

> **Tip**: Use `make urls` to see all available service endpoints and `make status` to check which services are running.

## Supported Alert Types

The system now supports flexible alert types from any monitoring source:

### Current Agent Types
- **Kubernetes Agent**: Processes alerts from Kubernetes clusters (namespaces, pods, services, etc.)

### Flexible Alert Support  
- **Any Monitoring System**: Accepts arbitrary JSON payloads from Prometheus, AWS CloudWatch, ArgoCD, Datadog, etc.
- **Agent-Agnostic Processing**: New alert types can be added by creating specialized agents and updating agent registry
- **LLM-Driven Analysis**: Agents intelligently interpret any alert data structure without code changes to core system

The LLM-driven approach with flexible data structures means diverse alert types can be handled from any monitoring source, as long as:
- A runbook exists for the alert type
- An appropriate specialized agent is available or can be created
- The MCP servers have relevant tools for the monitoring domain

## API Endpoints

### Core API
- `GET /` - Health check endpoint
- `GET /health` - Comprehensive health check with service status
- `POST /alerts` - Submit a new alert for processing
- `GET /alert-types` - Get supported alert types
- `GET /processing-status/{alert_id}` - Get processing status
- `WebSocket /ws/{alert_id}` - Real-time progress updates

### History API (EP-0003)
- `GET /api/v1/history/sessions` - List alert processing sessions with filtering and pagination
- `GET /api/v1/history/sessions/{session_id}` - Get detailed session with chronological timeline
- `GET /api/v1/history/health` - History service health check and database status

## Development

### Adding New Components

- **Alert Types**: Add to `supported_alerts` in `config/settings.py` and create corresponding runbooks, or use configuration-based agents via `config/agents.yaml`
- **MCP Servers**: Update `mcp_servers` configuration in `settings.py` or define in `config/agents.yaml`
- **Agents**: Create traditional hardcoded agent classes extending BaseAgent, or define configuration-based agents in `config/agents.yaml`
- **LLM Providers**: See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed instructions

### Running Tests

```bash
# Install test dependencies and run integration tests
cd backend
make test
```

The test suite includes comprehensive end-to-end integration tests covering the complete alert processing pipeline, agent specialization, error handling, and performance scenarios with full mocking of external services.

### Architecture Documents

- [docs/requirements.md](docs/requirements.md): Application requirements and specifications
- [docs/design.md](docs/design.md): System design and architecture documentation
- [DEPLOYMENT.md](DEPLOYMENT.md) - Production deployment and advanced configuration
```