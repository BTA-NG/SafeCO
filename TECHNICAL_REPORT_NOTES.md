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

## Current evidence (17 September 2026)

- `origin/main` is at `1a296d7`, merging dashboard PR #17 after the timing/noise
  hardening PR #16. The merged tree includes the simulator, scenarios, detector,
  evaluation, persistent API stores, scenario runner, and operator dashboard.
- The merged dashboard branch passed Ruff, formatting, `git diff --check`, and
  269 tests on the demo laptop before merge.
- The final post-merge dashboard-clarity/baseline-integration changes passed all
  required checks on the demo laptop on 17 September: Ruff lint, Ruff formatting,
  `git diff --check`, and 273 tests in 3.00 seconds. The 28 warnings are
  third-party Starlette/FastAPI deprecations under Python 3.14, not failures.
- A live local run on 17 September verified the dashboard workflow: initial
  degraded visibility with no events; `startup_01` creating three normal events
  and a healthy feed; persisted event history; attack alerts; record-only
  acknowledgement; and stale-feed degradation with last-known values retained.
- Live attack evidence captured:
  - `attack_injection_01` -> HIGH `unsafe_pump_start` alert.
  - `attack_mistimed_01` -> HIGH `recovery_out_of_sequence` alert.
  - `attack_replay_01` -> HIGH `command_replay` plus the related unsafe pump/inlet
    invariant finding.
  - `benign_noise_01` -> persisted normal events and no attack alert.
- A direct post-review integration smoke test confirms `startup_01` produces
  3 events/0 alerts, `benign_noise_01` 10/0, `attack_injection_01` 1/1
  (`unsafe_pump_start`), and `attack_baseline_high_limit_01` 5/1
  (`baseline_deviation`) with the dashboard runner's cached tuning-only profile.
- Integration test verifies three simulator commands become ordered events, retain
  process context and register metadata, reach a detector callback, and verify the
  SQLite hash chain.
- Ruff check passes.
- Ruff format check passes.
- Maintenance, extended-normal, scenario fingerprint, and CLI tests passed in the
  Phase 2 scenario PR review (27 relevant tests).
- Joseph's detector/evaluation review passed Ruff and formatting checks and 84
  focused tests; the full detector branch reported 133 tests before merge.
- Local Modbus TCP tests require an environment that permits localhost socket binding;
  they passed in the developer worktree used to verify PR #15/#16. The restricted
  agent sandbox may reject those sockets, so sandbox failures must not be reported as
  product failures.
- `source="scheduler"` identifies the deterministic simulator command channel;
  `ground_truth` is synthetic evaluation metadata. Detection does not branch on
  either field.

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
- Structured alerts with deterministic IDs, evidence, severity, confidence,
  recommendations, and acknowledgement fields.
- Detector layers for invariants, state transitions, replay/sequence, command-rate,
  and setpoint drift checks.
- Conservative median/MAD baseline scoring with baseline-only anomaly fixtures.
- Scenario-level evaluation with explicit tuning, validation, and held-out splits,
  classification counts, precision, recall, false-alert rate, and latency fields.
- Human-confirmed simulator actions are documented as an optional response
  demonstration; no timeout or autonomous fallback is permitted.
- API routes are implemented for health, events, alerts, plant state, scenario
  discovery, and scenario execution. Events and alerts persist in separate SQLite
  stores; acknowledgements survive replay/restart.
- The no-build dashboard provides plant state, registered-scenario event filtering,
  alert filters/search, pagination, scenario execution, system health, and degraded
  last-known visibility. The site identity is fixed to the fictional Adupe facility.
- Scenario execution uses the canonical `run_scenario` path and runs the rule layers
  plus the deterministic tuning-only median/MAD baseline cached by seed.
- PR #16 adds bounded telemetry-noise and timing-jitter anomaly variants, observed
  state snapshots for evaluation handoff, and realism evidence; these additions
  preserve deterministic seeds and generator-version recording.

## Remaining required work

- Commit, push, and review the final UI/documentation/baseline-integration changes;
  the complete required checks now pass on the demo laptop.
- Capture clean held-out evaluation output, final metric tables, and representative
  event/alert JSON from the final tree.
- Select and archive the strongest dashboard screenshots, then write the final
  maximum-four-page report.
- Rehearse a clean-database, one-command local demo and prepare an offline screen
  recording as fallback.
- The optional engineer-confirmed simulator action remains unimplemented. Do not
  imply that acknowledgement changes plant state.

## Dashboard transport

- The implemented dashboard uses two-second HTTP polling and immediate refresh after
  scenario runs, acknowledgement, filter changes, and manual refresh.
- SSE was preferred over WebSockets for a future push transport because the dashboard
  is read-dominant and writes already use explicit REST calls. SSE is not implemented
  and must not be claimed in the submission.
- Any future stream must publish after successful persistence, use bounded per-client
  queues, and never block the simulator, collector, or SQLite writer.

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
- Current evaluation results are synthetic and scenario-based; they are evidence of
  reproducibility and detector behavior, not operational performance in a real plant.
- Do not report baseline-enabled results without naming the tuning-only training set
  and the separate validation/held-out scenarios.

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
- `events_for_scenario` now composes canonical `run_scenario`, maps observed analog
  telemetry into evaluated event features, and retains command-time discrete state.
  Registered anomalies therefore reach evaluation without manufacturing transition
  false positives.

## Hardening: attack timing variation + telemetry noise (8 September 2026)

- Bounded telemetry noise on the observed layer: `telemetry_noise` plan kind
  adds 3σ-clamped gaussian noise to observed `tank_level`/`flow_rate` only; the
  true `PlantState` stays clean so invariants never trip on a sensor artifact.
  New `benign_noise_01` (steady running, `normal`) gives the Layer-5 baseline a
  realistic noisy benign envelope.
- Attack timing variation: `attack_*_jitter_01` variants jitter the approach
  phase durations (pre-attack silence for injection/replay/mistimed; cadence for
  drift). Same command payloads and same invariant-violation set as the base
  attacks; detection must lean on process context, not fixed clock offsets.
  Registered in `ATTACK_JITTER_SCENARIOS`; evaluation and API discovery combine the
  base and jitter attack registries, with each jitter variant mapped to its base
  attack reason code.
- Generator version bumped to `safeco-scenarios/1.3`.
- `ScenarioResult.step_durations` records perturbed durations, so evaluation event
  timestamps and detection latency reflect the actual jittered simulated timeline.
- Reproducible fingerprints (seed 42):
  - `benign_noise_01` (normal): `6ff5662b1a1cdb43b73d30310bf4381c381d249645467e719a4be35da85eca2f`
  - `attack_injection_jitter_01` (injection): `11f5cfdd81281a156c30609dc9d4742da16568d72681b20c966acaee35333d44`
  - `attack_replay_jitter_01` (replay): `1d7322c7e1a8c33627b070ad5f5b8310af687496049bf2bb359b4e4730b44cda`
  - `attack_mistimed_jitter_01` (mistimed): `44f11c548bffeb24fe7e00e087f1b3b155f321bae513d106d7125eaa6b5a2330`
  - `attack_drift_jitter_01` (drift): `8df39f0de234ec4238644fac0a4626b03e970015c489d25082f38cbbf49c7771`
- Realism evidence reproduces via `check_process_realism("benign_noise_01")`
  including the `bounded_noise` check.

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
