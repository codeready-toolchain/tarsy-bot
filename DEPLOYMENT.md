# Tarsy-bot - Deployment Guide 🚀

This guide covers advanced deployment scenarios, production setup, and troubleshooting for tarsy.

## Documentation Overview

- **[README.md](README.md)**: Project overview, features, and quick start
- **[Makefile](Makefile)**: Development workflow automation (recommended for first-time users)
- **[DEPLOYMENT.md](DEPLOYMENT.md)**: This file - advanced deployment and development
- **[docs/requirements.md](docs/requirements.md)**: Application requirements and specifications
- **[docs/design.md](docs/design.md)**: System design and architecture documentation

> **Quick Start**: If you're new to the project, run `make setup` for automated setup.

## Overview

Tarsy-bot consists of three main components:
- **Backend**: FastAPI service (Python)
- **Alert Dev UI**: React application (Node.js)
- **MCP Server**: Kubernetes integration via npx

## Environment Variables

All environment variables are documented in `backend/env.template`. Key variables:

### Required
- **LLM API Keys**: `GEMINI_API_KEY`, `OPENAI_API_KEY`, or `GROK_API_KEY`
- **GitHub Token**: `GITHUB_TOKEN` (for runbook access)

### Optional
- **MCP Configuration**: Automatically handled via npx
- **CORS Origins**: `CORS_ORIGINS` (default: localhost:3001)
- **Default LLM**: `DEFAULT_LLM_PROVIDER` (default: gemini)

## Manual Development Setup

> **Note**: For automated setup, use `make setup` instead of these manual steps.

### 1. Backend Setup

```bash
cd backend

# Install dependencies using uv
uv sync

# Create environment file
cp env.template .env
# Edit .env with your API keys

# Start the server
source .venv/bin/activate
uvicorn tarsy.main:app --reload --port 8000
```

### 2. Alert Dev UI Setup

```bash
cd alert-dev-ui

# Install dependencies
npm install

# Start development server (with custom port)
PORT=3001 npm start
```

### 3. Service URLs

- **Alert Dev UI**: http://localhost:3001
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **MCP Server**: Automatically started via npx

## MCP Server Configuration

The application uses the official MCP SDK to automatically start MCP servers. Built-in servers like Kubernetes are configured centrally, while custom servers can be added through YAML configuration.

### Template Variable Support

MCP server configurations now support **template variables** using `${VARIABLE_NAME}` syntax for environment-specific values:

```yaml
# In config/agents.yaml
mcp_servers:
  security-server:
    server_id: "security-server"
    server_type: "security"
    enabled: true
    connection_params:
      command: "/opt/security-mcp/server"
      # Template variables resolved from environment or defaults
      args: ["--token", "${SECURITY_SERVER_TOKEN}", "--kubeconfig", "${KUBECONFIG}"]
```

**Environment Variables in .env:**
```env
# Required - no default available
SECURITY_SERVER_TOKEN=your_secret_token_here

# Optional - has built-in default (expands to absolute path like /home/user/.kube/config)
# Always use absolute paths - tilde expansion only works for built-in defaults
KUBECONFIG=/custom/path/to/kubeconfig
```

### Built-in Server Configuration

1. **Kubernetes Server**: Automatically started with template support
   ```bash
   # Uses KUBECONFIG environment variable or expanded absolute path default
   npx -y kubernetes-mcp-server@latest --kubeconfig ${KUBECONFIG}
   ```

2. **Configuration Location**: Built-in servers configured in `backend/tarsy/config/builtin_config.py`

3. **Template Resolution**: Environment variables are resolved at startup:
   - **Environment First**: `KUBECONFIG=/custom/path` takes precedence  
   - **Settings Defaults**: Falls back to expanded absolute path (e.g., `/home/user/.kube/config`) if `KUBECONFIG` not set
   - **Tilde Expansion**: Built-in defaults automatically expand `~` to the user's home directory
   - **Error Handling**: Missing required variables without defaults cause fallback to original config

   **⚠️ Important**: When setting custom kubeconfig paths, always use absolute paths. The `~` character is only expanded for built-in defaults, not for user-provided environment variables.

4. **Communication**: Uses stdio-based communication via the MCP SDK

### For Testing Without Kubernetes

If you need to test without a real Kubernetes cluster, you can create a mock MCP server:

```bash
# Create a simple mock server script
cat > mock_mcp_server.py << 'EOF'
#!/usr/bin/env python3
"""Mock MCP Server for testing tarsy-bot"""

import asyncio
import json
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Create server instance
server = Server("mock-kubernetes-mcp")

@server.list_tools()
async def list_tools():
    """List available tools"""
    return [
        Tool(
            name="get_namespace",
            description="Get namespace information",
            inputSchema={
                "type": "object",
                "properties": {
                    "namespace": {"type": "string", "description": "Namespace name"}
                },
                "required": ["namespace"]
            }
        ),
        Tool(
            name="describe_pods",
            description="Describe pods in a namespace",
            inputSchema={
                "type": "object", 
                "properties": {
                    "namespace": {"type": "string", "description": "Namespace name"}
                },
                "required": ["namespace"]
            }
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict):
    """Handle tool calls"""
    if name == "get_namespace":
        namespace = arguments.get("namespace", "default")
        return [TextContent(
            type="text",
            text=f"Mock namespace info for '{namespace}': Status=Active, CreationTime=2023-01-01T00:00:00Z"
        )]
    elif name == "describe_pods":
        namespace = arguments.get("namespace", "default")
        return [TextContent(
            type="text",
            text=f"Mock pods in namespace '{namespace}': pod-1 (Running), pod-2 (Pending)"
        )]
    else:
        raise ValueError(f"Unknown tool: {name}")

async def main():
    """Run the mock MCP server"""
    async with stdio_server() as streams:
        await server.run(streams[0], streams[1])

if __name__ == "__main__":
    asyncio.run(main())
EOF

chmod +x mock_mcp_server.py
```

Then update your MCP server configuration to use the mock server instead of the real one.

## Docker Deployment

### 1. Build and Run with Docker Compose

```bash
# Build all services
docker-compose build

# Start all services
docker-compose up -d

# View logs
docker-compose logs -f
```

### 2. Individual Service Deployment

#### Backend Docker

```bash
cd backend

# Create Dockerfile
cat > Dockerfile << 'EOF'
FROM python:3.11-slim

WORKDIR /app

# Install uv
RUN pip install uv

# Copy project files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-dev

# Copy application
COPY . .

# Expose port
EXPOSE 8000

# Run application
CMD ["uv", "run", "uvicorn", "tarsy.main:app", "--host", "0.0.0.0", "--port", "8000"]
EOF

# Build and run
docker build -t tarsy-backend .
docker run -p 8000:8000 --env-file .env tarsy-backend
```

#### Alert Dev UI Docker

```bash
cd alert-dev-ui

# Create Dockerfile
cat > Dockerfile << 'EOF'
FROM node:18-alpine as builder

WORKDIR /app
COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
EOF

# Create nginx.conf
cat > nginx.conf << 'EOF'
server {
    listen 80;
    location / {
        root /usr/share/nginx/html;
        index index.html index.htm;
        try_files $uri $uri/ /index.html;
    }
    
    location /api {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
EOF

# Build and run
docker build -t tarsy-alert-dev-ui .
docker run -p 3001:80 tarsy-alert-dev-ui
```

## Production Deployment

### 1. Environment Setup

```bash
# Create production environment file
cp backend/env.template backend/.env.prod

# Set production values
vim backend/.env.prod
```

### 2. Security Considerations

- **API Keys**: Store in secure key management system
- **CORS**: Configure proper CORS origins for production domain
- **HTTPS**: Enable SSL/TLS for all communications
- **Authentication**: Add authentication layer for production use
- **Rate Limiting**: Implement rate limiting for API endpoints

### 3. Kubernetes Deployment

Create Kubernetes manifests:

```yaml
# backend-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: tarsy-backend
spec:
  replicas: 3
  selector:
    matchLabels:
      app: tarsy-backend
  template:
    metadata:
      labels:
        app: tarsy-backend
    spec:
      containers:
      - name: backend
        image: tarsy-backend:latest
        ports:
        - containerPort: 8000
        envFrom:
        - secretRef:
            name: tarsy-secrets
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "1Gi"
            cpu: "500m"
---
apiVersion: v1
kind: Service
metadata:
  name: tarsy-backend-service
spec:
  selector:
    app: tarsy-backend
  ports:
  - port: 8000
    targetPort: 8000
  type: ClusterIP
```

## Testing the Deployment

### 1. Health Check

```bash
# Backend health
curl http://localhost:8000/health

# Expected response:
# {"status": "healthy", "service": "tarsy"}
```

### 2. Test Alert Submission

```bash
# Submit a test alert
curl -X POST http://localhost:8000/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "alert": "NamespaceTerminating",
    "severity": "warning",
    "environment": "production",
    "cluster": "https://api.test-cluster.example.com:6443",
    "namespace": "test-namespace",
    "message": "namespace is stuck in Terminating phase",
    "runbook": "https://github.com/codeready-toolchain/sandbox-sre/blob/master/runbooks/namespace-terminating.md"
  }'

# Expected response:
# {"alert_id": "uuid-here", "status": "queued", "message": "Alert submitted for processing"}
```

### 3. Monitor Processing

```bash
# Check processing status
curl http://localhost:8000/processing-status/{alert_id}

# Or connect to WebSocket for real-time updates
# ws://localhost:8000/ws/{alert_id}
```

## Troubleshooting

### Common Issues

1. **Backend fails to start**
   - Check API keys are set correctly
   - Verify Python dependencies are installed
   - Check port 8000 is available

2. **Alert Dev UI can't connect to backend**
   - Verify backend is running on port 8000
   - Check CORS configuration
   - Verify proxy setting in package.json

3. **MCP Server connection failed**
   - Ensure Kubernetes MCP server is running on port 8080
   - Check network connectivity
   - Verify MCP server is responding to health checks

4. **LLM API errors**
   - Verify API keys are valid and have sufficient quota
   - Check internet connectivity
   - Try different LLM provider

### Logs

```bash
# Backend logs
tail -f backend/logs/tarsy.log

# Docker logs
docker-compose logs -f backend
docker-compose logs -f alert-dev-ui

# Check specific service
docker logs tarsy-backend
```

## Monitoring

### Health Endpoints

- `GET /health` - Backend health status
- `GET /` - Basic service status
- `GET /alert-types` - Supported alert types

### Metrics

Consider implementing:
- Processing time metrics
- Success/failure rates
- LLM token usage
- WebSocket connection counts

## Development

### Adding New LLM Providers

To add a new LLM provider:

1. **Update Settings**: Add the provider configuration to `llm_providers` in `backend/app/config/settings.py`:
   ```python
   llm_providers: Dict = Field(default={
       # ... existing providers ...
       "new_provider": {
           "model": "new-model-name",
           "api_key_env": "NEW_PROVIDER_API_KEY",
           "type": "new_provider"
       }
   })
   ```

2. **Add LangChain Integration**: Update `LLM_PROVIDERS` mapping in `backend/app/integrations/llm/client.py`:
   ```python
   LLM_PROVIDERS = {
       # ... existing providers ...
       "new_provider": lambda temp, api_key, model: NewProviderChat(
           model=model or "default-model",
           api_key=api_key,
           temperature=temp
       ),
   }
   ```

3. **Update Environment Template**: Add the new API key field to `backend/env.template`:
   ```env
   # New Provider API Key
   NEW_PROVIDER_API_KEY=your_new_provider_api_key_here
   ```

4. **Update Settings Class**: Add the new API key field to the `Settings` class:
   ```python
   new_provider_api_key: str = Field(default="")
   ```

5. **Update get_llm_config Method**: Add the new provider to the method:
   ```python
   def get_llm_config(self, provider: str) -> Dict:
       # ... existing code ...
       elif provider == "new_provider":
           config["api_key"] = self.new_provider_api_key
   ```

The system uses LangChain for unified LLM access, so any LangChain-compatible provider can be easily integrated.

### Adding New MCP Servers

Add custom MCP servers through **YAML configuration** without code changes:

1. **Create Configuration**: Add to `config/agents.yaml`:
   ```yaml
   mcp_servers:
     monitoring-server:
       server_id: "monitoring-server"
       server_type: "monitoring"
       enabled: true
       connection_params:
         command: "monitoring-mcp-server"
         # Use template variables for sensitive/environment-specific values
         args: ["--prometheus-url", "${PROMETHEUS_URL}", "--grafana-token", "${GRAFANA_TOKEN}"]
         environment:
           LOG_LEVEL: "info"
       instructions: |
         Monitoring server instructions:
         - Query Prometheus for metrics and alerts
         - Access Grafana dashboards for visualization
         - Provide performance insights and recommendations
   ```

2. **Set Environment Variables**: Add to `backend/.env`:
   ```env
   # Required environment variables for template resolution
   PROMETHEUS_URL=http://prometheus:9090
   GRAFANA_TOKEN=your_grafana_api_token_here
   ```

3. **Assign to Agents**: Reference the server in agent configurations:
   ```yaml
   agents:
     performance-agent:
       alert_types: ["HighCPU", "HighMemory", "DiskSpaceFull"]
       mcp_servers: ["monitoring-server", "kubernetes-server"]  # Built-in + custom
   ```

**Template Variable Features:**
- **Environment Resolution**: `${VAR}` resolved from environment variables
- **Settings Defaults**: Built-in defaults for common variables (e.g., `KUBECONFIG`)
- **Error Handling**: Missing variables without defaults trigger fallback behavior
- **Secure**: Keeps sensitive values out of configuration files

The MCP client will automatically initialize and use the new server with resolved template variables.

## Support

For issues and questions:
1. Check the logs for error messages
2. Verify all prerequisites are met
3. Test with a simple alert submission
4. Check MCP server connectivity
5. See [README.md](README.md) for basic usage
6. Run `./setup.sh` for automated setup

Tarsy-bot is now ready for deployment and use! 