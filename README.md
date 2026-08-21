# SafeCO

Track E prototype: an advisory monitor for unsafe commands in a simulated industrial control system.

## Backend foundation

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=src pytest -q
```

The initial backend provides the shared event contract and a local SQLite event store with a tamper-evident hash chain. The simulator and dashboard will consume this contract.

## Before contributing

Read, in order: `context.md`, `architecture.md`, `docs/plant_contract.md`, then `team_handoff.md`. The product name is **SafeCO** and the Python package/import name is `safeco`.
