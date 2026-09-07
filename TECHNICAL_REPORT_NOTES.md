# SafeCO Technical Report Notes

Working evidence file for the final ICSC 2026 technical report (maximum four pages).
Keep claims here tied to a reproducible command, test, scenario, or stored artifact.

## Submission claim

SafeCO is a local-first, explainable monitor for unsafe commands in a simulated
Adupe Municipal Water Station. It detects commands that are protocol-valid but
unsafe in the current process context, preserves evidence, and advises an engineer.
It never independently blocks, reverses, delays, or issues a consequential
plant-control command.

SafeCO may support a simulator-only action explicitly confirmed by an engineer.
That action records the operator, alert, exact command, timestamp, and resulting
state; it is distinct from autonomous response and is not a real-plant control path.

## Architecture proof points

- Frozen plant/register contract: `src/safeco/plant.py`, `docs/plant_contract.md`.
- Deterministic Adupe simulator with seeded commands, snapshots, and normal scenarios.
- Localhost Modbus TCP adapter with rejected-write recording.
- Shared normalized `Event` contract in `src/safeco/events.py`.
- SQLite WAL event store retaining raw JSON and a tamper-evident hash chain.
- Backend integration path: simulator command -> `EventCollector` -> SQLite -> detector callback.
- Ruff lint/format rules and contributor workflow are documented in `AGENTS.md` and
  `CONTRIBUTING.md`.

## Current evidence (25 August 2026)

- `main` includes simulator, scenario, tooling, and backend integration PRs.
- Latest merged integration commit: `80db5c1`.
- Integration test verifies three simulator commands become ordered events, retain
  process context and register metadata, reach a detector callback, and verify the
  SQLite hash chain.
- Ruff check passes.
- Ruff format check passes.
- Maintenance, extended-normal, scenario fingerprint, and CLI tests passed in the
  Phase 2 scenario PR review (27 relevant tests).
- Two live Modbus TCP tests cannot bind localhost in this restricted execution
  environment. Re-run those tests on a normal developer laptop/CI and record the
  result here.

## Implemented scope

- Plant state, register map, safety invariants, and deterministic physics.
- Normal scenarios: startup, steady running, controlled shutdown, grid recovery,
  maintenance, and an extended normal run.
- `maintenance_01`: labelled `maintenance`; enters maintenance mode, performs five
  authorised +1% target-level changes and five restores, then returns to RUNNING
  with no invariant violations.
- `extended_normal_01`: approximately 969 simulated seconds of demand variation
  plus a benign outlet-valve service cycle; tested level range remains bounded.
- Seed, generator-version, ground-truth, and SHA-256 scenario-fingerprint recording
  provide reproducibility evidence. The scenario CLI can print run metadata and a
  fingerprint using `python -m safeco.scenarios <scenario> --seed 42 --fingerprint`.
- Protocol validation, cross-register-family rejection, and rejected-write protection.
- Event serialization, SQLite persistence, chain verification, and simulator integration.
- Advisory-only response semantics.
- Human-confirmed simulator actions are an optional response demonstration; no
  timeout or autonomous fallback is permitted.

## Remaining required work

- Four attack scenario runners: injection, replay, mistimed valid command, and gradual drift.
- Hybrid detector: invariants, transition checks, replay/sequence, rate/drift, optional baseline.
- Structured alert contract, evidence, severity, confidence, recommendation, and acknowledgement.
- FastAPI endpoints and local dashboard.
- Optional confirmed simulator action with operator and command audit fields.
- Offline collection/reconnect catch-up and degraded-visibility state.
- Held-out evaluation latency, confusion matrix, and expanded error analysis.
- One-command demo packaging, screenshots, four-page report, and clean-checkout rehearsal.

## Evidence to capture next

For each scenario, record: command to run, seed, generator version, fingerprint,
event count, expected ground truth, alert result, detection latency, and a
representative event/alert JSON pair. Keep tuning/validation/held-out scenario IDs
separate.

## Detector evaluation notes

- `src/safeco/evaluation.py` replays complete normal and attack scenarios through
  the shared event contract and detector.
- The evaluator reports precision, recall, false alerts per normal hour, missed
  attacks, maintenance false positives, first detection event ID, and detection
  latency in events and seconds.
- Evaluation reports include a per-scenario classification table and aggregate
  TP/FP/TN/FN counts.
- Attack expectations are explicit: injection -> `unsafe_pump_start`, replay ->
  `command_replay`, mistimed -> `recovery_out_of_sequence`, and drift ->
  `setpoint_drift`.
- Layer 5 statistical baseline training is implemented in `src/safeco/baseline.py`
  using conservative median/MAD feature ranges learned from benign scenario
  traces.
- The evaluation CLI enables the baseline by default. Use `--without-baseline`
  for rule-only metrics, or `--compare` to print rule-only and baseline-enabled
  reports side by side.
- Baseline-enabled metrics train Layer 5 only from benign tuning scenarios;
  validation and held-out scenarios are excluded from `BaselineProfile.training_scenarios`.
- Three baseline-only anomaly scenarios demonstrate Layer 5's added coverage:
  `attack_baseline_low_tank_01`, `attack_baseline_high_limit_01`, and
  `attack_baseline_mode_context_01`.
- `python -m safeco.evaluation --samples-json` emits representative event/alert
  JSON pairs for report evidence.
- Scenario splits are explicit and non-overlapping: tuning, validation, and
  held-out.
- Known limitations are tracked in `docs/detector_evaluation.md`.

## Process realism and benign anomalies (7 September 2026)

- Three benign-anomaly scenarios extend `extended_normal_01`, all labelled
  `normal` and invariant-free:
  - `benign_spike_01` — transient +3% tank-level sensor blip, self-restoring.
  - `benign_duty_jitter_01` — drain/fill durations jittered ±15% per cycle.
  - `benign_setpoint_nudge_01` — observed target-level +0.5% blip then restore.
- Anomalies perturb the *observed* telemetry copy only; the true `PlantState`
  is never mutated, so invariant checks cannot trip on a sensor artifact
  (`_perturbed_observed` in `src/safeco/scenarios.py`).
- Deterministic, seed-keyed anomaly RNG: `Random(f"{seed}:{scenario_id}:{GENERATOR_VERSION}")`.
- Generator version bumped to `safeco-scenarios/1.2`.
- Process-realism evidence module `src/safeco/realism.py` checks level bounds,
  flow balance, valve/pump consistency, bounded tank slew, zero violations,
  and monotonic event timestamps per scenario. Reproduce:
  ```bash
  PYTHONPATH=src .venv/bin/python -c "from safeco.realism import check_process_realism; print(check_process_realism('benign_duty_jitter_01'))"
  ```
- Reproducible fingerprints (seed 42):
  - `benign_spike_01`: `637543c89fb71784e77fbbe334c8bbd6729f425d372766383dc29b9007fa3047`
  - `benign_duty_jitter_01`: `20567190cdee4d630a6d88c413277219b6cabaafff54f4314ccbc76dfbd43bdd`
  - `benign_setpoint_nudge_01`: `60b941e6e5c479882c91f4d2daaa6d456e8a890eb2c908c4418df46232b9c074`
- Evaluation timestamp fix (Task 2): scenario event traces are now stamped
  from simulated elapsed time instead of wall clock, removing the nondeterministic
  `STALE_TIMESTAMP` false positive. See commit `56c692f` and flag for Joseph/Daniel
  review of `src/safeco/evaluation.py`.
- Evaluation harness replays raw steps today and so sees clean traces; hooking
  `ANOMALY_PLANS` into `events_for_scenario` when baseline metrics must exercise
  the anomalies is a Joseph/Daniel follow-up.

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
