DOCKER ?= sudo docker
COMPOSE = $(DOCKER) compose -f docker-compose.yml -f docker-compose.dev.yml
PYTHON = .venv/bin/python

.PHONY: install up down logs check clean-data

install:
	cd api && python3 -m venv .venv && .venv/bin/python -m pip install -r requirements-dev.txt
	cd web && npm ci

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f --tail=100

check:
	cd api && $(PYTHON) -m ruff check app tests alembic && $(PYTHON) -m pytest
	cd web && npm run check
	$(COMPOSE) config --quiet

clean-data:
	$(COMPOSE) down --volumes
