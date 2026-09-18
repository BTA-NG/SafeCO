# SafeCO Contribution and Git Workflow

## Branches

`main` must remain runnable and tested. Do not commit unfinished work directly to `main`.

Use one branch per bounded change:

```text
feature/<short-description>
fix/<short-description>
test/<short-description>
docs/<short-description>
```

Examples: `feature/modbus-simulator`, `feature/hybrid-detector`, `feature/dashboard-alerts`.

## Pull requests

Open a PR into `main` for every change. Include what changed and why, how to run it, tests and results, interface changes, known limitations, and screenshots or sample output where relevant. At least one teammate reviews each PR. Daniel reviews changes to shared contracts, storage, runtime integration, safety semantics, or release packaging.

Do not merge failing tests, undocumented schema changes, invented metrics, or claims beyond the documented simulator model.

## Commits

Use short imperative commits with a component scope:

```text
feat(simulator): add deterministic Modbus tank process
feat(detector): detect unsafe pump start
feat(dashboard): show process state
fix(storage): verify chain after restart
test(detector): cover generator recovery
docs: clarify synthetic data generation
```

## Shared contracts

Before changing `src/safeco/events.py`, `src/safeco/plant.py`, `docs/plant_contract.md`, `architecture.md`, or `context.md`, explain compatibility impact in the PR. Prefer additive fields with defaults, and update tests and documentation in the same PR.

## Local checks

```bash
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
PYTHONPATH=src .venv/bin/python -m pytest -q
git diff --check
```

Lint and format rules are configured in `pyproject.toml` (tool: ruff, pinned in `requirements-dev.txt`).

Do not commit `.venv`, SQLite runtime databases, caches, credentials, real personal data, or unreviewed generated output.

## Release

Before release, run the complete demo from a clean checkout and record the commit, test result, scenario seed, and evaluation output.
