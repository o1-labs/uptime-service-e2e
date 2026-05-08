.PHONY: install up down test logs clean ps schema env

COMPOSE := docker compose -f compose/docker-compose.yaml --env-file .env
SCHEMA_PATH := compose/config/postgres-init.sql
SCHEMA_URL_TEMPLATE := https://raw.githubusercontent.com/o1-labs/uptime-service-validation/$$VALIDATION_TAG/uptime_service_validation/database/create_tables.sql

install:
	pip install -e .

env:
	@test -f .env || cp .env.example .env

# Fetch the canonical Postgres schema from the same uptime-service-validation
# release we're about to run. Pinning to VALIDATION_TAG (instead of vendoring
# a copy in this repo) eliminates schema drift — the e2e harness is always
# testing against the schema the running image actually expects.
schema: env
	@. ./.env && \
	if [ -z "$$VALIDATION_TAG" ]; then echo "VALIDATION_TAG not set in .env"; exit 1; fi && \
	echo "Fetching schema from validation $$VALIDATION_TAG" && \
	curl -fsSL -o $(SCHEMA_PATH) "$(SCHEMA_URL_TEMPLATE)"

up: schema
	$(COMPOSE) up -d

down:
	$(COMPOSE) down -v

test:
	pytest

logs:
	$(COMPOSE) logs -f

ps:
	$(COMPOSE) ps

clean:
	rm -rf .pytest_cache __pycache__ tests/__pycache__ $(SCHEMA_PATH)
