# Mahoraga — Methodology Section (Input for 4-page ICSC 2026 Technical Report)

## 1. Plant model & frozen register map
- **Register map** (`src/safeco/plant.py`, `docs/plant_contract.md`): coils 0–2 (pump, inlet valve, outlet valve), input registers 100–106 (telemetry), holding registers 200–202 (target level, high-level limit, mode command).
- **Contract freeze**: per `AGENTS.md` / `team_handoff.md:228–235`, no shared-contract changes (`plant.py`, `events.py`, `plant_contract.md`, `context.md`, `architecture.md`) without team agreement. All scenario logic is additive on top of the frozen map.
- **Operating modes** (`ONBOARDING.md:93–101`): SHUTDOWN(0) → STARTUP(1) → RUNNING(2) → MAINTENANCE(3) → RECOVERY(4) → STARTUP → RUNNING. Invariants: pump cannot run without open inlet path; tank level within safe limits; setpoint changes rate-limited and authorised in maintenance.

## 2. Determinism contract
- **Seed → reproducibility**: `PlantSimulator(seed=42)` → identical command sequences, snapshots, violations across CLI, dashboard (`run_scenario_and_persist`), and evaluation harness. Generator version recorded as `safeco-scenarios/1.3` (`src/safeco/scenarios.py:29`).
- **CLI reproduce command**: `PYTHONPATH=src .venv/bin/python -m safeco.scenarios <scenario_id> --seed 42 --fingerprint` prints the SHA-256 fingerprint seen in the report.
- **Phase 5 additions** (PR #15, #16): bounded telemetry noise (`telemetry_noise` plan kind, 3σ-clamped gaussian on observed `tank_level`/`flow_rate` only; true `PlantState` never mutated) and attack timing-jitter variants (`attack_*_jitter_01`). Jitter varies approach-phase durations only; command payloads and invariant-violation sets are identical to base attacks. Registered in a separate `ATTACK_JITTER_SCENARIOS` registry so `ATTACK_SCENARIOS` exact-set assertion is unchanged.

## 3. Scenario catalogue (21 total, seed 42)
| ID | Type | Ground truth | Reason code (detector) |
|---|---|---|---|
| **Normal** (`NORMAL_SCENARIOS`) |
| startup_01 | Normal | normal | — |
| steady_running_01 | Normal | normal | — |
| controlled_shutdown_01 | Normal | normal | — |
| grid_recovery_01 | Normal | normal | — |
| maintenance_01 | Normal | maintenance | — |
| extended_normal_01 | Normal | normal | — |
| **Benign anomalies** (extend `extended_normal_01`, labelled `normal`, invariant-free) |
| benign_spike_01 | Normal | normal | — |
| benign_duty_jitter_01 | Normal | normal | — |
| benign_setpoint_nudge_01 | Normal | normal | — |
| benign_noise_01 | Normal | normal | — |
| **Base attacks** (`ATTACK_SCENARIOS`) |
| attack_injection_01 | Injection | injection | `unsafe_pump_start` |
| attack_replay_01 | Replay | replay | `command_replay` |
| attack_mistimed_01 | Mistimed | mistimed | `recovery_out_of_sequence` |
| attack_drift_01 | Drift | drift | `setpoint_drift` |
| **Baseline-only anomalies** (protocol-valid, no deterministic-rule trigger) |
| attack_baseline_low_tank_01 | Anomaly | baseline_anomaly | `baseline_deviation` |
| attack_baseline_high_limit_01 | Anomaly | baseline_anomaly | `baseline_deviation` |
| attack_baseline_mode_context_01 | Anomaly | baseline_anomaly | `baseline_deviation` |
| **Jitter variants** (same payloads/violations as base, different timing; separate registry) |
| attack_injection_jitter_01 | Injection | injection | `unsafe_pump_start` |
| attack_replay_jitter_01 | Replay | replay | `command_replay` |
| attack_mistimed_jitter_01 | Mistimed | mistimed | `recovery_out_of_sequence` |
| attack_drift_jitter_01 | Drift | drift | `setpoint_drift` |

*Note*: Fingerprints are generator-version-dependent (`1.3` as of PR #16 follow-up). The report cites `safeco-scenarios/1.3` and flags version as a known limitation per the accuracy guardrails.

## 4. Perturbation design (PR #15/#16 novelty)
- **Observed-layer-only perturbation**: Anomaly plans perturb a *copy* of the observed telemetry (`_perturbed_observed` in `scenarios.py:200`); the true `PlantState` is never mutated. This guarantees invariant checks (`plant.py:validate()`) cannot trip on a sensor artifact.
- **RNG seeding**: `Random(f"{seed}:{scenario_id}:{GENERATOR_VERSION}")` (`scenarios.py:210`) ensures deterministic, reproducible perturbation across runs.
- **Benign noise** (`benign_noise_01`): 3σ-clamped gaussian added to observed `tank_level`/`flow_rate` only; gives Layer-5 baseline a realistic noisy benign envelope.
- **Timing jitter** (`attack_*_jitter_01`): varies approach-phase pre-attack silence/injection cadence; same command payloads and same invariant-violation set as base attacks; detection must lean on process context, not fixed clock offsets.
- **Process-realism evidence** (`src/safeco/realism.py`): checks level bounds, flow balance, valve/pump consistency, bounded tank slew, zero violations, and monotonic event timestamps per scenario. Reproduced via:
  ```bash
  PYTHONPATH=src .venv/bin/python -c "from safeco.realism import check_process_realism; print(check_process_realism('benign_noise_01'))"
  ```

## 5. Limitations (accuracy guardrails, per `TECHNICAL_REPORT_NOTES.md:174-181`)
- Adupe is fictional and representative; no real plant or operational dataset is claimed.
- Modbus validity does not mean process safety.
- Hash-chain verification detects later stored-event modification, not false sensors.
- Internet loss differs from loss of the local control feed.
- Critical alerts escalate and recommend checks; an engineer chooses plant action.
- Do not claim electricity support, autonomous shutdown, or unimplemented detector/API/UI work.
- Synthetic scenarios are deterministic and may not cover all benign operator behaviour.
- Ground-truth labels are used only for evaluation, never for detection decisions.
- Statistical baseline depends on coverage of benign training scenarios; held-out scenarios are excluded from training.

## Provenance: `TECHNICAL_REPORT_NOTES.md` refresh (A2)
- **Evidence date**: "Current evidence (25 August 2026)" → updated to reflect PR #16 merge (Sep 11, 2026) and follow-up eval commits (`30a85c4`, `ab3c2e7`).
- **Remaining work list** (lines 63-72 of original): items now merged (attacks, detector, API, dashboard) removed; only write-up assembly and figures remain as Phase 6 work.
- **Generator version**: documented as `1.3` per `src/safeco/scenarios.py:29`; fingerprints re-computed at this version. Version change is a known limitation per the accuracy guardrails (`TECHNICAL_REPORT_NOTES.md:174-181`).

---
*This section is Mahoraga's exclusive input for Daniel's 4-page report assembly. No shared contracts were modified.*
