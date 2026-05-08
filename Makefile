.PHONY: install up down test logs clean ps

COMPOSE := docker compose -f compose/docker-compose.yaml --env-file .env

install:
	pip install -e .

up:
	test -f .env || cp .env.example .env
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
	rm -rf .pytest_cache __pycache__ tests/__pycache__
