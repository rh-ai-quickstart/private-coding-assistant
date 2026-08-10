DEV_USER ?=
DEV_NAMESPACE ?= $(if $(DEV_USER),$(DEV_USER)-devspaces,)
AI_NAMESPACE ?= private-assistant-ai-serving
MODEL_NAME ?= qwen3-coder
N_LIST ?= 16
PYTEST_ARGS ?=

VENV := .venv
PYTHON := $(VENV)/bin/python
PYTEST := $(VENV)/bin/pytest

.PHONY: e2e performance venv help

help: ## Show e2e help
	@echo "Usage:"
	@echo "  make e2e DEV_USER=<user> [PYTEST_ARGS='...']"
	@echo "  make performance N_LIST=1,2,4 [AI_NAMESPACE=...] [MODEL_NAME=...]  # OpenCode ladder"
	@echo "Example:"
	@echo "  make e2e DEV_USER=dev-user1"
	@echo "  make e2e DEV_USER=dev-user1 PYTEST_ARGS='-k opencode_calculator'"
	@echo "  make performance  # default N_LIST=16"
	@echo "  make performance N_LIST=1,2,4"
	@echo "  make performance MODEL_NAME=my-model"

venv: $(PYTHON)

$(PYTHON): pyproject.toml uv.lock
	@command -v uv >/dev/null || { echo "ERROR: uv not found in PATH"; exit 1; }
	uv sync --frozen

e2e: venv ## Run cluster e2e tests (requires oc login + Running OpenCode workspace)
	@command -v oc >/dev/null || { echo "ERROR: oc not found in PATH"; exit 1; }
	@test -n "$(DEV_NAMESPACE)" || { echo "ERROR: set DEV_USER= (e.g. DEV_USER=dev-user1)"; exit 1; }
	DEV_NAMESPACE=$(DEV_NAMESPACE) \
		$(PYTEST) -v --tb=short --ignore=fixtures --ignore=performance $(PYTEST_ARGS)

performance: venv ## OpenCode scalability ladder; default N_LIST=16
	@command -v oc >/dev/null || { echo "ERROR: oc not found in PATH"; exit 1; }
	@test -n "$(N_LIST)" || { echo "ERROR: set N_LIST= (e.g. N_LIST=16)"; exit 1; }
	AI_NAMESPACE=$(AI_NAMESPACE) MODEL_NAME=$(MODEL_NAME) N_LIST=$(N_LIST) \
		$(PYTEST) performance -v --tb=short $(PYTEST_ARGS)
