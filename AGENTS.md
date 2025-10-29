# TARSy Project

**TARSy** is an AI-powered SRE system that processes alerts through sequential agent chains using MCP (Model Context Protocol) servers for multi-stage incident analysis.

# Project Structure

- `/backend` - Python 3.13+ FastAPI backend with async agent orchestration
- `/dashboard` - React/TypeScript SRE dashboard with real-time WebSocket updates
- `/config` - YAML-based agent and LLM provider configurations
- `/docs` - Architecture and enhancement proposals

# Technology Stack

## Backend (Python 3.13+)
- **Framework:** FastAPI with async/await
- **Agent Framework:** LangChain with custom sequential chains
- **Tooling:** Black (formatting), Ruff (linting), pytest (testing)
- **Type Hints:** Mandatory for all functions, methods, and class members
- **Environment:** uv for dependency management
- **Containers:** podman, podman-compose

## Dashboard (TypeScript/React)
- **Framework:** React 19+ with TypeScript 5+
- **Build Tool:** Vite
- **UI:** Material-UI (MUI) with custom theme
- **Real-time:** WebSocket for LLM streaming
- **Testing:** Vitest, React Testing Library

# TARSy-Specific Patterns

## Agent Architecture
- Agents extend `BaseAgent` and implement `mcp_servers()` and `custom_instructions()`
- Support both hardcoded agents (Python classes) and configuration-based agents (YAML)
- Agents work in sequential stages, building upon previous stage results
- Each agent specifies its MCP server subset for domain-specific tools

## Configuration-Based Development
- Agent definitions: `config/agents.yaml` with template variable support `${VAR}`
- LLM providers: `config/llm_providers.yaml` for multi-provider support
- Runbook integration: Automatic GitHub runbook retrieval per agent chain

## Hook System & Audit Trail
- Hooks capture all LLM interactions for complete audit trails
- `on_llm_new_token`, `on_llm_end`, `on_tool_start`, `on_tool_end`
- Database persistence for timeline reconstruction and compliance

## MCP Integration
- MCP servers provide domain-specific tools to agents (kubectl, db clients, etc.)
- Server lifecycle managed per agent execution
- Tool calls logged and captured via hook system

# Code Standards

## Python (Backend)
- PEP 8 compliance, enforced by Ruff
- Type annotations required (use `typing` module)
- Async/await preferred for I/O operations
- Google-style docstrings for public APIs
- Specific exception types with clear error messages
- Import order: stdlib → third-party → local (auto-sorted by Ruff)

## TypeScript (Dashboard)
- Strict type checking enabled
- Functional components with hooks
- Proper error boundaries and loading states
- WebSocket connection management with reconnection logic
- Material-UI theming consistency

# Essential Commands

```bash
# Development
make setup              # Initial project setup (one-time)
make dev                # Start backend and dashboard in dev mode
make test               # Run all tests (backend + dashboard)
make lint               # Format and lint all code

# Testing
make test-backend       # Backend tests only
make test-dashboard     # Dashboard tests only
make test-coverage      # Generate coverage reports

# Database
make db-migrate         # Run pending migrations
make db-revision        # Create new migration

# Containers
make containers-up      # Start all services via podman-compose
make containers-clean   # Clean up containers and volumes
```

# Development Guidelines

- **Security First:** Mask sensitive data in logs, validate all external inputs
- **Keep It Simple:** Avoid over-engineering; prefer maintainable solutions
- **Configuration Over Code:** Use YAML configs for new agents when possible
- **Test Coverage:** Maintain high test coverage, especially for agent logic
- **Documentation:** Update docs when changing architecture or adding features
- **Web Search:** Use web search for unfamiliar technologies or recent developments
