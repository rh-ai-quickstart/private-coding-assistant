DEV_USER ?=
DEV_NAMESPACE ?= $(if $(DEV_USER),$(DEV_USER)-devspaces,)
PYTEST_ARGS ?=

E2E_DIR := ../e2e
VENV := $(E2E_DIR)/.venv
PYTEST := $(VENV)/bin/pytest

.PHONY: uat venv help

help: ## Show UAT help
	@echo "Usage:"
	@echo "  make uat DEV_USER=<user> [PYTEST_ARGS='...']"
	@echo "Example:"
	@echo "  make uat DEV_USER=dev-user1"

venv:
	$(MAKE) -C $(E2E_DIR) venv

uat: venv ## Run cluster UAT (requires oc login + Running OpenCode workspace)
	@command -v oc >/dev/null || { echo "ERROR: oc not found in PATH"; exit 1; }
	@test -n "$(DEV_NAMESPACE)" || { echo "ERROR: set DEV_USER= (e.g. DEV_USER=dev-user1)"; exit 1; }
	DEV_NAMESPACE=$(DEV_NAMESPACE) \
		$(PYTEST) -v --tb=short --ignore=fixtures $(PYTEST_ARGS)
