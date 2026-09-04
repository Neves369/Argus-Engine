.PHONY: setup run test lint migrate revision

setup:
	python -m venv .venv
	.venv/bin/pip install -e ".[dev]"
	cp -n .env.example .env || true
	mkdir -p data

run:
	.venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

migrate:
	.venv/bin/alembic upgrade head

revision:
	.venv/bin/alembic revision --autogenerate -m "$(m)"

test:
	.venv/bin/pytest

lint:
	.venv/bin/ruff check app tests
