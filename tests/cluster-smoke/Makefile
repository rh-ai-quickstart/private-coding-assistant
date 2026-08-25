AI_NAMESPACE ?= private-assistant-ai-serving
DEV_NAMESPACE ?=
COMPONENT ?=
PYTEST_ARGS ?=
N_PARALLEL ?= 4
PCA_MAAS_HOSTNAME ?=
PCA_MAAS_GATEWAY_CLASS ?=

VENV := .venv
PYTHON := $(VENV)/bin/python
PYTEST := $(VENV)/bin/pytest

# Map COMPONENT= to a pytest marker (-m). Empty COMPONENT runs the full suite.
MARKER_ARGS := $(if $(COMPONENT),-m $(COMPONENT),)

.PHONY: smoke venv help

help: ## Show smoke-test help
	@echo "Usage:"
	@echo "  make smoke AI_NAMESPACE=<ns> [DEV_USER=<user> → <user>-devspaces] [COMPONENT=<marker>] [N_PARALLEL=4] [PYTEST_ARGS='...']"
	@echo ""
	@echo "Markers: readiness vllm grafana langfuse otel devspaces guardrails ai_gateway"
	@echo "Parallelism: N_PARALLEL=4 by default (pytest-xdist). Use N_PARALLEL=1 for serial."
	@echo "Example: make smoke COMPONENT=vllm AI_NAMESPACE=ai-serving"

venv: $(PYTHON)

$(PYTHON): pyproject.toml
	python3 -m venv $(VENV)
	$(PYTHON) -m pip install -q -U pip
	$(PYTHON) -m pip install -q -e .

# Empty values must not be exported: os.environ.get("X", default) returns "" if X is set.
smoke: venv ## Run cluster smoke tests (requires oc login)
	@command -v oc >/dev/null || { echo "ERROR: oc not found in PATH"; exit 1; }
	AI_NAMESPACE=$(AI_NAMESPACE) DEV_NAMESPACE=$(DEV_NAMESPACE) \
		$(if $(PCA_MAAS_HOSTNAME),PCA_MAAS_HOSTNAME='$(PCA_MAAS_HOSTNAME)') \
		$(if $(PCA_MAAS_GATEWAY_CLASS),PCA_MAAS_GATEWAY_CLASS='$(PCA_MAAS_GATEWAY_CLASS)') \
		$(PYTEST) -v --tb=short -n $(N_PARALLEL) $(MARKER_ARGS) $(PYTEST_ARGS)
