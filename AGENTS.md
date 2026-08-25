# SafeCO Engineering Standards

Instructions for coding agents and contributors. Read `context.md`, `architecture.md`, and `docs/plant_contract.md` before changing direction or shared interfaces. Git workflow, branch naming, commit style, and PR rules live in `CONTRIBUTING.md`.

## Commands

Run from the repo root before every commit:

```bash
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
PYTHONPATH=src .venv/bin/python -m pytest -q
git diff --check
```

All four must pass. Dev tools are pinned in `requirements-dev.txt`; install with `uv pip install --python .venv/bin/python -r requirements-dev.txt`.

## Python conventions

- **Formatter/linter:** ruff only (`pyproject.toml`). Rule sets: `E`/`W` pycodestyle, `F` pyflakes, `I` import order, `N` naming, `B` bugbear, `D` pydocstyle. Do not weaken rules without a PR discussion.
- **Line length:** 88 columns.
- **Naming:** PEP 8. The one sanctioned exemption is `setValues` in Modbus adapters (pymodbus API override), marked `# noqa: N802`.
- **Typing:** annotate public function signatures; use `from __future__ import annotations`. No mypy gate yet.
- **Docstrings:** Google Python Style (PEP 257). Summary line, blank line, then `Args:`, `Returns:`, `Raises:` sections as needed. Types omitted from `Args` when PEP 484 annotations are present. Public classes, public methods, key private helpers, and all modules require docstrings.
- **Errors:** raise domain exceptions (e.g. `ProtocolError`) with actionable messages. Never bare `except:`; catch the narrowest type and record context where it matters (see `rejected_writes` in `modbus_server.py`).
- **Determinism:** anything generating data must be seed-reproducible and record its generator version. No wall-clock-dependent logic in simulator/scenario code paths.
- **Advisory-only invariant:** the system advises a human and never blocks process actions automatically. Unsafe-but-protocol-valid commands are applied and recorded, never silently dropped.
- **Comments:** explain why, not what. No speculative TODOs — open an issue or note it in the PR body.

## Shared contracts

Changes to `src/safeco/events.py`, `src/safeco/plant.py`, `docs/plant_contract.md`, `architecture.md`, or `context.md` require a compatibility explanation in the PR and Daniel's review. Prefer additive fields with defaults. Formatting-only changes to these files must still be flagged as such in the PR body.
