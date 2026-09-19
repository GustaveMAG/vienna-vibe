# Raccourcis de développement.
.PHONY: help install lint test up down migrate run stats logs clean

help:
	@echo "install   Installe le paquet et les outils de développement"
	@echo "lint      Analyse statique (ruff)"
	@echo "test      Tests unitaires"
	@echo "up        Démarre PostgreSQL et Airflow"
	@echo "down      Arrête la pile"
	@echo "migrate   Applique le schéma"
	@echo "run       Exécute le pipeline une fois, en local"
	@echo "stats     Affiche les chiffres du jeu de données"
	@echo "logs      Suit les logs Airflow"
	@echo "clean     Supprime les caches"

install:
	pip install -e ".[dev]"

lint:
	ruff check src tests dags
	ruff format --check src tests

test:
	pytest

up:
	docker compose up -d
	@echo "Airflow : http://localhost:$${AIRFLOW_PORT:-8080}"

down:
	docker compose down

migrate:
	vienna-vibe migrate

run:
	vienna-vibe run -v

stats:
	vienna-vibe stats

logs:
	docker compose logs -f airflow

clean:
	rm -rf .pytest_cache .ruff_cache .coverage htmlcov
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
