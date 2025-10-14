# Configuration Reload on Change in Kubernetes/ArgoCD

> **Status**: Exploring options - not implemented yet
> 
> This document explores different approaches for automatically restarting pods when ConfigMaps or Secrets change in ArgoCD.

---

## Problem Statement

When ConfigMaps or Secrets are updated in the GitHub repository and synced by ArgoCD, the backend pods continue running with the old configuration. This requires manual pod restarts or deployment rollouts.

---

## Configuration Points in TARSy Backend

### ConfigMaps (File Mounts)
Backend pod mounts these files from ConfigMaps:

1. **agents-config** → `/app/config/agents.yaml`
   - Agent definitions
   - MCP server configurations
   - Agent chains

2. **llm-providers-config** → `/app/config/llm_providers.yaml`
   - Custom LLM provider configurations
   - Model specifications
   - API endpoints

3. **oauth2-config** → `/config/oauth2-proxy.cfg` (oauth2-proxy container)
   - OAuth2 proxy settings

4. **oauth2-templates** → `/templates/` (oauth2-proxy container)
   - Sign-in HTML
   - Logo files

### ConfigMap (Environment Variables)
**tarsy-config** ConfigMap provides environment variables:
- `LLM_PROVIDER` - Default LLM provider
- `HISTORY_ENABLED` - Enable/disable history
- `HISTORY_RETENTION_DAYS` - Data retention period
- `HOST`, `PORT` - Server configuration
- `LOG_LEVEL` - Logging verbosity
- `CORS_ORIGINS` - CORS configuration
- `AGENT_CONFIG_PATH`, `LLM_CONFIG_PATH` - Config file paths

### Secrets (Environment Variables)
1. **database-secret**:
   - `DATABASE_URL` - Complete PostgreSQL connection string

2. **tarsy-secrets**:
   - `GOOGLE_API_KEY`
   - `GITHUB_TOKEN`
   - `OPENAI_API_KEY` (optional)
   - `ANTHROPIC_API_KEY` (optional)
   - `XAI_API_KEY` (optional)

3. **oauth2-proxy-secret**:
   - `OAUTH2_PROXY_CLIENT_ID`
   - `OAUTH2_PROXY_CLIENT_SECRET`
   - `OAUTH2_PROXY_COOKIE_SECRET`

### Built-in Configuration (Code)
**Location**: `backend/tarsy/config/builtin_config.py`
- Built-in agents (KubernetesAgent)
- Built-in MCP servers
- Built-in LLM providers
- Built-in masking patterns

**Note**: Changes require image rebuild, not covered by ConfigMap/Secret reload solutions.

### Configuration Coverage

| Config Source | Type | All 3 Options Cover? | Notes |
|---------------|------|---------------------|-------|
| `agents-config` | ConfigMap (file) | ✅ Yes | |
| `llm-providers-config` | ConfigMap (file) | ✅ Yes | |
| `oauth2-config` | ConfigMap (file) | ✅ Yes | |
| `oauth2-templates` | ConfigMap (file) | ✅ Yes | |
| `tarsy-config` | ConfigMap (env) | ✅ Yes | |
| `database-secret` | Secret | ✅ Yes* | *Kustomize Hash requires secretGenerator |
| `tarsy-secrets` | Secret | ✅ Yes* | *Kustomize Hash requires secretGenerator |
| `oauth2-proxy-secret` | Secret | ✅ Yes* | *Kustomize Hash requires secretGenerator |
| `builtin_config.py` | Code in image | ❌ No | Requires image rebuild (expected) |

**Important Note for Kustomize Hash**: Current setup uses `oc process` to create secrets from templates. Kustomize Hash approach would require switching to `secretGenerator` in kustomization.yaml.

---

## Pre-Implementation Improvements

Before selecting and implementing a config reload solution, the following improvements should be made:

### 1. Enable Built-in Configuration Override in agents.yaml

**Current State:**
- Built-in MCP servers, agents, and chains cannot be overridden
- If you define the same server_id/agent/chain in both `builtin_config.py` and `agents.yaml`, behavior is undefined
- Kubernetes MCP server uses `${KUBECONFIG}` which works locally but not in pods
- No way to customize built-in MCP server configuration for Kubernetes deployments

**Target State:**
- `agents.yaml` can override built-in MCP servers, agents, and chains by ID
- Mount kubeconfig content as Secret volume in pod
- Override built-in `kubernetes-server` to use mounted kubeconfig path
- Consistent override pattern for all configuration types

**Implementation Details:**

#### Code Changes:

**Step 1: Implement Configuration Merging**

File: `backend/tarsy/config/agent_config.py`

Update `ConfigurationLoader` to merge configured items over built-in items:

```python
def _merge_mcp_servers(self, builtin_servers, configured_servers):
    """
    Merge configured MCP servers over built-in servers.
    Configured servers with same server_id override built-in servers.
    """
    merged = builtin_servers.copy()
    for server_id, config in configured_servers.items():
        if server_id in merged:
            logger.info(f"Overriding built-in MCP server: {server_id}")
        merged[server_id] = config
    return merged

def _merge_agents(self, builtin_agents, configured_agents):
    """
    Merge configured agents over built-in agents.
    Configured agents with same class name override built-in agents.
    """
    merged = builtin_agents.copy()
    for agent_name, config in configured_agents.items():
        if agent_name in merged:
            logger.info(f"Overriding built-in agent: {agent_name}")
        merged[agent_name] = config
    return merged

def _merge_chains(self, builtin_chains, configured_chains):
    """
    Merge configured chains over built-in chains.
    Configured chains with same chain_id override built-in chains.
    """
    merged = builtin_chains.copy()
    for chain_id, config in configured_chains.items():
        if chain_id in merged:
            logger.info(f"Overriding built-in chain: {chain_id}")
        merged[chain_id] = config
    return merged
```

Apply merging in `ConfigurationLoader.load_configuration()`.

#### Deployment Changes:

**Step 2: Create Kubeconfig Secret**

Add to `deploy/secrets-template.yaml`:

```yaml
- apiVersion: v1
  kind: Secret
  metadata:
    name: mcp-kubeconfig-secret
    namespace: ${NAMESPACE}
    labels:
      app: tarsy
      component: mcp
  type: Opaque
  stringData:
    config: ${MCP_KUBECONFIG_CONTENT}
```

**Step 3: Mount Kubeconfig in Backend Deployment**

File: `deploy/kustomize/base/backend-deployment.yaml`

Add volume mount and environment variable:

```yaml
containers:
  - name: backend
    env:
      # ... existing env vars ...
      - name: MCP_KUBECONFIG
        value: /app/.kube/mcp-config
    volumeMounts:
      # ... existing volume mounts ...
      - name: mcp-kubeconfig
        mountPath: /app/.kube/mcp-config
        subPath: config
volumes:
  # ... existing volumes ...
  - name: mcp-kubeconfig
    secret:
      secretName: mcp-kubeconfig-secret
```

**Step 4: Override Built-in Kubernetes Server**

File: `config/agents.yaml`

Add override configuration:

```yaml
mcp_servers:
  kubernetes-server:  # Same server_id as built-in - will override
    server_id: kubernetes-server
    server_type: kubernetes
    enabled: true
    transport:
      type: stdio
      command: npx
      args:
        - "-y"
        - "kubernetes-mcp-server@latest"
        - "--read-only"
        - "--disable-destructive"
        - "--kubeconfig"
        - "${MCP_KUBECONFIG}"  # Uses mounted secret path
    instructions: |
      For Kubernetes operations:
      - Be careful with cluster-scoped resource listings in large clusters
      - Always prefer namespaced queries when possible
      - Use kubectl explain for resource schema information
      - Check resource quotas before creating new resources
    data_masking:
      enabled: true
      pattern_groups:
        - kubernetes
      patterns:
        - certificate
        - token
        - email
```

**Step 5: Update Secret Creation**

File: `make/openshift.mk`

Update `openshift-create-secrets` target to include `MCP_KUBECONFIG_CONTENT`:

```makefile
openshift-create-secrets: openshift-check openshift-create-namespace
	# ... existing validation ...
	@if [ -z "$$MCP_KUBECONFIG_CONTENT" ]; then \
		echo -e "$(YELLOW)⚠️  Warning: MCP_KUBECONFIG_CONTENT not set - kubernetes-server will not work$(NC)"; \
	fi
	oc process -f deploy/secrets-template.yaml \
		# ... existing parameters ...
		-p MCP_KUBECONFIG_CONTENT="$$MCP_KUBECONFIG_CONTENT" | \
		oc apply -f -
```

**Step 6: Update Environment Template**

File: `deploy/openshift.env.template`

Add MCP kubeconfig section:

```bash
# =============================================================================
# MCP Server Configuration
# =============================================================================
# Kubeconfig content for Kubernetes MCP server (base64 encoded or raw YAML)
# export MCP_KUBECONFIG_CONTENT := "$(cat ~/.kube/config)"
```

**Benefits:**
- Consistent override pattern for all configuration types (MCP servers, agents, chains)
- Works with existing Secret volume mount pattern
- No changes to transport layer or MCP initialization
- Discoverable configuration in `agents.yaml`
- Template variable resolution already supported

---

## Solutions

### Option 1: Stakater Reloader

Kubernetes controller that watches ConfigMaps and Secrets, automatically triggering rolling restarts when they change.

**Documentation**: [Stakater Reloader GitHub](https://github.com/stakater/Reloader)

**Installation**: Requires installing Reloader controller (via Helm, kubectl, or ArgoCD). See documentation for installation methods.

#### Configuration

Add annotations to `deploy/kustomize/base/backend-deployment.yaml`:

```yaml
metadata:
  annotations:
    # Option A: Auto-watch all ConfigMaps/Secrets mounted in this deployment
    reloader.stakater.com/auto: "true"
    
    # Option B: Watch specific ConfigMaps (comma-separated)
    # configmap.reloader.stakater.com/reload: "agents-config,llm-providers-config,tarsy-config"
    
    # Option C: Watch specific Secrets
    # secret.reloader.stakater.com/reload: "tarsy-secrets,database-secret"
```

#### How It Works

1. ConfigMap/Secret changes in GitHub
2. ArgoCD syncs the change to Kubernetes
3. Reloader detects the change
4. Reloader triggers a rolling restart by updating pod template annotation
5. Kubernetes performs graceful rolling update
6. New pods start with updated configuration

#### Pros
- ✅ Clean, declarative approach
- ✅ Zero code changes in application
- ✅ Works with any ConfigMap/Secret
- ✅ Graceful rolling restarts (no downtime)
- ✅ Popular, well-maintained project (4k+ GitHub stars)
- ✅ Supports annotations for fine-grained control

#### Cons
- ❌ Requires installing additional controller
- ❌ Cluster-wide permissions needed

---

### Option 2: Kustomize ConfigMap Hash Generator

Kustomize automatically appends a hash to ConfigMap/Secret names and updates all references, forcing pod recreation when content changes.

#### Configuration

Update `deploy/kustomize/overlays/development/kustomization.yaml`:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: tarsy-dev

resources:
  - ../../base

namePrefix: dev-

# Enable hash suffix for ConfigMaps (forces pod restart on change)
generatorOptions:
  disableNameSuffixHash: false  # Default: false (hash enabled)

configMapGenerator:
  - name: agents-config
    behavior: create
    files:
      - agents.yaml
  - name: llm-providers-config
    behavior: create
    files:
      - llm_providers.yaml
  # ... other configMaps
```

#### How It Works

1. ConfigMap content changes in GitHub
2. ArgoCD runs kustomize build
3. Kustomize generates new hash (e.g., `agents-config-abc123` → `agents-config-def456`)
4. Kustomize updates Deployment to reference new ConfigMap name
5. Kubernetes sees Deployment spec change → triggers rolling restart
6. Old ConfigMap remains until pods are replaced (safe rollback)

#### Pros
- ✅ No additional controllers needed
- ✅ Built into Kustomize
- ✅ Safe rollbacks (old ConfigMap still exists)
- ✅ Explicit, deterministic behavior

#### Cons
- ❌ ConfigMap names change in cluster (harder to debug)
- ❌ Only works with configMapGenerator/secretGenerator
- ❌ Requires kustomize configuration
- ❌ Can't use with pre-existing ConfigMaps

---

### Option 3: ArgoCD Resource Hooks (PostSync Job)

ArgoCD runs Kubernetes Jobs at specific sync phases to trigger deployment restarts.

#### Implementation

Create `deploy/kustomize/base/hooks/restart-backend-hook.yaml`:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: restart-backend
  namespace: tarsy
  annotations:
    argocd.argoproj.io/hook: PostSync
    argocd.argoproj.io/hook-delete-policy: HookSucceeded
spec:
  template:
    spec:
      serviceAccountName: argocd-hook-sa
      containers:
        - name: kubectl
          image: bitnami/kubectl:latest
          command:
            - /bin/sh
            - -c
            - |
              echo "Rolling restart backend deployment..."
              kubectl rollout restart deployment/tarsy-backend -n tarsy
              kubectl rollout status deployment/tarsy-backend -n tarsy
      restartPolicy: OnFailure
  backoffLimit: 2
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: argocd-hook-sa
  namespace: tarsy
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: argocd-hook-role
  namespace: tarsy
rules:
  - apiGroups: ["apps"]
    resources: ["deployments"]
    verbs: ["get", "patch"]
  - apiGroups: ["apps"]
    resources: ["deployments/status"]
    verbs: ["get"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: argocd-hook-binding
  namespace: tarsy
subjects:
  - kind: ServiceAccount
    name: argocd-hook-sa
    namespace: tarsy
roleRef:
  kind: Role
  name: argocd-hook-role
  apiGroup: rbac.authorization.k8s.io
```

Update `deploy/kustomize/base/kustomization.yaml`:

```yaml
resources:
  - hooks/restart-backend-hook.yaml
```

#### How It Works

1. Any resource changes in ArgoCD app
2. ArgoCD syncs all resources
3. After sync completes, PostSync hooks run
4. Job executes `kubectl rollout restart`
5. Deployment performs rolling restart
6. Job is auto-deleted on success

#### Pros
- ✅ Full control over restart logic
- ✅ Can add conditions (only restart if ConfigMap changed)
- ✅ Can run multiple commands
- ✅ No additional controllers

#### Cons
- ❌ Restarts on **any** sync (even if ConfigMap didn't change)
- ❌ More complex RBAC setup
- ❌ Requires Job cleanup
- ❌ Not specific to ConfigMap changes

---

## Comparison Matrix

| Feature | Reloader | Kustomize Hash | ArgoCD Hook |
|---------|----------|----------------|-------------|
| **Auto-restart on ConfigMap change** | ✅ Yes | ✅ Yes | ⚠️ Yes (always, even when config unchanged) |
| **No additional controller needed** | ❌ No | ✅ Yes | ✅ Yes |
| **Graceful rolling restart** | ✅ Yes | ✅ Yes | ✅ Yes |
| **Config-specific (only restarts when config changes)** | ✅ Yes | ✅ Yes | ❌ No (restarts on any sync) |
| **Easy debugging** | ✅ Yes | ⚠️ Harder (names change) | ✅ Yes |
| **GitOps-friendly** | ✅ Yes | ✅ Yes | ✅ Yes |
| **Production-ready** | ✅ Yes | ✅ Yes | ⚠️ Complex RBAC |
| **Safe rollbacks** | ✅ Good | ✅ Excellent (immutable) | ✅ Good |

---

## References

- [Stakater Reloader](https://github.com/stakater/Reloader)
- [Kustomize ConfigMap Generator](https://kubectl.docs.kubernetes.io/references/kustomize/kustomization/configmapgenerator/)
- [ArgoCD Resource Hooks](https://argo-cd.readthedocs.io/en/stable/user-guide/resource_hooks/)

