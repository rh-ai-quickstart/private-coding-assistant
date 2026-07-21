AI_NAMESPACE ?= private-assistant-ai-serving
DEV_NAMESPACE ?=
COMPONENT ?=
PYTEST_ARGS ?=
N ?= 4

VENV := .venv
PYTHON := $(VENV)/bin/python
PYTEST := $(VENV)/bin/pytest

# Map COMPONENT= to a pytest marker (-m). Empty COMPONENT runs the full suite.
MARKER_ARGS := $(if $(COMPONENT),-m $(COMPONENT),)

.PHONY: smoke venv help

help: ## Show smoke-test help
	@echo "Usage:"
	@echo "  make smoke AI_NAMESPACE=<ns> [DEV_NAMESPACE=<ns>] [COMPONENT=<marker>] [N=4] [PYTEST_ARGS='...']"
	@echo ""
	@echo "Markers: readiness vllm grafana langfuse otel devspaces guardrails ai_gateway"
	@echo "Parallelism: N=4 by default (pytest-xdist). Use N=1 for serial."
	@echo "Example: make smoke COMPONENT=vllm AI_NAMESPACE=ai-serving"

venv: $(PYTHON)

$(PYTHON): pyproject.toml
	python3 -m venv $(VENV)
	$(PYTHON) -m pip install -q -U pip
	$(PYTHON) -m pip install -q -e .

smoke: venv ## Run cluster smoke tests (requires oc login)
	@command -v oc >/dev/null || { echo "ERROR: oc not found in PATH"; exit 1; }
	AI_NAMESPACE=$(AI_NAMESPACE) DEV_NAMESPACE=$(DEV_NAMESPACE) \
		$(PYTEST) -v --tb=short -n $(N) $(MARKER_ARGS) $(PYTEST_ARGS)
