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

# Container management (reuse existing)
PODMAN_COMPOSE := COMPOSE_PROJECT_NAME=tarsy podman-compose -f podman-compose.yml

# Prerequisites for OpenShift workflow
.PHONY: openshift-check
openshift-check: ## Check OpenShift login and registry access
	@echo "$(BLUE)Checking OpenShift prerequisites...$(NC)"
	@if ! command -v oc >/dev/null 2>&1; then \
		echo "$(RED)❌ Error: oc (OpenShift CLI) not found$(NC)"; \
		echo "$(YELLOW)Please install the OpenShift CLI: https://docs.openshift.com/container-platform/latest/cli_reference/openshift_cli/getting-started-cli.html$(NC)"; \
		exit 1; \
	fi
	@if ! oc whoami >/dev/null 2>&1; then \
		echo "$(RED)❌ Error: Not logged into OpenShift$(NC)"; \
		echo "$(YELLOW)Please log in with: oc login$(NC)"; \
		exit 1; \
	fi
	@if [ "$(OPENSHIFT_REGISTRY)" = "registry.not.found" ]; then \
		echo "$(RED)❌ Error: OpenShift internal registry not exposed$(NC)"; \
		echo "$(YELLOW)Please expose the registry with:$(NC)"; \
		echo "$(YELLOW)  oc patch configs.imageregistry.operator.openshift.io/cluster --patch '{\"spec\":{\"defaultRoute\":true}}' --type=merge$(NC)"; \
		exit 1; \
	fi
	@echo "$(GREEN)✓ OpenShift CLI available$(NC)"
	@echo "$(GREEN)✓ Logged in as: $(shell oc whoami)$(NC)"  
	@echo "$(GREEN)✓ Registry available at: $(OPENSHIFT_REGISTRY)$(NC)"

.PHONY: openshift-login-registry
openshift-login-registry: openshift-check ## Login podman to OpenShift internal registry
	@echo "$(BLUE)Logging podman into OpenShift registry...$(NC)"
	@podman login -u $(shell oc whoami) -p $(shell oc whoami -t) $(OPENSHIFT_REGISTRY)
	@echo "$(GREEN)✅ Podman logged into OpenShift registry$(NC)"

.PHONY: openshift-create-namespace
openshift-create-namespace: openshift-check ## Create development namespace if it doesn't exist
	@echo "$(BLUE)Ensuring namespace $(OPENSHIFT_NAMESPACE) exists...$(NC)"
	@oc get namespace $(OPENSHIFT_NAMESPACE) >/dev/null 2>&1 || oc create namespace $(OPENSHIFT_NAMESPACE)
	@echo "$(GREEN)✅ Namespace $(OPENSHIFT_NAMESPACE) ready$(NC)"

# Build targets (reuse existing build logic)
.PHONY: openshift-build-backend
openshift-build-backend: sync-backend-deps openshift-login-registry ## Build backend image locally
	@echo "$(GREEN)Building backend image locally...$(NC)"
	$(PODMAN_COMPOSE) build backend
	@echo "$(GREEN)✅ Backend image built$(NC)"

.PHONY: openshift-build-dashboard  
openshift-build-dashboard: openshift-login-registry ## Build dashboard image locally
	@echo "$(GREEN)Building dashboard image locally...$(NC)"
	$(PODMAN_COMPOSE) build dashboard
	@echo "$(GREEN)✅ Dashboard image built$(NC)"

.PHONY: openshift-build-all
openshift-build-all: openshift-build-backend openshift-build-dashboard ## Build all images locally
	@echo "$(GREEN)✅ All images built$(NC)"

# Push targets
.PHONY: openshift-push-backend
openshift-push-backend: openshift-build-backend openshift-create-namespace ## Push backend image to OpenShift registry
	@echo "$(GREEN)Pushing backend image to OpenShift registry...$(NC)"
	@podman tag localhost/tarsy-backend:latest $(BACKEND_IMAGE):$(IMAGE_TAG)
	@podman push $(BACKEND_IMAGE):$(IMAGE_TAG)
	@echo "$(GREEN)✅ Backend image pushed: $(BACKEND_IMAGE):$(IMAGE_TAG)$(NC)"

.PHONY: openshift-push-dashboard
openshift-push-dashboard: openshift-build-dashboard openshift-create-namespace ## Push dashboard image to OpenShift registry  
	@echo "$(GREEN)Pushing dashboard image to OpenShift registry...$(NC)"
	@podman tag localhost/tarsy-dashboard:latest $(DASHBOARD_IMAGE):$(IMAGE_TAG)
	@podman push $(DASHBOARD_IMAGE):$(IMAGE_TAG)
	@echo "$(GREEN)✅ Dashboard image pushed: $(DASHBOARD_IMAGE):$(IMAGE_TAG)$(NC)"

.PHONY: openshift-push-all
openshift-push-all: openshift-push-backend openshift-push-dashboard ## Build and push all images to OpenShift registry
	@echo "$(GREEN)✅ All images built and pushed to OpenShift registry$(NC)"

# Secret management
.PHONY: openshift-create-secrets
openshift-create-secrets: openshift-check openshift-create-namespace ## Create secrets from environment variables
	@echo "$(GREEN)Creating secrets from environment variables...$(NC)"
	@if [ -z "$$GOOGLE_API_KEY" ]; then \
		echo "$(RED)❌ Error: GOOGLE_API_KEY environment variable not set$(NC)"; \
		echo "$(YELLOW)Please set: export GOOGLE_API_KEY=your-actual-google-api-key$(NC)"; \
		exit 1; \
	fi
	@if [ -z "$$GITHUB_TOKEN" ]; then \
		echo "$(RED)❌ Error: GITHUB_TOKEN environment variable not set$(NC)"; \
		echo "$(YELLOW)Please set: export GITHUB_TOKEN=your-github-token$(NC)"; \
		exit 1; \
	fi
	@oc process -f deploy/secrets-template.yaml \
		-p NAMESPACE=$(OPENSHIFT_NAMESPACE) \
		-p GOOGLE_API_KEY="$$GOOGLE_API_KEY" \
		-p GITHUB_TOKEN="$$GITHUB_TOKEN" \
		-p OPENAI_API_KEY="$$OPENAI_API_KEY" \
		-p ANTHROPIC_API_KEY="$$ANTHROPIC_API_KEY" \
		-p XAI_API_KEY="$$XAI_API_KEY" \
		-p OAUTH2_CLIENT_ID="$$OAUTH2_CLIENT_ID" \
		-p OAUTH2_CLIENT_SECRET="$$OAUTH2_CLIENT_SECRET" | \
		oc apply -f -
	@echo "$(GREEN)✅ Secrets created in namespace: $(OPENSHIFT_NAMESPACE)$(NC)"

.PHONY: openshift-check-config-files
openshift-check-config-files: ## Check that required config files exist in deploy location
	@echo "$(BLUE)Checking deployment configuration files...$(NC)"
	@mkdir -p deploy/kustomize/base/config
	@if [ ! -f deploy/kustomize/base/config/agents.yaml ]; then \
		if [ -f config/agents.yaml ]; then \
			echo "$(YELLOW)📋 Copying agents.yaml to deployment location...$(NC)"; \
			cp config/agents.yaml deploy/kustomize/base/config/; \
		elif [ -f config/agents.yaml.example ]; then \
			echo "$(YELLOW)📋 Creating agents.yaml from example in deployment location...$(NC)"; \
			cp config/agents.yaml.example deploy/kustomize/base/config/agents.yaml; \
			echo "$(YELLOW)📝 Please customize deploy/kustomize/base/config/agents.yaml for your needs$(NC)"; \
		else \
			echo "$(RED)❌ Error: No agents.yaml or agents.yaml.example found$(NC)"; \
			exit 1; \
		fi; \
	fi
	@if [ ! -f deploy/kustomize/base/config/llm_providers.yaml ]; then \
		if [ -f config/llm_providers.yaml ]; then \
			echo "$(YELLOW)📋 Copying llm_providers.yaml to deployment location...$(NC)"; \
			cp config/llm_providers.yaml deploy/kustomize/base/config/; \
		elif [ -f config/llm_providers.yaml.example ]; then \
			echo "$(YELLOW)📋 Creating llm_providers.yaml from example in deployment location...$(NC)"; \
			cp config/llm_providers.yaml.example deploy/kustomize/base/config/llm_providers.yaml; \
			echo "$(YELLOW)📝 Please customize deploy/kustomize/base/config/llm_providers.yaml for your needs$(NC)"; \
		else \
			echo "$(RED)❌ Error: No llm_providers.yaml or llm_providers.yaml.example found$(NC)"; \
			exit 1; \
		fi; \
	fi
	@if [ ! -f deploy/kustomize/base/config/oauth2-proxy-container.cfg ]; then \
		if [ -f config/oauth2-proxy-container.cfg ]; then \
			echo "$(YELLOW)📋 Copying oauth2-proxy-container.cfg to deployment location...$(NC)"; \
			cp config/oauth2-proxy-container.cfg deploy/kustomize/base/config/; \
		elif [ -f config/oauth2-proxy-container.cfg.example ]; then \
			echo "$(YELLOW)📋 Creating oauth2-proxy-container.cfg from example in deployment location...$(NC)"; \
			cp config/oauth2-proxy-container.cfg.example deploy/kustomize/base/config/oauth2-proxy-container.cfg; \
			echo "$(YELLOW)📝 Please customize deploy/kustomize/base/config/oauth2-proxy-container.cfg for your needs$(NC)"; \
		else \
			echo "$(RED)❌ Error: No oauth2-proxy-container.cfg or oauth2-proxy-container.cfg.example found$(NC)"; \
			exit 1; \
		fi; \
	fi
	@echo "$(BLUE)Syncing config files to overlay directory...$(NC)"
	@cp deploy/kustomize/base/config/agents.yaml overlays/development/
	@cp deploy/kustomize/base/config/llm_providers.yaml overlays/development/
	@cp deploy/kustomize/base/config/oauth2-proxy-container.cfg overlays/development/
	@echo "$(GREEN)✅ Deployment configuration files ready$(NC)"

# Deploy targets
.PHONY: openshift-deploy
openshift-deploy: openshift-create-secrets openshift-push-all openshift-check-config-files ## Complete deployment: secrets, images, and manifests
	@echo "$(GREEN)Deploying application to OpenShift...$(NC)"
	@oc apply -k overlays/development/
	@echo "$(GREEN)✅ Deployed to OpenShift namespace: $(OPENSHIFT_NAMESPACE)$(NC)"
	@echo "$(BLUE)Check status with: make openshift-status$(NC)"

.PHONY: openshift-deploy-only
openshift-deploy-only: openshift-check openshift-check-config-files ## Deploy manifests only (assumes secrets and images exist)
	@echo "$(GREEN)Deploying manifests to OpenShift...$(NC)"
	@oc apply -k overlays/development/
	@echo "$(GREEN)✅ Manifests deployed to OpenShift namespace: $(OPENSHIFT_NAMESPACE)$(NC)"

# Status and info targets  
.PHONY: openshift-status
openshift-status: openshift-check ## Show OpenShift deployment status
	@echo "$(GREEN)OpenShift Deployment Status$(NC)"
	@echo "=============================="
	@echo "$(BLUE)Namespace: $(OPENSHIFT_NAMESPACE)$(NC)"
	@echo ""
	@echo "$(YELLOW)Pods:$(NC)"
	@oc get pods -n $(OPENSHIFT_NAMESPACE) 2>/dev/null || echo "No pods found"
	@echo ""
	@echo "$(YELLOW)Services:$(NC)"  
	@oc get services -n $(OPENSHIFT_NAMESPACE) 2>/dev/null || echo "No services found"
	@echo ""
	@echo "$(YELLOW)Routes:$(NC)"
	@oc get routes -n $(OPENSHIFT_NAMESPACE) 2>/dev/null || echo "No routes found"
	@echo ""
	@echo "$(YELLOW)ImageStreams:$(NC)"
	@oc get imagestreams -n $(OPENSHIFT_NAMESPACE) 2>/dev/null || echo "No imagestreams found"

.PHONY: openshift-logs
openshift-logs: openshift-check ## Show logs from backend pod
	@echo "$(GREEN)Backend logs:$(NC)"
	@oc logs -l component=backend -n $(OPENSHIFT_NAMESPACE) --tail=50 2>/dev/null || echo "No backend pods found"

.PHONY: openshift-logs-dashboard
openshift-logs-dashboard: openshift-check ## Show logs from dashboard pod
	@echo "$(GREEN)Dashboard logs:$(NC)"
	@oc logs -l component=dashboard -n $(OPENSHIFT_NAMESPACE) --tail=50 2>/dev/null || echo "No dashboard pods found"

.PHONY: openshift-urls
openshift-urls: openshift-check ## Show OpenShift application URLs
	@echo "$(GREEN)OpenShift Application URLs$(NC)"
	@echo "============================="
	@DASHBOARD_URL=$$(oc get route dev-tarsy-dashboard -n $(OPENSHIFT_NAMESPACE) -o jsonpath='{.spec.host}' 2>/dev/null); \
	if [ -n "$$DASHBOARD_URL" ]; then \
		echo "$(BLUE)🌍 Dashboard: https://$$DASHBOARD_URL$(NC)"; \
		echo "$(BLUE)🔧 API: https://$$DASHBOARD_URL/api$(NC)"; \
		echo "$(BLUE)🔐 OAuth: https://$$DASHBOARD_URL/oauth2$(NC)"; \
		echo "$(BLUE)🔌 WebSocket: https://$$DASHBOARD_URL/ws$(NC)"; \
	else \
		echo "$(RED)No routes found in namespace $(OPENSHIFT_NAMESPACE)$(NC)"; \
	fi

# Cleanup targets
.PHONY: openshift-clean
openshift-clean: openshift-check ## Delete all resources from OpenShift
	@echo "$(YELLOW)⚠️  This will delete all Tarsy resources from OpenShift!$(NC)"
	@printf "Are you sure? [y/N] "; \
	read REPLY; \
	case "$$REPLY" in \
		[Yy]|[Yy][Ee][Ss]) \
			echo "$(YELLOW)Deleting OpenShift resources...$(NC)"; \
			oc delete -k deploy/kustomize/overlays/development/ 2>/dev/null || true; \
			echo "$(GREEN)✅ OpenShift resources deleted$(NC)"; \
			;; \
		*) \
			echo "$(GREEN)Cancelled$(NC)"; \
			;; \
	esac

.PHONY: openshift-clean-images
openshift-clean-images: openshift-check ## Delete images from OpenShift registry
	@echo "$(YELLOW)⚠️  This will delete Tarsy images from OpenShift registry!$(NC)"
	@printf "Are you sure? [y/N] "; \
	read REPLY; \
	case "$$REPLY" in \
		[Yy]|[Yy][Ee][Ss]) \
			echo "$(YELLOW)Deleting images from ImageStreams...$(NC)"; \
			oc delete imagestream tarsy-backend -n $(OPENSHIFT_NAMESPACE) 2>/dev/null || true; \
			oc delete imagestream tarsy-dashboard -n $(OPENSHIFT_NAMESPACE) 2>/dev/null || true; \
			echo "$(GREEN)✅ Images deleted from registry$(NC)"; \
			;; \
		*) \
			echo "$(GREEN)Cancelled$(NC)"; \
			;; \
	esac

# Development workflow targets
.PHONY: openshift-dev
openshift-dev: openshift-deploy openshift-urls ## Complete dev workflow: secrets, build, push, deploy, and show URLs
	@echo "$(GREEN)🚀 OpenShift development deployment complete!$(NC)"
	@echo "$(YELLOW)💡 Tips:$(NC)"
	@echo "  - Check status: make openshift-status"
	@echo "  - View logs: make openshift-logs"  
	@echo "  - Redeploy: make openshift-redeploy"
	@echo "  - Update config: edit config/*.yaml then make openshift-redeploy"

.PHONY: openshift-redeploy
openshift-redeploy: openshift-push-all openshift-deploy-only ## Quick redeploy: rebuild images and update deployment
	@echo "$(GREEN)✅ Quick redeploy completed$(NC)"

.PHONY: openshift-quick
openshift-quick: openshift-deploy-only openshift-urls ## Quick deploy manifests only (no image rebuild)
	@echo "$(GREEN)✅ Quick manifest deployment completed$(NC)"
