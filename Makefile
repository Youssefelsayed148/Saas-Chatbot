# Day-to-day Docker commands for the dev stack. Run `make help`.
# Never loads an implicit .env; uses .env.local only when it exists, and never prints secrets.
# Requires GNU make (Windows: `winget install ezwinports.make`, or run from Git Bash/WSL).

export COMPOSE_DISABLE_ENV_FILE := 1
unexport COMPOSE_ENV_FILES

ENV_FILE := $(if $(wildcard .env.local),--env-file .env.local,)
DC := docker compose -f compose.yaml $(ENV_FILE)
DB_USER ?= saas
DB_NAME ?= saas_dev
SVC ?=

.DEFAULT_GOAL := help
.PHONY: help up build rebuild down restart ps logs logs-api logs-worker logs-web health \
        seed staff migrate psql shell-api shell-web config reset-db nuke

help: ## Show this help
	@awk 'BEGIN{FS=":.*## "} /^[a-zA-Z_-]+:.*## /{printf "  %-12s %s\n",$$1,$$2}' $(MAKEFILE_LIST)

up: ## Build (if needed) and start the whole stack, wait until healthy
	$(DC) up --build -d --wait

build: ## Build images only (SVC=api to limit)
	$(DC) build $(SVC)

rebuild: ## Rebuild without cache and restart the stack
	$(DC) build --no-cache $(SVC)
	$(DC) up -d --wait

down: ## Stop the stack (keeps database and uploads)
	$(DC) down

restart: ## Restart services (SVC=api|worker|web, default all)
	$(DC) restart $(SVC)

ps: ## Show container status
	$(DC) ps -a

logs: ## Follow logs of all services (SVC=api to limit)
	$(DC) logs -f --tail=100 $(SVC)

logs-api: ## Follow API logs
	$(DC) logs -f --tail=100 api

logs-worker: ## Follow worker logs (ingestion / embeddings)
	$(DC) logs -f --tail=100 worker

logs-web: ## Follow web logs
	$(DC) logs -f --tail=100 web

health: ## Check API readiness and web
	@curl -fsS http://127.0.0.1:8000/ready && echo && curl -fsSI http://127.0.0.1:3000 | head -1

seed: ## Seed the demo org (needs PLATFORM_STAFF_PASSWORD; may incur embedding cost)
	$(DC) --profile seed up seed

staff: ## Re-run the platform-admin bootstrap (after changing the staff password)
	$(DC) run --rm staff

migrate: ## Run Alembic migrations to head
	$(DC) run --rm migrate

psql: ## Open a psql shell in the database
	$(DC) exec db psql -U $(DB_USER) -d $(DB_NAME)

shell-api: ## Shell inside the API container
	$(DC) exec api sh

shell-web: ## Shell inside the web container
	$(DC) exec web sh

config: ## Validate compose file (fails if required keys are missing; secrets are not printed)
	$(DC) config --quiet && echo "compose config OK"

reset-db: ## DESTROYS database and uploads, then restarts fresh (asks first)
	@printf "This deletes ALL data (db + uploads). Type 'yes' to continue: " && read a && [ "$$a" = yes ]
	$(DC) down -v
	$(DC) up --build -d --wait

nuke: ## DESTROYS data and removes built images (asks first)
	@printf "This deletes ALL data and images. Type 'yes' to continue: " && read a && [ "$$a" = yes ]
	$(DC) down -v --rmi local
