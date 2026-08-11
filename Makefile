-include .env

IMAGE_NAME ?= pca-provisioner
CONTAINER_NAME ?= pca
CONTAINERFILE ?= Containerfile.provisioner
PROJECT_DIR := $(shell pwd)

AI_NAMESPACE ?= private-assistant-ai-serving
HF_TOKEN ?= $(HUGGINGFACE_TOKEN)
MCP_ENABLED ?= false
CHARTS_DIR := charts
SCRIPTS_DIR := PCA_Deployment_ROSA/scripts
DEPLOY_VALUES_DIR := deploy_existing_openshift

# MCP flags — gateway CRDs (mcp.kuadrant.io) are not yet widely available; always disable gateway.
MCP_FLAGS := $(if $(filter true,$(MCP_ENABLED)),\
	--set mcp.enabled=true \
	--set pca-mcp.gateway.enabled=false \
	--set pca-mcp.namespace=$(AI_NAMESPACE),)

ENV_FILE_FLAG := $(if $(wildcard .env),--env-file .env,)
AWS_MOUNT := $(if $(wildcard $(HOME)/.aws),-v $(HOME)/.aws:/home/pca/.aws:ro,)
AZURE_MOUNT := $(if $(wildcard $(HOME)/.azure),-v $(HOME)/.azure:/home/pca/.azure:ro,)
KUBE_MOUNT := $(if $(wildcard $(HOME)/.kube),-v $(HOME)/.kube:/home/pca/.kube:ro,)

RUN_FLAGS := --rm \
	--user 0:0 \
	--name $(CONTAINER_NAME) \
	-v $(PROJECT_DIR):/workspace:Z \
	$(AWS_MOUNT) \
	$(AZURE_MOUNT) \
	$(KUBE_MOUNT) \
	$(ENV_FILE_FLAG)

COMPONENT ?=
PYTEST_ARGS ?=
# N: DevSpace user count for devspace-deploy-existing-openshift (not used by smoke).
N ?=
# Performance ladder concurrency list (e.g. 1,2,4).
N_LIST ?= 16
# InferenceService / LLMInferenceService name for performance GPU sampling.
MODEL_NAME ?= qwen3-coder
# Smoke pytest-xdist workers (default 4).
N_PARALLEL ?= 4
DEV_USER ?=
TYPE ?= opencode
DEPLOY_SCRIPTS_DIR := $(DEPLOY_VALUES_DIR)/scripts
# Derived only for smoke tests (pytest still reads DEV_NAMESPACE).
DEV_NAMESPACE := $(if $(DEV_USER),$(DEV_USER)-devspaces,)

.PHONY: build shell run help smoke e2e performance performance-vllm unit ai-serving-deploy-existing-openshift ai-serving-undeploy-existing-openshift devspace-deploy-existing-openshift devspace-undeploy-existing-openshift setup-idp mcp-enable mcp-disable

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-42s\033[0m %s\n", $$1, $$2}'

build: ## Build the provisioner container image
	podman build -t $(IMAGE_NAME) -f $(CONTAINERFILE) .

shell: ## Start an interactive shell inside the container
	podman run -it $(RUN_FLAGS) $(IMAGE_NAME)

run: ## Run a one-shot command (usage: make run CMD="terraform plan")
	podman run $(RUN_FLAGS) $(IMAGE_NAME) $(CMD)

ai-serving-deploy-existing-openshift: ## Deploy AI serving on existing OpenShift (AI_NAMESPACE=, HF_TOKEN=, MCP_ENABLED=false)
	@if [ -z "$(HF_TOKEN)" ]; then echo "ERROR: HF_TOKEN is required. Set in .env or pass HF_TOKEN=hf_xxx"; exit 1; fi
	helm dependency update $(CHARTS_DIR)/pca-platform-config
	helm dependency update $(CHARTS_DIR)/pca-ai-serving/charts/pca-observability
	helm dependency update $(CHARTS_DIR)/pca-ai-serving
	helm upgrade --install $(AI_NAMESPACE)-platform-config $(CHARTS_DIR)/pca-platform-config \
		--namespace $(AI_NAMESPACE) --create-namespace \
		-f $(DEPLOY_VALUES_DIR)/values-platform-config.yaml \
		--set namespace=$(AI_NAMESPACE) \
		--set pca-guardrails.namespace=$(AI_NAMESPACE) \
		--set hfToken.raw=$(HF_TOKEN) \
		$(MCP_FLAGS)
	helm upgrade --install $(AI_NAMESPACE)-ai-serving $(CHARTS_DIR)/pca-ai-serving \
		--namespace $(AI_NAMESPACE) \
		-f $(DEPLOY_VALUES_DIR)/values-ai-serving.yaml \
		--set namespace=$(AI_NAMESPACE) \
		--set pca-observability.namespace=$(AI_NAMESPACE) \
		$(HELM_ARGS)

# Default: helm uninstall only — keeps AI_NAMESPACE + model-cache PVC (warm restart path).
# Full wipe (cold start next deploy): DELETE_NAMESPACE=1
ai-serving-undeploy-existing-openshift: ## Remove AI serving Helm releases; keep ns/PVC unless DELETE_NAMESPACE=1
	helm uninstall $(AI_NAMESPACE)-ai-serving --namespace $(AI_NAMESPACE) --ignore-not-found || true
	helm uninstall $(AI_NAMESPACE)-platform-config --namespace $(AI_NAMESPACE) --ignore-not-found || true
	@if [ "$(DELETE_NAMESPACE)" = "1" ]; then \
		oc delete namespace $(AI_NAMESPACE) --ignore-not-found; \
	else \
		echo "Kept namespace $(AI_NAMESPACE) and model-cache PVC (warm path). Full wipe: make ai-serving-undeploy-existing-openshift DELETE_NAMESPACE=1"; \
	fi

devspace-deploy-existing-openshift: ## Deploy DevSpaces: N=<count> (dev-user1..N) or DEV_USER=<username> (ns = <user>-devspaces)
	@N="$(N)" DEV_USER="$(DEV_USER)" \
		AI_NAMESPACE="$(AI_NAMESPACE)" TYPE="$(TYPE)" MCP_ENABLED="$(MCP_ENABLED)" \
		HELM_ARGS="$(HELM_ARGS)" CHARTS_DIR="$(CHARTS_DIR)" DEPLOY_VALUES_DIR="$(DEPLOY_VALUES_DIR)" \
		$(DEPLOY_SCRIPTS_DIR)/devspace-deploy.sh

devspace-undeploy-existing-openshift: ## Remove a DevSpace (DEV_USER= required → <user>-devspaces)
	@if [ -z "$(DEV_USER)" ]; then echo "ERROR: Pass DEV_USER=<username>"; exit 1; fi; \
	ns="$(DEV_USER)-devspaces"; \
	helm uninstall $$ns-devspaces --namespace $$ns --ignore-not-found || true

setup-idp: ## Configure HTPasswd IDP on existing cluster (reads users from values)
	$(SCRIPTS_DIR)/setup-idp.sh $(DEPLOY_VALUES_DIR)/values-platform-config.yaml

mcp-enable: ## Enable MCP on stack (AI_NAMESPACE=, optional DEV_USER= for that DevSpace release)
	helm upgrade $(AI_NAMESPACE)-platform-config $(CHARTS_DIR)/pca-platform-config \
		--namespace $(AI_NAMESPACE) --reuse-values \
		--set mcp.enabled=true \
		--set pca-mcp.gateway.enabled=false \
		--set pca-mcp.namespace=$(AI_NAMESPACE)
	@if [ -n "$(DEV_USER)" ]; then \
		ns="$(DEV_USER)-devspaces"; \
		helm upgrade $$ns-devspaces $(CHARTS_DIR)/pca-devspaces \
			--namespace $$ns --reuse-values \
			--set mcp.enabled=true; \
	fi

mcp-disable: ## Disable MCP on stack (AI_NAMESPACE=, optional DEV_USER= for that DevSpace release)
	helm upgrade $(AI_NAMESPACE)-platform-config $(CHARTS_DIR)/pca-platform-config \
		--namespace $(AI_NAMESPACE) --reuse-values \
		--set mcp.enabled=false
	@if [ -n "$(DEV_USER)" ]; then \
		ns="$(DEV_USER)-devspaces"; \
		helm upgrade $$ns-devspaces $(CHARTS_DIR)/pca-devspaces \
			--namespace $$ns --reuse-values \
			--set mcp.enabled=false; \
	fi

smoke: ## Cluster smoke tests (AI_NAMESPACE=, DEV_USER=, COMPONENT=, N_PARALLEL= xdist workers)
	$(MAKE) -C tests/cluster-smoke smoke \
		AI_NAMESPACE=$(AI_NAMESPACE) DEV_NAMESPACE=$(DEV_NAMESPACE) \
		COMPONENT=$(COMPONENT) N_PARALLEL=$(N_PARALLEL) PYTEST_ARGS='$(PYTEST_ARGS)'

unit: ## Local unit tests (PYTEST_ARGS=)
	python -m pytest tests/unit -v $(PYTEST_ARGS)

e2e: ## Cluster e2e tests (DEV_USER= required; PYTEST_ARGS=)
	@if [ -z "$(DEV_USER)" ] && [ -z "$(DEV_NAMESPACE)" ]; then \
		echo "ERROR: Pass DEV_USER=<username> (or DEV_NAMESPACE=)"; exit 1; \
	fi
	$(MAKE) -C tests/e2e e2e \
		DEV_USER=$(DEV_USER) DEV_NAMESPACE=$(DEV_NAMESPACE) PYTEST_ARGS='$(PYTEST_ARGS)'

# Do not run alongside make performance-vllm — shared vLLM/GPU.
performance: ## OpenCode scalability ladder (N_LIST=1,2,4,8 16; AI_NAMESPACE=; MODEL_NAME=; needs pre-deployed OpenCode users) default 16
	$(MAKE) -C tests/e2e performance \
		AI_NAMESPACE=$(AI_NAMESPACE) MODEL_NAME=$(MODEL_NAME) N_LIST=$(N_LIST) PYTEST_ARGS='$(PYTEST_ARGS)'

# Do not run alongside make performance — shared vLLM/GPU.
# GuideLLM Job → vLLM predictor HTTP (concurrent streams + throughput probe).
performance-vllm: ## GuideLLM capacity sweep on live vLLM (AI_NAMESPACE=; HELM_ARGS=)
	@command -v oc >/dev/null || { echo "ERROR: oc not found in PATH"; exit 1; }
	@command -v helm >/dev/null || { echo "ERROR: helm not found in PATH"; exit 1; }
	@echo "NOTE: Do not run make performance in parallel — shared vLLM/GPU."
	oc delete job guidellm-capacity -n $(AI_NAMESPACE) --ignore-not-found
	oc delete job guidellm-sweep-h100 -n $(AI_NAMESPACE) --ignore-not-found
	helm upgrade --install $(AI_NAMESPACE)-benchmarks $(CHARTS_DIR)/pca-benchmarks \
		--namespace $(AI_NAMESPACE) \
		-f $(DEPLOY_VALUES_DIR)/values-benchmarks.yaml \
		--set namespace=$(AI_NAMESPACE) \
		--set enabled=true \
		$(HELM_ARGS)
	@echo "Started Job guidellm-capacity in $(AI_NAMESPACE) (stateless — results in Job logs)."
	@echo "Follow logs:  oc logs -n $(AI_NAMESPACE) -f job/guidellm-capacity"
