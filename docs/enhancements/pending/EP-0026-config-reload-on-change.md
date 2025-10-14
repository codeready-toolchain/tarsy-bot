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

Before selecting and implementing a config reload solution, additional improvements may be identified here.

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

