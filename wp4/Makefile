.PHONY: help lint format check test typecheck all clean

help:
	@echo "Available commands:"
	@echo "  make lint       - Run ruff linter"
	@echo "  make format     - Format code with ruff"
	@echo "  make check      - Run ruff check (lint + format check)"
	@echo "  make typecheck  - Run pyright type checker"
	@echo "  make test       - Run pytest"
	@echo "  make all        - Run all checks (lint, typecheck, test)"
	@echo "  make clean      - Remove cache and build files"

lint:
	uv run ruff check src/ tests/

format:
	uv run ruff format src/ tests/

check:
	uv run ruff check --fix src/ tests/
	uv run ruff format src/ tests/

typecheck:
	uv run pyright src/ tests/

test:
	uv run pytest tests/ -v

all: check typecheck test
	@echo "✓ All checks passed!"

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf build/ dist/ *.egg-info/
