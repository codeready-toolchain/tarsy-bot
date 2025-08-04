# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TARSy-bot is an intelligent Site Reliability Engineering (SRE) agent that automatically processes alerts, retrieves runbooks, and uses MCP (Model Context Protocol) servers to gather system information for comprehensive incident analysis. The system implements a multi-layer agent architecture with flexible alert processing capabilities.

## Development Commands

### Quick Start
```bash
# Initial setup (one-time only)
make setup

# Start all services for development
make dev

# Stop all services
make stop
```

### Backend Development
```bash
cd backend

# Install dependencies
make install

# Run backend development server
make dev

# Run tests
make test              # All tests
make test-unit         # Unit tests only
make test-integration  # Integration tests only
make test-coverage     # Tests with coverage

# Code quality
make lint              # Linting with ruff
make format            # Format with black
make type-check        # Type checking with mypy
make quality           # All quality checks
```

### Frontend Development
```bash
# Dashboard (main SRE interface)
cd dashboard
npm run dev            # Development server
npm run build          # Production build
npm run test:run       # Run tests
npm run lint           # ESLint

# Alert Dev UI (testing interface)
cd alert-dev-ui
PORT=3001 npm start    # Development server
npm run build          # Production build
```

### Service URLs (Development)
- **TARSy Dashboard**: http://localhost:5173 (operational monitoring)
- **Alert Dev UI**: http://localhost:3001 (alert testing)
- **Backend API**: http://localhost:8000 (docs at /docs)

## Architecture Overview

### Multi-Layer Agent System
The system uses a sophisticated three-layer architecture:

1. **Orchestrator Layer** (`tarsy/main.py`): Routes alerts to specialized agents based on alert type
2. **Specialized Agents** (`tarsy/agents/`): Domain-specific agents (KubernetesAgent, ConfigurableAgent) with focused MCP server subsets
3. **Base Agent** (`tarsy/agents/base_agent.py`): Common processing logic shared across all specialized agents

### Key Components

#### Backend (`backend/tarsy/`)
- **Main Application**: `main.py` - FastAPI app with WebSocket support
- **Agents**: `agents/` - BaseAgent, KubernetesAgent, ConfigurableAgent, PromptBuilder
- **Services**: `services/` - AlertService, HistoryService, AgentRegistry, WebSocketManager
- **Models**: `models/` - Pydantic models for alerts, history, API schemas
- **Integrations**: `integrations/` - LLM clients (OpenAI, Google, xAI), MCP client
- **Configuration**: `config/` - Settings, agent configuration loading

#### Frontend Applications
- **Dashboard** (`dashboard/`): React TypeScript SRE dashboard with real-time monitoring
- **Alert Dev UI** (`alert-dev-ui/`): React TypeScript development interface for testing

### Configuration-Based Agents (EP-0006)
The system supports defining new agents through YAML configuration without code changes:

- **Configuration File**: `config/agents.yaml` (see `config/agents.yaml.example`)
- **Template Variables**: Use `${VAR}` syntax for environment-specific values
- **Mixed Architecture**: Configured and hardcoded agents work simultaneously
- **MCP Server Assignment**: Agents specify which MCP servers they use

## Working with Agents

### Creating New Hardcoded Agents
1. Extend `BaseAgent` in `backend/tarsy/agents/`
2. Implement required abstract methods: `mcp_servers()`, `custom_instructions()`
3. Register in `AgentRegistry` (`backend/tarsy/services/agent_registry.py`)
4. Add alert type mappings

### Creating Configuration-Based Agents
1. Copy `config/agents.yaml.example` to `config/agents.yaml`
2. Define agent with alert types and MCP servers
3. Set environment variables for template substitution
4. System automatically registers the agent

### Agent Capabilities
- **LLM-First Processing**: Agents receive complete JSON payloads for intelligent interpretation
- **Iterative Analysis**: Multi-step tool selection with up to 10 LLM→MCP iterations
- **Tool Selection**: Intelligent MCP tool selection based on alert context and runbooks
- **Progress Tracking**: Real-time status updates via WebSocket

## History and Monitoring System (EP-0003)

### Database
- **Default**: SQLite (`history.db`) for development
- **Production**: PostgreSQL support via `HISTORY_DATABASE_URL`
- **Models**: SQLModel-based with timeline logging

### History Service
- **Comprehensive Logging**: All LLM interactions and MCP communications
- **Session Management**: Complete alert processing workflows
- **API Endpoints**: REST API with filtering and pagination
- **Retention**: Configurable retention period (default 90 days)

### Dashboard Integration
- **Real-time Updates**: WebSocket-based live monitoring
- **Historical Analysis**: Session filtering and search
- **Timeline Visualization**: Chronological view of processing steps

## Testing Strategy

### Backend Tests
- **Unit Tests**: `backend/tests/unit/` - Component-level testing
- **Integration Tests**: `backend/tests/integration/` - End-to-end workflows
- **Fixtures**: `backend/tests/conftest.py` - Shared test fixtures
- **Mocking**: External services mocked for reliable testing

### Test Environment
- **Automatic Detection**: Tests use in-memory SQLite database
- **Environment Variable**: Set `TESTING=true` for explicit test mode
- **Parallel Execution**: `pytest -n auto` for faster test runs

## Data Flow and Processing

### Alert Processing Pipeline
1. **Alert Submission**: Flexible JSON structure via `/alerts` endpoint
2. **Validation**: Pydantic models ensure data integrity
3. **Agent Selection**: AgentRegistry routes to appropriate specialized agent
4. **History Session**: Created for complete audit trail
5. **Runbook Download**: GitHub runbook retrieval and agent distribution
6. **Iterative Analysis**: Agent uses LLM + MCP tools iteratively
7. **Real-time Updates**: WebSocket broadcasts to dashboard
8. **Final Analysis**: Comprehensive result with processing history

### WebSocket Channels
- **Alert Progress**: `/ws/{alert_id}` - Individual alert status updates
- **Dashboard**: `/ws/dashboard/{user_id}` - Real-time operational monitoring

## Important Implementation Notes

### MCP Integration
- **Client**: Official `mcp` library with agent-specific server assignments
- **Server Registry**: Centralized configuration and template variable support
- **Hook Context**: Transparent interaction capture for history service
- **Tool Validation**: Agents restricted to their assigned MCP server subset

### LLM Support
- **Providers**: OpenAI, Google Gemini, xAI with unified client interface
- **Configuration**: Provider selection via `DEFAULT_LLM_PROVIDER` environment variable
- **API Keys**: Separate environment variables for each provider
- **Interaction Logging**: All LLM calls automatically captured for audit

### Security and Data Handling
- **Flexible Alerts**: Accept arbitrary JSON from any monitoring system
- **Input Sanitization**: XSS prevention and payload size limits
- **Data Masking**: Optional PII/sensitive data protection for MCP responses
- **Concurrent Processing**: Semaphore-based concurrency control

### Development Environment
- **UV Package Manager**: Fast Python dependency management
- **Docker Compose**: Available for containerized development
- **Hot Reload**: Both backend (uvicorn) and frontend (Vite) support hot reload
- **Environment Files**: `.env` files for configuration (see `backend/env.template`)

## Troubleshooting

### Common Issues
- **Missing API Keys**: Check `.env` file for LLM provider API keys
- **Database Errors**: Ensure database permissions and connectivity
- **MCP Server Failures**: Verify MCP server configurations and environment variables
- **Agent Registration**: Check agent configuration syntax and alert type conflicts

### Debugging
- **Logs**: Application logs in `backend/logs/`
- **Database**: SQLite browser for history database inspection
- **WebSocket**: Browser dev tools for real-time connection debugging
- **API Documentation**: http://localhost:8000/docs for interactive API testing