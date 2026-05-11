.PHONY: install up down test logs clean ps schema env net worker-image minimina-up minimina-down wait-for-blocks

COMPOSE := docker compose -f compose/docker-compose.yaml --env-file .env
SCHEMA_PATH := compose/config/postgres-init.sql
SCHEMA_URL_TEMPLATE := https://raw.githubusercontent.com/o1-labs/uptime-service-validation/$$VALIDATION_TAG/uptime_service_validation/database/create_tables.sql

# Shared docker network between our compose stack and the sibling
# docker-compose project minimina manages. See compose/docker-compose.yaml
# for the role of this network.
SHARED_NET := uptime-e2e-net

# Minimina network identifier; appears as a suffix in container names
# (e.g. node-a-e2e, default-seed-e2e) and is concatenated with the
# uptime-service-backend node name to form the hostname BPs target.
MINIMINA_NET := e2e
MINIMINA_HOME ?= $(CURDIR)/.minimina-home
export MINIMINA_HOME

# Topology + genesis are vendored; minimina resolves the relative paths
# inside topology.json against the cwd at invocation time, so all
# `minimina` calls below run from the repo root.
TOPOLOGY := fixtures/minimina/topology.json
GENESIS := fixtures/minimina/genesis_ledger.json

WORKER_LOCAL_IMAGE := uptime-e2e-worker
WORKER_LOCAL_TAG := dev

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

net:
	@docker network inspect $(SHARED_NET) >/dev/null 2>&1 || \
		docker network create $(SHARED_NET)

# Bake our minimina-network genesis into the submission-updater image
# under a known path. The validation coordinator doesn't pass arbitrary
# volume mounts or env to DinD-spawned workers, so the genesis has to
# live inside the image. See compose/worker/Dockerfile for context.
worker-image:
	cp $(GENESIS) compose/worker/genesis_ledger.json
	docker build -t $(WORKER_LOCAL_IMAGE):$(WORKER_LOCAL_TAG) compose/worker

minimina-up: net
	minimina --mode docker network create -n $(MINIMINA_NET) -t $(TOPOLOGY) -g $(GENESIS)
	# Drop the placeholder uptime-service-backend service we only kept in
	# the topology so minimina would bake `--uptime-url` into the BPs.
	# Our compose stack runs the real backend; we wire BPs to it via the
	# `docker network connect` loop below.
	python3 scripts/patch_minimina_compose.py \
		$(MINIMINA_HOME)/.minimina/$(MINIMINA_NET)/docker-compose.yaml \
		--dummy-service uptime-service-backend-$(MINIMINA_NET)
	minimina --mode docker network start -n $(MINIMINA_NET)
	# Dual-home each running minimina container on the shared external
	# network. Patching the file's `networks:` block is too late by this
	# point — `minimina network create` already locked in the project's
	# default network — so we attach after start. The backend service in
	# our compose exposes `uptime-service-backend-$(MINIMINA_NET)` as an
	# alias on this network, completing the resolution chain for BPs'
	# baked-in --uptime-url.
	for c in default-seed-$(MINIMINA_NET) snark-node-$(MINIMINA_NET) \
			snark-node-worker_1-$(MINIMINA_NET) \
			node-a-$(MINIMINA_NET) node-b-$(MINIMINA_NET) node-c-$(MINIMINA_NET); do \
		docker network connect $(SHARED_NET) $$c || true; \
	done

minimina-down:
	-minimina --mode docker network stop -n $(MINIMINA_NET)
	-minimina --mode docker network delete -n $(MINIMINA_NET)

up: schema net worker-image
	$(COMPOSE) up -d
	$(MAKE) minimina-up

down:
	-$(MAKE) minimina-down
	$(COMPOSE) down -v
	-docker network rm $(SHARED_NET)

test:
	pytest

logs:
	$(COMPOSE) logs -f

ps:
	$(COMPOSE) ps
	@echo "--- minimina ---"
	-minimina --mode docker network status -n $(MINIMINA_NET)

clean:
	rm -rf .pytest_cache __pycache__ tests/__pycache__ $(SCHEMA_PATH) \
		compose/worker/genesis_ledger.json $(MINIMINA_HOME)
