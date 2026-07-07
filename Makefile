-include .env

IMAGE_NAME ?= pca-provisioner
CONTAINER_NAME ?= pca
CONTAINERFILE ?= Containerfile.provisioner
PROJECT_DIR := $(shell pwd)

NAMESPACE ?= private-assistant-ai-serving
AI_NAMESPACE ?= $(NAMESPACE)
HF_TOKEN ?= $(HUGGINGFACE_TOKEN)
CHARTS_DIR := PCA_Deployment_ROSA/charts
SCRIPTS_DIR := PCA_Deployment_ROSA/scripts
DEPLOY_VALUES_DIR := deploy_existing_openshift

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

.PHONY: build shell run help ai-serving-deploy-existing-openshift ai-serving-undeploy-existing-openshift devspace-deploy-existing-openshift devspace-undeploy-existing-openshift setup-idp

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-42s\033[0m %s\n", $$1, $$2}'

build: ## Build the provisioner container image
	podman build -t $(IMAGE_NAME) -f $(CONTAINERFILE) .

shell: ## Start an interactive shell inside the container
	podman run -it $(RUN_FLAGS) $(IMAGE_NAME)

run: ## Run a one-shot command (usage: make run CMD="terraform plan")
	podman run $(RUN_FLAGS) $(IMAGE_NAME) $(CMD)

ai-serving-deploy-existing-openshift: ## Deploy AI serving on existing OpenShift (NAMESPACE=, HF_TOKEN=)
	@if [ -z "$(HF_TOKEN)" ]; then echo "ERROR: HF_TOKEN is required. Set in .env or pass HF_TOKEN=hf_xxx"; exit 1; fi
	helm upgrade --install $(NAMESPACE)-platform-config $(CHARTS_DIR)/pca-platform-config \
		--namespace $(NAMESPACE) --create-namespace \
		-f $(DEPLOY_VALUES_DIR)/values-platform-config.yaml \
		--set namespace=$(NAMESPACE) \
		--set hfToken.raw=$(HF_TOKEN)
	helm upgrade --install $(NAMESPACE)-ai-serving $(CHARTS_DIR)/pca-ai-serving \
		--namespace $(NAMESPACE) \
		-f $(DEPLOY_VALUES_DIR)/values-ai-serving.yaml \
		--set namespace=$(NAMESPACE)

ai-serving-undeploy-existing-openshift: ## Remove AI serving from OpenShift (NAMESPACE=)
	helm uninstall $(NAMESPACE)-ai-serving --namespace $(NAMESPACE) --ignore-not-found || true
	helm uninstall $(NAMESPACE)-platform-config --namespace $(NAMESPACE) --ignore-not-found || true
	oc delete namespace $(NAMESPACE) --ignore-not-found

devspace-deploy-existing-openshift: ## Deploy a devspace (NAMESPACE=, AI_NAMESPACE=)
	helm upgrade --install $(NAMESPACE)-devspaces $(CHARTS_DIR)/pca-devspaces \
		--namespace $(NAMESPACE) --create-namespace \
		-f $(DEPLOY_VALUES_DIR)/values-devspaces.yaml \
		--set aiServingNamespace=$(AI_NAMESPACE)

devspace-undeploy-existing-openshift: ## Remove a devspace (NAMESPACE=)
	helm uninstall $(NAMESPACE)-devspaces --namespace $(NAMESPACE) --ignore-not-found || true

setup-idp: ## Configure HTPasswd IDP on existing cluster (reads users from values)
	$(SCRIPTS_DIR)/setup-idp.sh $(DEPLOY_VALUES_DIR)/values-platform-config.yaml
