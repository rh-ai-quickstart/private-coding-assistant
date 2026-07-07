-include .env

IMAGE_NAME ?= pca-provisioner
CONTAINER_NAME ?= pca
CONTAINERFILE ?= Containerfile.provisioner
PROJECT_DIR := $(shell pwd)

NAMESPACE ?= private-assistant
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

.PHONY: build shell run help deploy undeploy deploy-devspaces undeploy-devspaces setup-idp

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

build: ## Build the provisioner container image
	podman build -t $(IMAGE_NAME) -f $(CONTAINERFILE) .

shell: ## Start an interactive shell inside the container
	podman run -it $(RUN_FLAGS) $(IMAGE_NAME)

run: ## Run a one-shot command (usage: make run CMD="terraform plan")
	podman run $(RUN_FLAGS) $(IMAGE_NAME) $(CMD)

deploy: ## Deploy AI serving stack on existing OpenShift (NAMESPACE=, HF_TOKEN=)
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

undeploy: ## Remove AI serving stack from OpenShift (NAMESPACE=)
	helm uninstall $(NAMESPACE)-ai-serving --namespace $(NAMESPACE) --ignore-not-found || true
	helm uninstall $(NAMESPACE)-platform-config --namespace $(NAMESPACE) --ignore-not-found || true
	oc delete namespace $(NAMESPACE) --ignore-not-found

deploy-devspaces: ## Deploy DevSpaces workspaces (NAMESPACE=)
	helm upgrade --install $(NAMESPACE)-devspaces $(CHARTS_DIR)/pca-devspaces \
		--namespace $(NAMESPACE) \
		-f $(DEPLOY_VALUES_DIR)/values-devspaces.yaml \
		--set aiServingNamespace=$(NAMESPACE)

undeploy-devspaces: ## Remove DevSpaces workspaces (NAMESPACE=)
	helm uninstall $(NAMESPACE)-devspaces --namespace $(NAMESPACE) --ignore-not-found || true

setup-idp: ## Configure HTPasswd IDP on existing cluster (reads users from values)
	$(SCRIPTS_DIR)/setup-idp.sh $(DEPLOY_VALUES_DIR)/values-platform-config.yaml
