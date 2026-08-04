DEV_USER ?=
DEV_NAMESPACE ?= $(if $(DEV_USER),$(DEV_USER)-devspaces,)
PYTEST_ARGS ?=

VENV := .venv
PYTHON := $(VENV)/bin/python
PYTEST := $(VENV)/bin/pytest

.PHONY: e2e venv help

help: ## Show e2e help
	@echo "Usage:"
	@echo "  make e2e DEV_USER=<user> [PYTEST_ARGS='...']"
	@echo "Example:"
	@echo "  make e2e DEV_USER=dev-user1"
	@echo "  make e2e DEV_USER=dev-user1 PYTEST_ARGS='-k opencode_calculator'"

venv: $(PYTHON)

$(PYTHON): pyproject.toml
	@command -v uv >/dev/null || { echo "ERROR: uv not found in PATH"; exit 1; }
	uv venv $(VENV)
	uv pip install -p $(PYTHON) -e .

e2e: venv ## Run cluster e2e tests (requires oc login + Running OpenCode workspace)
	@command -v oc >/dev/null || { echo "ERROR: oc not found in PATH"; exit 1; }
	@test -n "$(DEV_NAMESPACE)" || { echo "ERROR: set DEV_USER= (e.g. DEV_USER=dev-user1)"; exit 1; }
	DEV_NAMESPACE=$(DEV_NAMESPACE) \
		$(PYTEST) -v --tb=short --ignore=fixtures $(PYTEST_ARGS)
