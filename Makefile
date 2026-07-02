IMAGE_NAME ?= pca-provisioner
CONTAINER_NAME ?= pca
CONTAINERFILE ?= Containerfile.provisioner
PROJECT_DIR := $(shell pwd)

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

.PHONY: build shell run help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

build: ## Build the provisioner container image
	podman build -t $(IMAGE_NAME) -f $(CONTAINERFILE) .

shell: ## Start an interactive shell inside the container
	podman run -it $(RUN_FLAGS) $(IMAGE_NAME)

run: ## Run a one-shot command (usage: make run CMD="terraform plan")
	podman run $(RUN_FLAGS) $(IMAGE_NAME) $(CMD)
