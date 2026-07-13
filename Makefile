-include .env

IMAGE_NAME ?= pca-provisioner
CONTAINER_NAME ?= pca
CONTAINERFILE ?= Containerfile.provisioner
PROJECT_DIR := $(shell pwd)

AI_NAMESPACE ?= private-assistant-ai-serving
HF_TOKEN ?= $(HUGGINGFACE_TOKEN)
MCP_ENABLED ?= false
CHARTS_DIR := PCA_Deployment_ROSA/charts
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

.PHONY: build shell run help ai-serving-deploy-existing-openshift ai-serving-undeploy-existing-openshift devspace-deploy-existing-openshift devspace-undeploy-existing-openshift setup-idp mcp-enable mcp-disable

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
	helm upgrade --install $(AI_NAMESPACE)-platform-config $(CHARTS_DIR)/pca-platform-config \
		--namespace $(AI_NAMESPACE) --create-namespace \
		-f $(DEPLOY_VALUES_DIR)/values-platform-config.yaml \
		--set namespace=$(AI_NAMESPACE) \
		--set hfToken.raw=$(HF_TOKEN) \
		$(MCP_FLAGS)
	helm upgrade --install $(AI_NAMESPACE)-ai-serving $(CHARTS_DIR)/pca-ai-serving \
		--namespace $(AI_NAMESPACE) \
		-f $(DEPLOY_VALUES_DIR)/values-ai-serving.yaml \
		--set namespace=$(AI_NAMESPACE)

ai-serving-undeploy-existing-openshift: ## Remove AI serving from OpenShift (AI_NAMESPACE=)
	helm uninstall $(AI_NAMESPACE)-ai-serving --namespace $(AI_NAMESPACE) --ignore-not-found || true
	helm uninstall $(AI_NAMESPACE)-platform-config --namespace $(AI_NAMESPACE) --ignore-not-found || true
	oc delete namespace $(AI_NAMESPACE) --ignore-not-found

devspace-deploy-existing-openshift: ## Deploy a devspace (DEV_NAMESPACE=, AI_NAMESPACE=, MCP_ENABLED=false)
	@if [ -z "$(DEV_NAMESPACE)" ]; then echo "ERROR: DEV_NAMESPACE is required. Pass DEV_NAMESPACE=<name>"; exit 1; fi
	helm upgrade --install $(DEV_NAMESPACE)-devspaces $(CHARTS_DIR)/pca-devspaces \
		--namespace $(DEV_NAMESPACE) --create-namespace \
		-f $(DEPLOY_VALUES_DIR)/values-devspaces.yaml \
		--set aiServingNamespace=$(AI_NAMESPACE) \
		$(if $(filter true,$(MCP_ENABLED)),--set mcp.enabled=true,)

devspace-undeploy-existing-openshift: ## Remove a devspace (DEV_NAMESPACE=)
	@if [ -z "$(DEV_NAMESPACE)" ]; then echo "ERROR: DEV_NAMESPACE is required. Pass DEV_NAMESPACE=<name>"; exit 1; fi
	helm uninstall $(DEV_NAMESPACE)-devspaces --namespace $(DEV_NAMESPACE) --ignore-not-found || true

setup-idp: ## Configure HTPasswd IDP on existing cluster (reads users from values)
	$(SCRIPTS_DIR)/setup-idp.sh $(DEPLOY_VALUES_DIR)/values-platform-config.yaml

mcp-enable: ## Enable MCP server on an already-deployed stack (AI_NAMESPACE=, DEV_NAMESPACE=)
	helm upgrade $(AI_NAMESPACE)-platform-config $(CHARTS_DIR)/pca-platform-config \
		--namespace $(AI_NAMESPACE) --reuse-values \
		--set mcp.enabled=true \
		--set pca-mcp.gateway.enabled=false \
		--set pca-mcp.namespace=$(AI_NAMESPACE)
	@if [ -n "$(DEV_NAMESPACE)" ]; then \
		helm upgrade $(DEV_NAMESPACE)-devspaces $(CHARTS_DIR)/pca-devspaces \
			--namespace $(DEV_NAMESPACE) --reuse-values \
			--set mcp.enabled=true; \
	fi

mcp-disable: ## Disable MCP server on an already-deployed stack (AI_NAMESPACE=, DEV_NAMESPACE=)
	helm upgrade $(AI_NAMESPACE)-platform-config $(CHARTS_DIR)/pca-platform-config \
		--namespace $(AI_NAMESPACE) --reuse-values \
		--set mcp.enabled=false
	@if [ -n "$(DEV_NAMESPACE)" ]; then \
		helm upgrade $(DEV_NAMESPACE)-devspaces $(CHARTS_DIR)/pca-devspaces \
			--namespace $(DEV_NAMESPACE) --reuse-values \
			--set mcp.enabled=false; \
	fi
