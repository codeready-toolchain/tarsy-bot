# TARSy Deployment

Deployment options for TARSy in various environments.

## Deployment Options

### 1. Local Container Deployment (podman-compose)
For local development with containerized services:
```bash
make containers-deploy
```
See main [README.md](../README.md) for details.

### 2. OpenShift/Kubernetes Deployment
For deploying to OpenShift clusters (this guide):
```bash
make openshift-deploy
```

---

## OpenShift Deployment Guide

Simple deployment for TARSy on OpenShift for development and testing.

### Overview

Deploys TARSy stack to OpenShift using local builds + internal registry:
- **Backend**: Python FastAPI + OAuth2-proxy sidecar
- **Dashboard**: React frontend  
- **Database**: PostgreSQL with persistent storage

## Prerequisites

1. **OpenShift CLI**: `oc` command available
2. **Podman**: Already used by this project
3. **OpenShift Login**: `oc login https://your-cluster.com`
4. **Exposed Registry**: OpenShift internal registry must be exposed (one-time cluster setup)

### One-Time Registry Setup
```bash
# Requires cluster-admin privileges
oc patch configs.imageregistry.operator.openshift.io/cluster \
  --patch '{"spec":{"defaultRoute":true}}' --type=merge
```

## Configuration

### 1. Set Environment Variables

You have two options:

**Option A: Use environment file (recommended)**
```bash
# Copy the template
cp deploy/openshift.env.template deploy/openshift.env

# Edit with your values
vi deploy/openshift.env

# The Makefile will automatically load it when you run OpenShift targets (e.g., make openshift-dev)
# This file is ONLY loaded for openshift-* targets, not for local dev targets
```

**Option B: Export manually**
```bash
# Required: LLM API keys
export GOOGLE_API_KEY=your-actual-google-api-key-here
export GITHUB_TOKEN=your-github-token-here

# Optional: Additional LLM providers
export OPENAI_API_KEY=your-openai-api-key
export ANTHROPIC_API_KEY=your-anthropic-api-key
export XAI_API_KEY=your-xai-api-key

# Optional: OAuth2 settings (for authentication)
export OAUTH2_CLIENT_ID=your-oauth-client-id
export OAUTH2_CLIENT_SECRET=your-oauth-client-secret

# Optional: MCP Kubernetes server configuration (for in-cluster k8s access)
# Provides kubeconfig for the kubernetes-server MCP to access the cluster
# Portable (Linux/macOS): use base64 | tr -d '\n' to produce single-line output
export MCP_KUBECONFIG_CONTENT="$(cat ~/.kube/config | base64 | tr -d '\n')"
# Linux-only alternative: export MCP_KUBECONFIG_CONTENT="$(cat ~/.kube/config | base64 -w 0)"
# macOS-only alternative: export MCP_KUBECONFIG_CONTENT="$(cat ~/.kube/config | base64 -b 0)"

# Optional: JWT authentication (for API token validation)
# Public key for validating JWT tokens if you need TARSy backend to accept service account tokens for machine-to-machine communication
# Portable (Linux/macOS): use base64 | tr -d '\n' to produce single-line output
export JWT_PUBLIC_KEY_CONTENT="$(cat config/keys/jwt_public_key.pem | base64 | tr -d '\n')"
# Linux-only alternative: export JWT_PUBLIC_KEY_CONTENT="$(cat config/keys/jwt_public_key.pem | base64 -w 0)"
# macOS-only alternative: export JWT_PUBLIC_KEY_CONTENT="$(cat config/keys/jwt_public_key.pem | base64 -b 0)"
```

### 2. Create Configuration Files
```bash
# Create your deployment configuration files in the deploy directory:
mkdir -p deploy/kustomize/base/config

# Copy and customize from examples:
cp config/agents.yaml.example deploy/kustomize/base/config/agents.yaml
cp config/llm_providers.yaml.example deploy/kustomize/base/config/llm_providers.yaml
cp config/oauth2-proxy-container.cfg.template deploy/kustomize/base/config/oauth2-proxy-container.cfg

# Edit the deployment config files:
vi deploy/kustomize/base/config/agents.yaml          # Define your agents and runbooks
vi deploy/kustomize/base/config/llm_providers.yaml   # Configure LLM provider settings
vi deploy/kustomize/base/config/oauth2-proxy-container.cfg  # OAuth2 proxy settings (see config/README.md)
```

**Note**: These files are automatically created from examples during deployment if missing.

For detailed OAuth2 configuration (client IDs, secrets, GitHub org/team), see **[config/README.md](../config/README.md)**.

## Usage

### Complete Deployment
```bash
# Build images, create secrets, and deploy
make openshift-deploy
```

**Note**: If `deploy/openshift.env` exists, it will be automatically loaded when running OpenShift targets. This file does NOT affect local development targets (like `make dev`). If the file doesn't exist, ensure environment variables are exported manually.

This will:
1. ✅ Load environment variables (from `deploy/openshift.env` if present)
2. ✅ Check environment variables are set
3. ✅ Create secrets from environment variables
4. ✅ Check/copy config files from examples
5. ✅ Build and push images to OpenShift registry
6. ✅ Deploy all manifests to `tarsy-dev` namespace

### Development Iterations
```bash
# After code changes, rebuild and redeploy
make openshift-redeploy

# After config file changes, just apply manifests
make openshift-apply

# Show application URLs
make openshift-urls
```

### Check Status
```bash
# View deployment status
make openshift-status

# Get application URLs  
make openshift-urls

# View backend logs
make openshift-logs
```

### Cleanup
```bash
# Remove everything
make openshift-clean
```

## Access

After deployment, access via the URLs shown by `make openshift-urls`:
- **Dashboard**: `https://tarsy-dev.apps.your-cluster.com`
- **API**: `https://tarsy-dev.apps.your-cluster.com/api`

## Architecture

**Environment Variables → OpenShift Secrets**: API keys and sensitive data  
**Config Files → ConfigMaps**: Agents, LLM providers, OAuth2 settings  
**Kustomize**: Clean application manifests that reference secrets and configs  

### Configuration File Workflow:
1. **Users edit**: `deploy/kustomize/base/config/agents.yaml` (and other config files)
2. **Make targets sync**: Files to `overlays/development/` (temporary)
3. **Kustomize generates**: ConfigMaps from overlay files
4. **Containers mount**: ConfigMaps as `/app/config/*.yaml`
5. **Git ignores**: User-specific config files (never committed)

**Production Ready**: 
- Secrets can come from external secret managers instead of templates
- Config files can be maintained in production overlays  
- Application manifests remain unchanged

## Troubleshooting

**"GOOGLE_API_KEY not set"**: Set required environment variables above  
**"Registry not found"**: Registry not exposed - run the one-time setup above  
**"Not logged in"**: Run `oc login https://your-cluster.com`  
**"Config file not found"**: Files are auto-copied from examples, customize as needed  

**Note**: This deployment is for development/testing only. For production, use separate repositories with production overlays and external secret management.