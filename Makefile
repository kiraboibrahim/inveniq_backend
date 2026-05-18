
# Variables
DC = docker compose
EXEC = $(DC) exec web
MANAGE = $(EXEC) python manage.py

.PHONY: build up down logs migrate makemigrations superuser test shell bash

build:
	$(DC) build

up:
	$(DC) up -d

down:
	$(DC) down

logs:
	$(DC) logs -f

migrate:
	$(MANAGE) migrate

makemigrations:
	$(MANAGE) makemigrations

superuser:
	$(MANAGE) createsuperuser

test:
	$(DC) run --rm test pytest

shell:
	$(MANAGE) shell

bash:
	$(EXEC) bash
