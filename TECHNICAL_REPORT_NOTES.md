# SafeCO Technical Report Notes

Working evidence file for the final ICSC 2026 technical report (maximum four pages).
Keep claims here tied to a reproducible command, test, scenario, or stored artifact.

## Submission claim

SafeCO is a local-first, explainable monitor for unsafe commands in a simulated
Adupe Municipal Water Station. It detects commands that are protocol-valid but
unsafe in the current process context, preserves evidence, and advises an engineer.
It never independently blocks, reverses, delays, or issues a consequential
plant-control command.

## Architecture proof points

- Frozen plant/register contract: `src/safeco/plant.py`, `docs/plant_contract.md`.
- Deterministic Adupe simulator with seeded commands, snapshots, and normal scenarios.
- Localhost Modbus TCP adapter with rejected-write recording.
- Shared normalized `Event` contract in `src/safeco/events.py`.
- SQLite WAL event store retaining raw JSON and a tamper-evident hash chain.
- Backend integration path: simulator command -> `EventCollector` -> SQLite -> detector callback.
- Ruff lint/format rules and contributor workflow are documented in `AGENTS.md` and
  `CONTRIBUTING.md`.

## Current evidence (24 August 2026)

- `main` includes simulator, scenario, tooling, and backend integration PRs.
- Latest merged integration commit: `80db5c1`.
- Integration test verifies three simulator commands become ordered events, retain
  process context and register metadata, reach a detector callback, and verify the
  SQLite hash chain.
- Ruff check passes.
- Ruff format check passes.
- Repository suite currently reports 40 passing tests plus two live Modbus TCP tests
  that cannot bind localhost in this restricted execution environment. Re-run those
  tests on a normal developer laptop/CI and record the result here.

## Implemented scope

- Plant state, register map, safety invariants, and deterministic physics.
- Normal scenarios: startup, steady running, controlled shutdown, grid recovery.
- Seed and generator-version recording for scenario reproducibility.
- Protocol validation, cross-register-family rejection, and rejected-write protection.
- Event serialization, SQLite persistence, chain verification, and simulator integration.
- Advisory-only response semantics.

## Remaining required work

- Maintenance scenario and benign maintenance tests.
- Four attack scenario runners: injection, replay, mistimed valid command, and gradual drift.
- Hybrid detector: invariants, transition checks, replay/sequence, rate/drift, optional baseline.
- Structured alert contract, evidence, severity, confidence, recommendation, and acknowledgement.
- FastAPI endpoints and local dashboard.
- Offline collection/reconnect catch-up and degraded-visibility state.
- Held-out evaluation with precision, recall, false alerts per normal hour, latency,
  confusion matrix, missed attacks, and maintenance false positives.
- One-command demo packaging, screenshots, four-page report, and clean-checkout rehearsal.

## Evidence to capture next

For each scenario, record: command to run, seed, generator version, event count,
expected ground truth, alert result, detection latency, and a representative event/
alert JSON pair. Keep tuning/validation/held-out scenario IDs separate.

## Final report outline

1. Problem and threat model.
2. Adupe simulator, normalized event contract, and local architecture.
3. Hybrid detection rules and human-in-the-loop response.
4. Synthetic-data generation and held-out evaluation.
5. Demonstration results, limitations, and future work.

## Accuracy guardrails

- Adupe is fictional and representative; no real plant or operational dataset is claimed.
- Modbus validity is not process safety.
- Hash-chain verification detects later stored-event modification, not false sensors.
- Internet loss differs from loss of the local control feed.
- Critical alerts escalate and recommend checks; an engineer chooses plant action.
- Do not claim electricity support, autonomous shutdown, or unimplemented detector/API/UI work.
