[![CI Pipeline](https://github.com/codeready-toolchain/tarsy-bot/workflows/CI%20Pipeline/badge.svg)](https://github.com/codeready-toolchain/tarsy-bot/actions)
[![codecov](https://codecov.io/gh/codeready-toolchain/tarsy-bot/branch/master/graph/badge.svg)](https://codecov.io/gh/codeready-toolchain/tarsy-bot)

<div align="center">
  <img src="./docs/img/TARSy-logo.png" alt="TARSy" width="100"/>
</div>

**TARSy** (Thoughtful Alert Response System) is an intelligent Site Reliability Engineering system that automatically processes alerts through sequential agent chains, retrieves runbooks, and uses MCP (Model Context Protocol) servers to gather system information for comprehensive multi-stage incident analysis.

Inspired by the spirit of sci-fi AI, TARSy is your reliable companion for SRE operations. 🚀

[tarsy.webm](https://github.com/user-attachments/assets/fc7fa6d1-fdc7-4ccb-b1eb-7e52b2abd617)

## Documentation

- **[README.md](README.md)**: This file - project overview and quick start
- **[docs/architecture-overview.md](docs/architecture-overview.md)**: High-level architecture concepts and design principles
- **[docs/functional-areas-design.md](docs/functional-areas-design.md)**: Functional areas design and architecture documentation

## Prerequisites

### For Development Mode
- **Python 3.13+** - Core backend runtime
- **Node.js 18+** - Frontend development and build tools  
- **npm** - Node.js package manager (comes with Node.js)
- **uv** - Modern Python package and project manager
  - Install: `pip install uv`
  - Alternative: `curl -LsSf https://astral.sh/uv/install.sh | sh`

### For Container Deployment (Additional)
- **Podman** (or Docker) - Container runtime
- **podman-compose** - Multi-container application management
  - Install: `pip install podman-compose`

> **Quick Check**: Run `make check-prereqs` to verify all prerequisites are installed.

## Quick Start

### Development Mode (Direct Backend)

```bash
# 1. Initial setup (one-time only)
make setup

# 2. Configure API keys (REQUIRED)
# Edit backend/.env and set your API keys:
# - GOOGLE_API_KEY (get from https://aistudio.google.com/app/apikey)
# - GITHUB_TOKEN (get from https://github.com/settings/tokens)

# 3. Ensure Kubernetes/OpenShift access (REQUIRED)
# See [K8s Access Requirements](#k8s-access-reqs) section below for details

# 4. Start all services  
make dev
```

**Services will be available at:**
- 🖥️ **TARSy Dashboard**: http://localhost:5173
  - Manual Alert Submission: http://localhost:5173/submit-alert
- 🔧 **Backend API**: http://localhost:8000 (docs at /docs)

**Stop all services:** `make stop`

### Container Deployment (Production-like)

For production-like testing with containerized services, authentication, and database:

```bash
# 1. Initial setup (one-time only)
make setup

# 2. Configure API keys and OAuth (REQUIRED)
# Edit backend/.env and set your API keys + OAuth configuration
# - See config/README.md for OAuth2 proxy customization (client IDs, secrets, org/team)
# - See docs/oauth2-proxy-setup.md for detailed GitHub OAuth setup guide
# - Configure LLM providers in backend/.env (GOOGLE_API_KEY, etc.)

# 3. Deploy complete containerized stack
make containers-deploy        # Preserves database data (recommended)
# OR for fresh start:
make containers-deploy-fresh  # Clean rebuild including database
```

**Services will be available at:**
- 🖥️ **TARSy Dashboard**: http://localhost:8080 (with OAuth authentication)
- 🔧 **Backend API**: http://localhost:8080/api (protected by OAuth2-proxy)
- 🗄️ **PostgreSQL Database**: localhost:5432 (admin access)

**Container Management:**
- **Update apps (preserve database):** `make containers-deploy`
- **Fresh deployment:** `make containers-deploy-fresh` 
- **Stop containers:** `make containers-stop`
- **View logs:** `make containers-logs` 
- **Check status:** `make containers-status`
- **Clean up:** `make containers-clean` (removes all containers and data)

### OpenShift/Kubernetes Deployment

For deploying TARSy to OpenShift or Kubernetes clusters:

```bash
# Complete deployment with local builds
make openshift-deploy
```

**📖 For complete OpenShift deployment guide**: See [deploy/README.md](deploy/README.md)

This deployment is designed for development and testing environments, serving as a reference for production deployments in separate repositories.

## Key Features

- **🛠️ Configuration-Based Agents**: Deploy new agents and chain definitions via YAML configuration without code changes
- **🔧 Flexible Alert Processing**: Accept arbitrary JSON payloads from any monitoring system  
- **🧠 Chain-Based Agent Architecture**: Specialized agents with domain-specific tools and AI reasoning working in coordinated stages
- **📊 Comprehensive Audit Trail**: Complete visibility into chain processing workflows with stage-level timeline reconstruction
- **🖥️ SRE Dashboard**: Real-time monitoring with live LLM streaming and interactive chain timeline visualization
- **💬 Follow-up Chat**: Continue investigating after sessions complete - ask clarifying questions, request deeper analysis, or explore different aspects with full context and tool access
- **⏸️ Pause & Resume**: Long-running investigations automatically pause at iteration limits and can be resumed with one click - preserves full conversation state and continues exactly where it left off
- **🔒 Data Masking**: Hybrid masking system combining code-based structural analysis (Kubernetes Secrets) with regex patterns (API keys, passwords, certificates, emails, SSH keys) to automatically protect sensitive data in MCP responses and alert payloads

## Architecture

Tarsy uses an AI-powered chain-based architecture where alerts flow through sequential stages of specialized agents that build upon each other's work using domain-specific tools to provide comprehensive expert recommendations to engineers.

> **📖 For high-level architecture concepts**: See [Architecture Overview](docs/architecture-overview.md)

## How It Works

1. **Alert arrives** from monitoring systems with flexible JSON payload
2. **Orchestrator selects** appropriate agent chain based on alert type  
3. **Runbook downloaded** automatically from GitHub for chain guidance
4. **Sequential stages execute** where each agent builds upon previous stage data using AI to select and execute domain-specific tools
5. **Automatic pause** if investigation reaches iteration limits - preserves full state and allows manual resume with one click
6. **Comprehensive multi-stage analysis** provided to engineers with actionable recommendations
7. **Follow-up chat available** after investigation completes - engineers can ask questions, request more comprehensive analysis, or explore different aspects
8. **Full audit trail** captured with stage-level detail for monitoring and continuous improvement

```mermaid
sequenceDiagram
    participant MonitoringSystem
    participant Orchestrator
    participant AgentChains
    participant GitHub
    participant AI
    participant MCPServers
    participant Dashboard
    participant Engineer

    MonitoringSystem->>Orchestrator: Send Alert
    Orchestrator->>AgentChains: Assign Alert & Context
    AgentChains->>GitHub: Download Runbook
    loop Investigation Loop
        AgentChains->>AI: Investigate with LLM
        AI->>MCPServers: Query/Actuate as needed
    end
    AgentChains->>Dashboard: Send Analysis & Recommendations
    Engineer->>Dashboard: Review & Take Action
```

## Usage

### Development Mode
1. **Start All Services**: Run `make dev` to start backend and dashboard
2. **Submit an Alert**: Use Manual Alert Submission at http://localhost:5173/submit-alert for testing TARSy
3. **Monitor via Dashboard**: Watch real-time progress updates and historical analysis at http://localhost:5173
4. **View Results**: See detailed processing timelines and comprehensive LLM analysis
5. **Stop Services**: Run `make stop` when finished

### Container Deployment Mode
1. **Deploy Stack**: Run `make containers-deploy` (preserves database) or `make containers-deploy-fresh` (clean start)
2. **Login**: Navigate to http://localhost:8080 and authenticate via GitHub OAuth
3. **Submit Alert**: Use the dashboard at http://localhost:8080/submit-alert (OAuth protected)
4. **Monitor Processing**: Watch real-time progress with full audit trail
5. **Stop Containers**: Run `make containers-stop` when finished

> **Tip**: Use `make status` or `make containers-status` to check which services are running.

## Container Architecture

The containerized deployment provides a production-like environment with:

- **🔐 OAuth2 Authentication**: GitHub OAuth integration via oauth2-proxy
- **🔄 Reverse Proxy**: Nginx handles all traffic routing and CORS  
- **🗄️ PostgreSQL Database**: Persistent storage for processing history
- **📦 Production Builds**: Optimized frontend and backend containers
- **🔒 Security**: All API endpoints protected behind authentication

**Architecture Overview:**
```
Browser → Nginx (8080) → OAuth2-Proxy → Backend (FastAPI)
                      ↘ Dashboard (Static Files)
```

**📖 For OAuth2-proxy setup instructions**: See [docs/oauth2-proxy-setup.md](docs/oauth2-proxy-setup.md)

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

<a id="k8s-access-reqs"></a>
## Kubernetes/OpenShift Access Requirements

TARSy requires read-only access to a Kubernetes or OpenShift cluster to analyze and troubleshoot Kubernetes infrastructure issues. The system uses the [**kubernetes-mcp-server**](https://github.com/containers/kubernetes-mcp-server), which connects to your cluster via kubeconfig.

### 🔗 How TARSy Accesses Your Cluster

TARSy **does not use `oc` or `kubectl` commands directly**. Instead, it:

1. **Uses [Kubernetes MCP Server](https://github.com/containers/kubernetes-mcp-server)**
2. **Reads kubeconfig**: Authenticates using your existing kubeconfig file
3. **Read-Only Operations**: Configured with `--read-only --disable-destructive` flags
4. **No Modifications**: Cannot create, update, or delete cluster resources

### ⚙️ Setup Instructions

#### Option 1: Use Existing Session (Recommended)
If you're already logged into your OpenShift/Kubernetes cluster:

```bash
# Verify your current access
oc whoami
oc cluster-info

# TARSy will automatically use your current kubeconfig
# Default location: ~/.kube/config or $KUBECONFIG
```

#### Option 2: Custom Kubeconfig
To use a specific kubeconfig file:

```bash
# Set in backend/.env
KUBECONFIG=/path/to/your/kubeconfig

# Or set environment variable
export KUBECONFIG=/path/to/your/kubeconfig
```

## API Endpoints

### Core API
- `GET /health` - Comprehensive health check with service status and warnings (HTTP 503 for degraded/unhealthy)
- `POST /api/v1/alerts` - Submit a new alert for processing (returns `session_id` immediately)
  - **Optional alert_type**: The `alert_type` field is optional and defaults to the configured default (typically "kubernetes")
  - **Custom MCP Configuration**: Optionally override default agent MCP server configuration via the `mcp` field in the request payload. This allows you to specify which MCP servers and tools to use for processing, providing fine-grained control over available tooling per alert.
- `GET /api/v1/alert-types` - Get supported alert types and default alert type
- `WebSocket /api/v1/ws` - Real-time progress updates via WebSocket with channel subscriptions

### History API
- `GET /api/v1/history/sessions` - List alert processing sessions with filtering and pagination
- `GET /api/v1/history/sessions/{session_id}` - Get detailed session with chronological timeline
- `POST /api/v1/history/sessions/{session_id}/resume` - Resume a paused session from where it left off
- `POST /api/v1/history/sessions/{session_id}/cancel` - Cancel an active or paused session

### Chat API
- `POST /api/v1/sessions/{session_id}/chat` - Create follow-up chat for a completed session
- `GET /api/v1/sessions/{session_id}/chat-available` - Check if chat is available for a session
- `POST /api/v1/chats/{chat_id}/messages` - Send message to chat (AI response streams via WebSocket)
- `GET /api/v1/chats/{chat_id}` - Get chat details

### System API
- `GET /api/v1/system/warnings` - Active system warnings (MCP/LLM init failures, etc.)
- `GET /api/v1/system/mcp-servers` - Get available MCP servers and their tools (used for custom MCP configuration)

## Development

### Adding New Components

- **Alert Types**: Define any alert type in `config/agents.yaml` - no hardcoding required, just create corresponding runbooks
- **MCP Servers**: Define custom MCP servers in `config/agents.yaml` with support for stdio, HTTP, and SSE transports. Can override built-in MCP servers (e.g., customize kubernetes-server with specific kubeconfig)
- **Agents**: Create traditional hardcoded agent classes extending BaseAgent, or define configuration-based agents in `config/agents.yaml`. Can override built-in agents to customize behavior
- **Chains**: Define multi-stage workflows in `config/agents.yaml`. Can override built-in chains to customize investigation workflows
- **LLM Providers**: Built-in providers work out-of-the-box (OpenAI, Google, xAI, Anthropic, Vertex AI). Add custom providers via `config/llm_providers.yaml` for proxy configurations or model overrides

> **📖 For detailed extensibility examples**: See [Extensibility section](docs/architecture-overview.md#extensibility) in the Architecture Overview

### Database Migrations

TARSy uses **Alembic** for database schema versioning and migrations. The migration system automatically applies pending migrations on startup, ensuring your database schema is always up-to-date.

**Quick Migration Workflow:**

```bash
# 1. Modify SQLModel in backend/tarsy/models/
# 2. Generate migration from model changes
make migration msg="Add new field to AlertSession"

# 3. Review generated file in backend/alembic/versions/
# 4. Test migration
make migration-upgrade

# 5. If needed, rollback
make migration-downgrade
```

**Available Migration Commands:**

```bash
make migration msg="Description"     # Generate migration from model changes
make migration-manual msg="Desc"     # Create empty migration for manual changes
make migration-upgrade               # Apply all pending migrations
make migration-downgrade             # Rollback last migration
make migration-status                # Show current database version
make migration-history               # Show full migration history
```

> **📖 For complete migration documentation**: See [docs/database-migrations.md](docs/database-migrations.md)

### Running Tests

```bash
# Run back-end and front-end (dashboard) tests
make test
```

The test suite includes comprehensive end-to-end integration tests covering the complete alert processing pipeline, agent specialization, error handling, and performance scenarios with full mocking of external services.
