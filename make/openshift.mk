# Tarsy - OpenShift Development Makefile
# ======================================

# Colors for output
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
BLUE := \033[0;34m
NC := \033[0m # No Color

# OpenShift variables
OPENSHIFT_NAMESPACE := tarsy-dev
OPENSHIFT_REGISTRY := $(shell oc get route default-route -n openshift-image-registry --template='{{ .spec.host }}' 2>/dev/null || echo "registry.not.found")
BACKEND_IMAGE := $(OPENSHIFT_REGISTRY)/$(OPENSHIFT_NAMESPACE)/tarsy-backend
DASHBOARD_IMAGE := $(OPENSHIFT_REGISTRY)/$(OPENSHIFT_NAMESPACE)/tarsy-dashboard
IMAGE_TAG := dev

# Push tool selection
# Set USE_SKOPEO=true to use skopeo instead of podman for pushing images
USE_SKOPEO ?=

# Container management (reuse existing)
PODMAN_COMPOSE := COMPOSE_PROJECT_NAME=tarsy podman compose -f deploy/podman-compose.yml

# Auto-detect OpenShift cluster domain
CLUSTER_DOMAIN := $(shell oc get ingresses.config.openshift.io cluster -o jsonpath='{.spec.domain}' 2>/dev/null)

# Auto-load deploy/openshift.env ONLY when running OpenShift targets
# Check if any OpenShift target is in the command line goals
OPENSHIFT_TARGETS := openshift-check openshift-login-registry openshift-create-namespace \
                     openshift-build-backend openshift-build-dashboard openshift-build-all \
                     openshift-push-backend openshift-push-dashboard openshift-push-all \
                     openshift-create-secrets openshift-check-config-files \
                     openshift-apply openshift-deploy \
                     openshift-redeploy openshift-status \
                     openshift-urls openshift-logs openshift-logs-dashboard \
                     openshift-clean openshift-clean-images

ifneq ($(filter $(OPENSHIFT_TARGETS),$(MAKECMDGOALS)),)
	# Auto-detect ROUTE_HOST
	ifneq ($(CLUSTER_DOMAIN),)
		ROUTE_HOST := $(OPENSHIFT_NAMESPACE).$(CLUSTER_DOMAIN)
	endif
    -include deploy/openshift.env
    ifndef ROUTE_HOST
		$(error ROUTE_HOST is not defined. Please define ROUTE_HOST in deploy/openshift.env)
	else ifeq ($(ROUTE_HOST),localhost:8080)
		$(error ROUTE_HOST is not defined or auto-detected. Please fix your cluster context or define ROUTE_HOST in deploy/openshift.env)
	endif
endif

# Prerequisites for OpenShift workflow
.PHONY: openshift-check
openshift-check: ## Check OpenShift login and registry access
	@echo -e "$(BLUE)Checking OpenShift prerequisites...$(NC)"
	@if ! command -v oc >/dev/null 2>&1; then \
		echo -e "$(RED)❌ Error: oc (OpenShift CLI) not found$(NC)"; \
		echo -e "$(YELLOW)Please install the OpenShift CLI: https://docs.openshift.com/container-platform/latest/cli_reference/openshift_cli/getting-started-cli.html$(NC)"; \
		exit 1; \
	fi
	@if ! oc whoami >/dev/null 2>&1; then \
		echo -e "$(RED)❌ Error: Not logged into OpenShift$(NC)"; \
		echo -e "$(YELLOW)Please log in with: oc login$(NC)"; \
		exit 1; \
	fi
	@if [ "$(OPENSHIFT_REGISTRY)" = "registry.not.found" ]; then \
		echo -e "$(RED)❌ Error: OpenShift internal registry not exposed$(NC)"; \
		echo -e "$(YELLOW)Please expose the registry with:$(NC)"; \
		echo -e "$(YELLOW)  oc patch configs.imageregistry.operator.openshift.io/cluster --patch '{\"spec\":{\"defaultRoute\":true}}' --type=merge$(NC)"; \
		exit 1; \
	fi
	@echo -e "$(GREEN)✓ OpenShift CLI available$(NC)"
	@echo -e "$(GREEN)✓ Logged in as: $(shell oc whoami)$(NC)"  
	@echo -e "$(GREEN)✓ Registry available at: $(OPENSHIFT_REGISTRY)$(NC)"

.PHONY: openshift-login-registry
openshift-login-registry: openshift-check ## Login podman to OpenShift internal registry
	@echo -e "$(BLUE)Logging podman into OpenShift registry...$(NC)"
	@# Note: --tls-verify=false is used for development environments with self-signed certs
	@podman login --tls-verify=false -u $(shell oc whoami) -p $(shell oc whoami -t) $(OPENSHIFT_REGISTRY)
	@echo -e "$(GREEN)✅ Podman logged into OpenShift registry$(NC)"

.PHONY: openshift-create-namespace
openshift-create-namespace: openshift-check ## Create development namespace if it doesn't exist
	@echo -e "$(BLUE)Ensuring namespace $(OPENSHIFT_NAMESPACE) exists...$(NC)"
	@oc get namespace $(OPENSHIFT_NAMESPACE) >/dev/null 2>&1 || oc create namespace $(OPENSHIFT_NAMESPACE)
	@echo -e "$(GREEN)✅ Namespace $(OPENSHIFT_NAMESPACE) ready$(NC)"

# Build targets (use plain podman build for OpenShift, independent of compose)
.PHONY: openshift-build-backend
openshift-build-backend: sync-backend-deps openshift-login-registry ## Build backend image locally
	@echo -e "$(GREEN)Building backend image for OpenShift...$(NC)"
	@podman build -t localhost/tarsy_backend:latest -f backend/Dockerfile backend/
	@echo -e "$(GREEN)✅ Backend image built$(NC)"

.PHONY: openshift-build-dashboard  
openshift-build-dashboard: openshift-login-registry ## Build dashboard image locally
	@echo -e "$(GREEN)Building dashboard image for OpenShift...$(NC)"
	@if [ -f deploy/openshift.env ] && grep -q "^export ROUTE_HOST" deploy/openshift.env 2>/dev/null; then \
		echo -e "$(YELLOW)Using manually configured Route Host: $(ROUTE_HOST)$(NC)"; \
	else \
		echo -e "$(YELLOW)Using auto-detected Route Host: $(ROUTE_HOST)$(NC)"; \
	fi
	@podman build -t localhost/tarsy_dashboard:latest \
		--build-arg VITE_API_BASE_URL="" \
		--build-arg VITE_WS_BASE_URL="wss://$(ROUTE_HOST)" \
		-f dashboard/Dockerfile dashboard/
	@echo -e "$(GREEN)✅ Dashboard image built with OpenShift URLs$(NC)"

.PHONY: openshift-build-all
openshift-build-all: openshift-build-backend openshift-build-dashboard ## Build all images locally
	@echo -e "$(GREEN)✅ All images built$(NC)"

# Push targets
.PHONY: openshift-push-backend
openshift-push-backend: openshift-build-backend openshift-create-namespace ## Push backend image to OpenShift registry
	@echo -e "$(GREEN)Pushing backend image to OpenShift registry...$(NC)"
	@podman tag localhost/tarsy_backend:latest $(BACKEND_IMAGE):$(IMAGE_TAG)
	@if [ -n "$(USE_SKOPEO)" ]; then \
		echo -e "$(BLUE)Using skopeo to push image...$(NC)"; \
		echo -e "$(BLUE)Saving image to archive...$(NC)"; \
		podman save localhost/tarsy_backend:latest -o /tmp/tarsy_backend.tar; \
		echo -e "$(BLUE)Pushing from archive to registry...$(NC)"; \
		skopeo copy --dest-tls-verify=false docker-archive:/tmp/tarsy_backend.tar docker://$(BACKEND_IMAGE):$(IMAGE_TAG); \
		rm -f /tmp/tarsy_backend.tar; \
		echo -e "$(BLUE)Archive cleaned up$(NC)"; \
	else \
		podman push --tls-verify=false $(BACKEND_IMAGE):$(IMAGE_TAG); \
	fi
	@echo -e "$(GREEN)✅ Backend image pushed: $(BACKEND_IMAGE):$(IMAGE_TAG)$(NC)"

.PHONY: openshift-push-dashboard
openshift-push-dashboard: openshift-build-dashboard openshift-create-namespace ## Push dashboard image to OpenShift registry  
	@echo -e "$(GREEN)Pushing dashboard image to OpenShift registry...$(NC)"
	@podman tag localhost/tarsy_dashboard:latest $(DASHBOARD_IMAGE):$(IMAGE_TAG)
	@if [ -n "$(USE_SKOPEO)" ]; then \
		echo -e "$(BLUE)Using skopeo to push image...$(NC)"; \
		echo -e "$(BLUE)Saving image to archive...$(NC)"; \
		podman save localhost/tarsy_dashboard:latest -o /tmp/tarsy_dashboard.tar; \
		echo -e "$(BLUE)Pushing from archive to registry...$(NC)"; \
		skopeo copy --dest-tls-verify=false docker-archive:/tmp/tarsy_dashboard.tar docker://$(DASHBOARD_IMAGE):$(IMAGE_TAG); \
		rm -f /tmp/tarsy_dashboard.tar; \
		echo -e "$(BLUE)Archive cleaned up$(NC)"; \
	else \
		podman push --tls-verify=false $(DASHBOARD_IMAGE):$(IMAGE_TAG); \
	fi
	@echo -e "$(GREEN)✅ Dashboard image pushed: $(DASHBOARD_IMAGE):$(IMAGE_TAG)$(NC)"

.PHONY: openshift-push-all
openshift-push-all: openshift-push-backend openshift-push-dashboard ## Build and push all images to OpenShift registry
	@echo -e "$(GREEN)✅ All images built and pushed to OpenShift registry$(NC)"

# Secret management
.PHONY: openshift-create-secrets
openshift-create-secrets: openshift-check openshift-create-namespace ## Create secrets from environment variables
	@echo -e "$(GREEN)Creating secrets from environment variables...$(NC)"
	@if [ -z "$$GOOGLE_API_KEY" ]; then \
		echo -e "$(RED)❌ Error: GOOGLE_API_KEY environment variable not set$(NC)"; \
		echo -e "$(YELLOW)Please set: export GOOGLE_API_KEY=your-actual-google-api-key$(NC)"; \
		exit 1; \
	fi
	@if [ -z "$$GITHUB_TOKEN" ]; then \
		echo -e "$(RED)❌ Error: GITHUB_TOKEN environment variable not set$(NC)"; \
		echo -e "$(YELLOW)Please set: export GITHUB_TOKEN=your-github-token$(NC)"; \
		exit 1; \
	fi
	@if [ -z "$$MCP_KUBECONFIG_CONTENT" ]; then \
		echo -e "$(YELLOW)⚠️  Warning: MCP_KUBECONFIG_CONTENT not set - kubernetes-server may not work in cluster$(NC)"; \
	fi
	@if [ -z "$$JWT_PUBLIC_KEY_CONTENT" ]; then \
		echo -e "$(YELLOW)⚠️  Warning: JWT_PUBLIC_KEY_CONTENT not set - JWT authentication will not work$(NC)"; \
	fi
	# Set defaults for database connection if not provided
	# Note: Users can override these by exporting DATABASE_* variables in deploy/openshift.env
	# Example: export DATABASE_USER := my-custom-user
	@export DATABASE_USER=$${DATABASE_USER:-tarsy}; \
	export DATABASE_NAME=$${DATABASE_NAME:-tarsy}; \
	export DATABASE_HOST=$${DATABASE_HOST:-dev-tarsy-database}; \
	export DATABASE_PORT=$${DATABASE_PORT:-5432}; \
	PROCESS_CMD="oc process -f deploy/secrets-template.yaml \
		-p NAMESPACE=$(OPENSHIFT_NAMESPACE) \
		-p GOOGLE_API_KEY=\"$$GOOGLE_API_KEY\" \
		-p GITHUB_TOKEN=\"$$GITHUB_TOKEN\" \
		-p DATABASE_USER=\"$$DATABASE_USER\" \
		-p DATABASE_NAME=\"$$DATABASE_NAME\" \
		-p DATABASE_HOST=\"$$DATABASE_HOST\" \
		-p DATABASE_PORT=\"$$DATABASE_PORT\" \
		-p MCP_KUBECONFIG_CONTENT=\"$$MCP_KUBECONFIG_CONTENT\" \
		-p JWT_PUBLIC_KEY_CONTENT=\"$$JWT_PUBLIC_KEY_CONTENT\" \
		-p OPENAI_API_KEY=\"$$OPENAI_API_KEY\" \
		-p ANTHROPIC_API_KEY=\"$$ANTHROPIC_API_KEY\" \
		-p XAI_API_KEY=\"$$XAI_API_KEY\" \
		-p VERTEX_AI_PROJECT=\"$$VERTEX_AI_PROJECT\" \
		-p GOOGLE_SERVICE_ACCOUNT_KEY=\"$$GOOGLE_SERVICE_ACCOUNT_KEY\" \
		-p OAUTH2_CLIENT_ID=\"$$OAUTH2_CLIENT_ID\" \
		-p OAUTH2_CLIENT_SECRET=\"$$OAUTH2_CLIENT_SECRET\""; \
	if [ -n "$$DATABASE_PASSWORD" ]; then \
		echo -e "$(BLUE)Using provided DATABASE_PASSWORD$(NC)"; \
		PROCESS_CMD="$$PROCESS_CMD -p DATABASE_PASSWORD=\"$$DATABASE_PASSWORD\""; \
	else \
		echo -e "$(BLUE)Auto-generating DATABASE_PASSWORD$(NC)"; \
	fi; \
	if [ -n "$$OAUTH2_COOKIE_SECRET" ]; then \
		echo -e "$(BLUE)Using provided OAUTH2_COOKIE_SECRET$(NC)"; \
		PROCESS_CMD="$$PROCESS_CMD -p OAUTH2_COOKIE_SECRET=\"$$OAUTH2_COOKIE_SECRET\""; \
	else \
		echo -e "$(BLUE)Auto-generating OAUTH2_COOKIE_SECRET$(NC)"; \
	fi; \
	eval "$$PROCESS_CMD" | oc apply -f -
	@echo -e "$(GREEN)✅ Secrets created in namespace: $(OPENSHIFT_NAMESPACE)$(NC)"

.PHONY: openshift-check-config-files
openshift-check-config-files: ## Check that required config files exist in deploy location
	@echo -e "$(BLUE)Checking deployment configuration files...$(NC)"
	@mkdir -p deploy/kustomize/base/config
	@if [ ! -f deploy/kustomize/base/config/agents.yaml ]; then \
		if [ -f config/agents.yaml ]; then \
			echo -e "$(YELLOW)📋 Copying agents.yaml to deployment location...$(NC)"; \
			cp config/agents.yaml deploy/kustomize/base/config/; \
		elif [ -f config/agents.yaml.example ]; then \
			echo -e "$(YELLOW)📋 Creating agents.yaml from example in deployment location...$(NC)"; \
			cp config/agents.yaml.example deploy/kustomize/base/config/agents.yaml; \
			echo -e "$(YELLOW)📝 Please customize deploy/kustomize/base/config/agents.yaml for your needs$(NC)"; \
		else \
			echo -e "$(RED)❌ Error: No agents.yaml or agents.yaml.example found$(NC)"; \
			exit 1; \
		fi; \
	fi
	@if [ ! -f deploy/kustomize/base/config/llm_providers.yaml ]; then \
		if [ -f config/llm_providers.yaml ]; then \
			echo -e "$(YELLOW)📋 Copying llm_providers.yaml to deployment location...$(NC)"; \
			cp config/llm_providers.yaml deploy/kustomize/base/config/; \
		elif [ -f config/llm_providers.yaml.example ]; then \
			echo -e "$(YELLOW)📋 Creating llm_providers.yaml from example in deployment location...$(NC)"; \
			cp config/llm_providers.yaml.example deploy/kustomize/base/config/llm_providers.yaml; \
			echo -e "$(YELLOW)📝 Please customize deploy/kustomize/base/config/llm_providers.yaml for your needs$(NC)"; \
		else \
			echo -e "$(RED)❌ Error: No llm_providers.yaml or llm_providers.yaml.example found$(NC)"; \
			exit 1; \
		fi; \
	fi
	@if [ -f config/oauth2-proxy-container.cfg ]; then \
		echo -e "$(YELLOW)📋 Copying oauth2-proxy-container.cfg to deployment location...$(NC)"; \
		cp config/oauth2-proxy-container.cfg deploy/kustomize/base/config/; \
	elif [ -f config/oauth2-proxy-container.cfg.example ]; then \
		echo -e "$(YELLOW)📋 Creating oauth2-proxy-container.cfg from example in deployment location...$(NC)"; \
		cp config/oauth2-proxy-container.cfg.example deploy/kustomize/base/config/oauth2-proxy-container.cfg; \
		echo -e "$(YELLOW)📝 Please customize deploy/kustomize/base/config/oauth2-proxy-container.cfg for your needs$(NC)"; \
	else \
		echo -e "$(RED)❌ Error: No oauth2-proxy-container.cfg or oauth2-proxy-container.cfg.example found$(NC)"; \
		exit 1; \
	fi
	@echo -e "$(BLUE)Syncing config files to overlay directory...$(NC)"
	@mkdir -p deploy/kustomize/overlays/development/templates
	@cp deploy/kustomize/base/config/agents.yaml deploy/kustomize/overlays/development/
	@cp deploy/kustomize/base/config/llm_providers.yaml deploy/kustomize/overlays/development/
	@cp deploy/kustomize/base/config/oauth2-proxy-container.cfg deploy/kustomize/overlays/development/
	@if [ -d config/templates ]; then \
		cp -r config/templates/* deploy/kustomize/overlays/development/templates/; \
	else \
		echo -e "$(RED)❌ Error: No config/templates directory found$(NC)"; \
		exit 1; \
	fi
	@echo -e "$(BLUE)Replacing placeholders in oauth2-proxy config...$(NC)"
	@sed -i.bak 's|{{ROUTE_HOST}}|$(ROUTE_HOST)|g' deploy/kustomize/overlays/development/oauth2-proxy-container.cfg
	@if [ -n "$(GITHUB_ORG)" ]; then \
		echo "  Setting GitHub org restriction: $(GITHUB_ORG)"; \
		sed -i.bak 's|{{GITHUB_ORG_CONFIG}}|github_org = "$(GITHUB_ORG)"|g' deploy/kustomize/overlays/development/oauth2-proxy-container.cfg; \
	else \
		echo "  No GitHub org restriction (allowing all authenticated users)"; \
		sed -i.bak 's|{{GITHUB_ORG_CONFIG}}|# github_org = "your-github-org"  # Not set - allowing all authenticated users|g' deploy/kustomize/overlays/development/oauth2-proxy-container.cfg; \
	fi
	@if [ -n "$(GITHUB_TEAM)" ]; then \
		echo "  Setting GitHub team restriction: $(GITHUB_TEAM)"; \
		sed -i.bak 's|{{GITHUB_TEAM_CONFIG}}|github_team = "$(GITHUB_TEAM)"|g' deploy/kustomize/overlays/development/oauth2-proxy-container.cfg; \
	else \
		echo "  No GitHub team restriction"; \
		sed -i.bak 's|{{GITHUB_TEAM_CONFIG}}|# github_team = "your-team"  # Not set|g' deploy/kustomize/overlays/development/oauth2-proxy-container.cfg; \
	fi
	@rm -f deploy/kustomize/overlays/development/oauth2-proxy-container.cfg.bak
	@echo -e "$(GREEN)✅ Deployment configuration files ready$(NC)"

# Deploy targets
.PHONY: openshift-deploy
openshift-deploy: openshift-create-secrets openshift-push-all openshift-check-config-files ## Complete deployment: secrets, images, and manifests
	@echo -e "$(GREEN)Deploying application to OpenShift...$(NC)"
	@if [ -f deploy/openshift.env ] && grep -q "^export ROUTE_HOST" deploy/openshift.env 2>/dev/null; then \
		echo -e "$(BLUE)Using manually configured Route Host: $(ROUTE_HOST)$(NC)"; \
	else \
		echo -e "$(BLUE)Using auto-detected Route Host: $(ROUTE_HOST)$(NC)"; \
	fi
	@echo -e "$(BLUE)Replacing {{ROUTE_HOST}} with $(ROUTE_HOST)...$(NC)"
	@sed -i.bak 's|{{ROUTE_HOST}}|$(ROUTE_HOST)|g' deploy/kustomize/base/routes.yaml
	@oc apply -k deploy/kustomize/overlays/development/
	@mv deploy/kustomize/base/routes.yaml.bak deploy/kustomize/base/routes.yaml
	@echo -e "$(GREEN)✅ Deployed to OpenShift namespace: $(OPENSHIFT_NAMESPACE)$(NC)"
	@echo -e "$(BLUE)Check status with: make openshift-status$(NC)"

.PHONY: openshift-apply
openshift-apply: openshift-check openshift-check-config-files ## Apply manifests only (assumes secrets and images exist)
	@echo -e "$(GREEN)Applying manifests to OpenShift...$(NC)"
	@if [ -f deploy/openshift.env ] && grep -q "^export ROUTE_HOST" deploy/openshift.env 2>/dev/null; then \
		echo -e "$(BLUE)Using manually configured Route Host: $(ROUTE_HOST)$(NC)"; \
	else \
		echo -e "$(BLUE)Using auto-detected Route Host: $(ROUTE_HOST)$(NC)"; \
	fi
	@echo -e "$(BLUE)Replacing {{ROUTE_HOST}} with $(ROUTE_HOST)...$(NC)"
	@sed -i.bak 's|{{ROUTE_HOST}}|$(ROUTE_HOST)|g' deploy/kustomize/base/routes.yaml
	@oc apply -k deploy/kustomize/overlays/development/
	@mv deploy/kustomize/base/routes.yaml.bak deploy/kustomize/base/routes.yaml
	@echo -e "$(GREEN)✅ Manifests applied to OpenShift namespace: $(OPENSHIFT_NAMESPACE)$(NC)"

# Status and info targets  
.PHONY: openshift-status
openshift-status: openshift-check ## Show OpenShift deployment status
	@echo -e "$(GREEN)OpenShift Deployment Status$(NC)"
	@echo "=============================="
	@echo -e "$(BLUE)Namespace: $(OPENSHIFT_NAMESPACE)$(NC)"
	@echo ""
	@echo -e "$(YELLOW)Pods:$(NC)"
	@oc get pods -n $(OPENSHIFT_NAMESPACE) 2>/dev/null || echo "No pods found"
	@echo ""
	@echo -e "$(YELLOW)Services:$(NC)"  
	@oc get services -n $(OPENSHIFT_NAMESPACE) 2>/dev/null || echo "No services found"
	@echo ""
	@echo -e "$(YELLOW)Routes:$(NC)"
	@oc get routes -n $(OPENSHIFT_NAMESPACE) 2>/dev/null || echo "No routes found"
	@echo ""
	@echo -e "$(YELLOW)ImageStreams:$(NC)"
	@oc get imagestreams -n $(OPENSHIFT_NAMESPACE) 2>/dev/null || echo "No imagestreams found"

.PHONY: openshift-logs
openshift-logs: openshift-check ## Show logs from backend pod
	@echo -e "$(GREEN)Backend logs:$(NC)"
	@oc logs -l component=backend -n $(OPENSHIFT_NAMESPACE) --tail=50 2>/dev/null || echo "No backend pods found"

.PHONY: openshift-logs-dashboard
openshift-logs-dashboard: openshift-check ## Show logs from dashboard pod
	@echo -e "$(GREEN)Dashboard logs:$(NC)"
	@oc logs -l component=dashboard -n $(OPENSHIFT_NAMESPACE) --tail=50 2>/dev/null || echo "No dashboard pods found"

.PHONY: openshift-urls
openshift-urls: openshift-check ## Show OpenShift application URLs
	@echo -e "$(GREEN)OpenShift Application URLs$(NC)"
	@echo "============================="
	@DASHBOARD_URL=$$(oc get route dev-tarsy-dashboard -n $(OPENSHIFT_NAMESPACE) -o jsonpath='{.spec.host}' 2>/dev/null); \
	if [ -n "$$DASHBOARD_URL" ]; then \
		echo -e "$(BLUE)🌍 Dashboard: https://$$DASHBOARD_URL$(NC)"; \
		echo -e "$(BLUE)🔧 API: https://$$DASHBOARD_URL/api$(NC)"; \
		echo -e "$(BLUE)🔐 OAuth: https://$$DASHBOARD_URL/oauth2$(NC)"; \
		echo -e "$(BLUE)🔌 WebSocket: https://$$DASHBOARD_URL/ws$(NC)"; \
	else \
		echo -e "$(RED)No routes found in namespace $(OPENSHIFT_NAMESPACE)$(NC)"; \
	fi

# Cleanup targets
.PHONY: openshift-clean
openshift-clean: openshift-check ## Delete all resources from OpenShift
	@echo -e "$(YELLOW)⚠️  This will delete all Tarsy resources from OpenShift!$(NC)"
	@printf "Are you sure? [y/N] "; \
	read REPLY; \
	case "$$REPLY" in \
		[Yy]|[Yy][Ee][Ss]) \
			echo -e "$(YELLOW)Deleting OpenShift resources...$(NC)"; \
			oc delete -k deploy/kustomize/overlays/development/ 2>/dev/null || true; \
			echo -e "$(GREEN)✅ OpenShift resources deleted$(NC)"; \
			;; \
		*) \
			echo -e "$(GREEN)Cancelled$(NC)"; \
			;; \
	esac

.PHONY: openshift-clean-images
openshift-clean-images: openshift-check ## Delete images from OpenShift registry
	@echo -e "$(YELLOW)⚠️  This will delete Tarsy images from OpenShift registry!$(NC)"
	@printf "Are you sure? [y/N] "; \
	read REPLY; \
	case "$$REPLY" in \
		[Yy]|[Yy][Ee][Ss]) \
			echo -e "$(YELLOW)Deleting images from ImageStreams...$(NC)"; \
			oc delete imagestream tarsy-backend -n $(OPENSHIFT_NAMESPACE) 2>/dev/null || true; \
			oc delete imagestream tarsy-dashboard -n $(OPENSHIFT_NAMESPACE) 2>/dev/null || true; \
			echo -e "$(GREEN)✅ Images deleted from registry$(NC)"; \
			;; \
		*) \
			echo -e "$(GREEN)Cancelled$(NC)"; \
			;; \
	esac

# Development workflow targets
.PHONY: openshift-redeploy
openshift-redeploy: openshift-push-all openshift-apply ## Rebuild images and update deployment
	@echo -e "$(GREEN)✅ Redeploy completed$(NC)"
