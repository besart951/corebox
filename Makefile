.PHONY: sync check test build verify dev migrate
sync:
	uv sync --all-extras --dev
check:
	uv run ruff format --check .
	uv run ruff check .
	uv run ty check
test:
	uv run pytest
build:
	uv build
verify: check test build
	uv run python scripts/check_distribution.py
dev:
	uv run fastapi dev examples/example_app/dev.py
migrate:
	uv run --env-file .env alembic upgrade heads
