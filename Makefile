.PHONY: install lint typecheck test audit verify e2e scan design check reproduce

install:
	uv sync --locked --python 3.11

lint:
	uv run ruff check src tests
	uv run ruff format --check src tests

typecheck:
	uv run mypy

test:
	uv run pytest --cov --cov-report=term

verify:
	uv run safetylens historical verify

audit:
	uv run safetylens historical audit

e2e:
	uv run safetylens synthetic --out runs/synthetic

scan:
	uv run safetylens scan

design:
	uv run safetylens design compare --reps 2000 --out docs/DESIGN_COMPARISON.md

# Everything CI runs, offline.
check: lint typecheck test verify scan e2e
	uv run safetylens historical audit
	git diff --exit-code -- historical/

# Rebuild all committed generated artefacts (no network, no API calls).
reproduce: verify audit design e2e
