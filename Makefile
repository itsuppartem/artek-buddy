PYTHON ?= python3
export PYTHONPATH := src
VENV := .venv
VENV_PY := $(VENV)/bin/python
NODE := $(HOME)/.local/node/bin
export PATH := $(NODE):$(PATH)

.PHONY: test test-host test-web test-integration test-ui ensure-host-py

test: test-host test-integration test-web

host-py = $(if $(shell $(PYTHON) -c "import cursor_sdk" >/dev/null 2>&1 && echo yes),$(PYTHON),$(VENV_PY))

ensure-host-py:
	@if ! $(PYTHON) -c "import cursor_sdk" >/dev/null 2>&1; then \
		if [ ! -x "$(VENV_PY)" ]; then \
			$(PYTHON) -m venv $(VENV); \
			$(VENV_PY) -m pip install -q -r requirements.txt; \
		fi; \
	fi

test-host: ensure-host-py
	$(host-py) -m unittest discover -s tests -p 'test_*.py' -t . -q

test-integration: ensure-host-py
	$(host-py) tests/run_integration.py

test-web:
	cd client/web && npm test

test-ui: ensure-host-py
	cd client/web && npm run build
	$(host-py) tests/run_ui.py
