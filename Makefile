SHELL := /bin/bash
COMPOSE := docker compose -f infra/docker-compose.yml

.PHONY: help build dev down logs ps shell test lint ci clean

help: ## show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-10s %s\n", $$1, $$2}'

build: ## build the pinned dev image (slow; once)
	$(COMPOSE) build

dev: ## start Solana base validator + local MagicBlock ER
	$(COMPOSE) up -d base er

down: ## stop the stack
	$(COMPOSE) down

logs: ## follow stack logs
	$(COMPOSE) logs -f

ps: ## show stack status
	$(COMPOSE) ps

shell: ## open a shell in the dev image (repo mounted at /workspace)
	$(COMPOSE) run --rm tools bash

test: ## validate contracts, runtime and ledger service behavior
	python3 infra/scripts/validate_contracts.py
	python3 -m unittest discover -s apps/runtime/tests -v
	node --experimental-strip-types --test apps/ledger/test/ledger.test.ts

lint: ## JSON validity + python syntax
	python3 -m compileall -q infra/scripts
	python3 -m compileall -q apps/runtime/looprail apps/dashboard/server.py
	@for f in packages/contracts/*.schema.json packages/contracts/examples/*.json; do \
		python3 -c "import json,sys; json.load(open('$$f'))" || exit 1; \
	done
	@echo "lint ok"

ci: lint test ## exactly what CI runs

clean: ## stop and remove containers/volumes
	$(COMPOSE) down -v
