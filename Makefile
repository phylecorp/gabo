VENV := venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: install test test-local-llms lint format

install: $(VENV)/bin/activate

$(VENV)/bin/activate:
	python3 -m venv $(VENV)
	$(PIP) install -e ".[dev,all]"

test:
	$(PYTHON) -m pytest tests/ -v

# Live tests against local Ollama (:11434) and LM Studio (:1234) native APIs.
# Skips each provider if its server is not reachable.
test-local-llms:
	$(PYTHON) -m pytest -m integration tests/test_providers/test_local_llm_live.py -v

lint:
	$(PYTHON) -m ruff check src/ tests/

format:
	$(PYTHON) -m ruff format src/ tests/
