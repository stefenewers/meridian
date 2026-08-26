# Meridian — one command per thing you actually want to do.
.PHONY: help install train api web dev test lint typecheck build check clean

VENV := services/simulation/.venv
PY   := $(VENV)/bin/python
PIP  := $(VENV)/bin/pip

help:
	@echo "Meridian"
	@echo "  make install    Create the Python venv and install both stacks"
	@echo "  make train      Generate demand history and fit the quantile model (run once)"
	@echo "  make api        Start the simulation service on :8000"
	@echo "  make web        Start the product UI on :3001"
	@echo "  make test       Python test suite"
	@echo "  make check      typecheck + lint + tests + production build"

install:
	python3 -m venv $(VENV)
	$(PIP) install -q --upgrade pip
	$(PIP) install -q -r services/simulation/requirements-dev.txt
	npm install
	@echo "Installed. Next: make train"

train:
	cd services/simulation && ../../$(PY) scripts/train_demand_model.py --save-history

api:
	cd services/simulation && ../../$(VENV)/bin/uvicorn meridian.api:app --host 127.0.0.1 --port 8000 --reload

web:
	npm run dev --workspace @meridian/web

test:
	cd services/simulation && ../../$(PY) -m pytest tests -q

lint:
	cd services/simulation && ../../$(VENV)/bin/ruff check meridian scripts tests
	npm run lint --workspace @meridian/web

typecheck:
	npm run typecheck --workspace @meridian/web

build:
	npm run build --workspace @meridian/web

check: typecheck lint test build
	@echo "All checks passed."

clean:
	rm -rf $(VENV) node_modules apps/web/.next data/models data/demand_history.csv
