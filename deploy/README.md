# TARSy OpenShift Deployment

Simple deployment for TARSy on OpenShift for development and testing.

## Overview

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
```

### 2. Create Configuration Files
```bash
# Create your deployment configuration files in the deploy directory:
mkdir -p deploy/kustomize/base/config

# Copy and customize from examples:
cp config/agents.yaml.example deploy/kustomize/base/config/agents.yaml
cp config/llm_providers.yaml.example deploy/kustomize/base/config/llm_providers.yaml
cp config/oauth2-proxy-container.cfg.example deploy/kustomize/base/config/oauth2-proxy-container.cfg

# Edit the deployment config files:
vi deploy/kustomize/base/config/agents.yaml          # Define your agents and runbooks
vi deploy/kustomize/base/config/llm_providers.yaml   # Configure LLM provider settings
vi deploy/kustomize/base/config/oauth2-proxy-container.cfg  # OAuth2 proxy settings (optional)
```

**Note**: These files are automatically created from examples during deployment if missing.

## Usage

### Complete Deployment
```bash
# Build images, create secrets, and deploy
make openshift-dev
```

This will:
1. ✅ Check environment variables are set
2. ✅ Create secrets from environment variables
3. ✅ Check/copy config files from examples
4. ✅ Build and push images to OpenShift registry
5. ✅ Deploy all manifests to `tarsy-dev` namespace
6. ✅ Show application URLs

### Development Iterations
```bash
# After code changes, rebuild and redeploy
make openshift-redeploy

# After config file changes, redeploy manifests
make openshift-deploy-only

# Just update manifests (no image rebuild)
make openshift-quick
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