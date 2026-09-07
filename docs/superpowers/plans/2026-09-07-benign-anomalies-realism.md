# Benign Anomalies & Process Realism Implementation Plan

> **For agentic workers:** Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement task-by-task. Steps use `- [ ]` syntax.

**Goal:** Add benign, invariant-safe anomalies and process-realism evidence to the SafeCO scenario library so Joseph's detector evaluation has a realistic false-positive baseline.

**Architecture:** Extend the scenario executor (`_execute`) to apply an opt-in `AnomalyPlan` that perturbs *observed* snapshots and step durations while leaving the true `PlantState` untouched, so invariants never trip on a sensor artifact. New benign scenarios live in `NORMAL_SCENARIOS` (ground truth `normal`); a new `realism.py` module asserts physical plausibility and records the evidence in report notes.

**Tech Stack:** Python 3, ruff, pytest, built-in `random` and `hashlib` (no new deps).

**Branch:** `feature/benign-anomalies-realism` (per CONTRIBUTING.md `feature/<short-description>`)

## Global Constraints (from AGENTS.md / context.md / team_handoff.md)

- Line length 88; ruff rule sets E/W, F, I, N, B, D. Run `.venv/bin/ruff check src tests` and `.venv/bin/ruff format --check src tests`.
- Deterministic: seed-reproducible, retain `GENERATOR_VERSION`; no wall-clock dependence. New `random.Random(...)` uses a fixed seed derived from `seed`+`scenario_id`+`GENERATOR_VERSION`, never wall clock.
- Advisory-only: anomalies must never look like an attack; ground truth stays `normal`.
- Docstrings: Google style (PEP 257) on all public classes/methods/modules.
- No speculative TODOs; no bare `except:`. Public function signatures annotated; `from __future__ import annotations`.
- Shared contracts (`events.py`, `plant.py`, `plant_contract.md`, `architecture.md`, `context.md`): do NOT change; flag any intended change in the PR body (this plan changes none of them).
- Commit style: `feat(scope): imperative description`; branch per change.
- Verify gate before PR: ruff check, ruff format --check, pytest, `git diff --check`.
- `test_scenarios.py:113` asserts `ATTACK_SCENARIOS` equals exactly the four attack ids — Joseph's PR #11 adds `attack_baseline_*`; the pull may already update it. Verify after pull.

---

### Task 1: Sync `main` and baseline-check upstream changes

**Files:**
- Test: `tests/test_scenarios.py` (verify only), `src/safeco/scenarios.py` (verify only), `src/safeco/simulator.py` (verify only)

**Interfaces:**
- Consumes: current `origin/main` (3 commits behind, fast-forward).
- Produces: a clean `main` at `334293c` with Joseph's `evaluation.py`, `baseline.py`, `docs/detector_evaluation.md`, and updated `scenarios.py` (incl. `force_mode_command` on `PlantSimulator`, refactored `grid_recovery_steps`, new `attack_baseline_*`).

- [ ] **Step 1:** Confirm no local uncommitted work that conflicts (the only untracked dirs are `docs/superpowers/` and `src/safeco.egg-info/` — safe).
  ```bash
  git status --short
  ```
- [ ] **Step 2:** Fast-forward main.
  ```bash
  git fetch origin && git pull --ff-only origin main
  ```
  Expected: fast-forward to `334293c`.
- [ ] **Step 3:** Run the full suite to confirm upstream is green.
  ```bash
  PYTHONPATH=src .venv/bin/python -m pytest -q
  ```
  Expected: full suite passes. Inspect the updated `test_scenarios.py:113` attack-set assertion (fixed by Joseph's PR) so Task 4 keeps the pattern intact.
- [ ] **Step 4:** Create and switch to the feature branch.
  ```bash
  git checkout -b feature/benign-anomalies-realism
  ```

---

### Task 2: Anomaly model + executor plumbing

**Files:**
- Modify: `src/safeco/scenarios.py` (add anomaly types near line 43; extend run_scenario/_execute at 115-188)
- Test: `tests/test_anomalies.py` (create)

**Interfaces:**
- Consumes: existing `Step = tuple[str, float, Callable[[PlantSimulator], None] | None]`, `_execute(...)` signature, `scenario_fingerprint`, `run_scenario`.
- Produces:
  - `Anomaly = tuple[str, str, dict]` where element 0 is a step-`phase` prefix to match, element 1 is a kind in `{"sensor_spike", "duration_jitter", "setpoint_nudge"}`, element 2 is params.
  - `AnomalyPlan = list[Anomaly]` (type alias).
  - `_execute(..., anomaly_plan: AnomalyPlan | None = None)` — returns `ScenarioResult`; default `None` keeps existing paths byte-identical.
  - `run_scenario(..., anomaly_plan: AnomalyPlan | None = None)` — forwards to `_execute`.

- [ ] **Step 1: Write the failing test** for a no-op anomaly plan:
```python
from safeco.scenarios import (NORMAL_SCENARIOS, run_scenario, scenario_fingerprint)

def test_empty_anomaly_plan_preserves_base_snapshots():
    NORMAL_SCENARIOS["_anom_demo"] = lambda: [("only_phase", 2.0, None)]
    base = run_scenario("_anom_demo", seed=42)
    anom = run_scenario("_anom_demo", seed=42, anomaly_plan=[])
    del NORMAL_SCENARIOS["_anom_demo"]
    assert scenario_fingerprint(base) == scenario_fingerprint(anom)
```
- [ ] **Step 2:** Run test — expected FAIL (no `anomaly_plan` kwarg yet).
- [ ] **Step 3:** Implement `Anomaly`, `AnomalyPlan`, thread `anomaly_plan` through `run_scenario` → `_execute`, defaulting to `None`. Immediately after computing the base snapshot dict, apply anomaly perturbations; for this task a stub that returns snapshots unchanged when plan is empty. Wire the anomaly-kind dispatch calls (helpers added in Tasks 3-4).
- [ ] **Step 4:** Run test — PASS.
- [ ] **Step 5:** Commit `feat(scenarios): thread anomaly plans through scenario executor`.

---

### Task 3: Sensor-spike / duty-jitter anomaly kinds

**Files:**
- Modify: `src/safeco/scenarios.py`
- Test: `tests/test_anomalies.py`

**Interfaces:**
- Consumes: `AnomalyPlan`, `_execute`, `scenario_fingerprint`, `PlantSimulator.snapshot()`.
- Produces:
  - `_anomaly_rng(seed: int, scenario_id: str) -> random.Random` — `Random(f"{seed}:{scenario_id}:{GENERATOR_VERSION}")`.
  - `_apply_duration_jitter(seconds: float, params: dict, rng: random.Random) -> float` — `seconds * (1 + fraction * (2*rng.random() - 1))`.
  - Sensor-spike handling inside `_execute`: for a matched step, set `observed["tank_level"]`/`["flow_rate"]` += magnitude in a copy, for `holds` steps.

- [ ] **Step 1:** Write failing tests:
```python
def test_sensor_spike_perturbs_observed_only_and_restores():
    # 3-step scenario; middle step has a spike on tank_level magnitude 5.0, holds 1
    # assert observed snapshot tank_level differs by ~5 while true final level unchanged
def test_duration_jitter_deterministic_and_bounded():
    # two runs same seed equal; deviation within [-fraction, +fraction] of seconds
def test_sensor_spike_invariant_safe():
    # all violations == []
```
- [ ] **Step 2:** Run — FAIL (helpers missing).
- [ ] **Step 3:** Implement helpers and wire into `_execute` (jitter before `sim.step`, spike on observed copy).
- [ ] **Step 4:** Run — PASS.
- [ ] **Step 5:** Commit `feat(scenarios): add sensor-spike and duration-jitter anomaly kinds`.

---

### Task 4: Setpoint-nudge kind + register the three benign scenarios

**Files:**
- Modify: `src/safeco/scenarios.py`
- Test: `tests/test_anomalies.py`

**Interfaces:**
- Consumes: `_execute`, `AnomalyPlan`, `_configure_running`, `Register`, `run_scenario`.
- Produces: three scenarios in `NORMAL_SCENARIOS`:
  - `benign_spike_01`
  - `benign_duty_jitter_01`
  - `benign_setpoint_nudge_01`
- And `ANOMALY_PLANS: dict[str, AnomalyPlan]`.
- Setpoint-nudge handling: for a matched step, add `params["delta"]` to `observed["target_level"]` in the copy for `holds` steps.

- [ ] **Step 1:** Write failing tests for the three scenarios: ground truth `normal`, zero violations, `target_level` restored to `70.0` (nudge self-restores), and they're in `NORMAL_SCENARIOS`.
- [ ] **Step 2:** Run — FAIL (scenarios missing).
- [ ] **Step 3:** Implement. `benign_spike_01`: `_configure_running` then short steady block with `sensor_spike` on `tank_level`. `benign_duty_jitter_01`: steady-running demand with `duration_jitter` on demand phases. `benign_setpoint_nudge_01`: RUNNING-mode `TARGET_LEVEL` bump `+delta` then restore via `setpoint_nudge`, staying below `HIGH_LEVEL_LIMIT`.
- [ ] **Step 4:** Run — PASS. Confirm the parametrized determinism test covers the three (they're in `NORMAL_SCENARIOS`).
- [ ] **Step 5:** Commit `feat(scenarios): add benign anomaly scenarios with normal ground truth`.

---

### Task 5: Provenance bump + fingerprint determinism

**Files:**
- Modify: `src/safeco/scenarios.py:28` (`GENERATOR_VERSION`)
- Test: `tests/test_anomalies.py`

**Interfaces:**
- Consumes: `scenario_fingerprint`, existing scenarios.
- Produces: `GENERATOR_VERSION = "safeco-scenarios/1.2"`.

- [ ] **Step 1:** Write failing test asserting `scenario_fingerprint` identical across two same-seed runs of each benign scenario, differs by seed, and `GENERATOR_VERSION == "safeco-scenarios/1.2"`.
- [ ] **Step 2:** Run — FAIL (version still 1.1).
- [ ] **Step 3:** Bump `GENERATOR_VERSION`.
- [ ] **Step 4:** Run — PASS.
- [ ] **Step 5:** Commit `feat(scenarios): bump generator version to 1.2 for benign anomalies`.

---

### Task 6: Process-realism evidence module (`realism.py`)

**Files:**
- Create: `src/safeco/realism.py`
- Test: `tests/test_realism.py` (create)

**Interfaces:**
- Consumes: all normal + benign scenarios via `run_scenario`, `ScenarioResult`.
- Produces:
  - `@dataclass RealismReport` with `scenario_id: str`, `ok: bool`, `checks: list[tuple[str, bool, str]]`.
  - `check_process_realism(scenario_id: str, seed: int = 42) -> RealismReport`.
  - Checks: level within documented bounds; `flow_rate == inflow - outflow` (recomputed from state) per step; valve/pump state consistency; bounded slew between consecutive `tank_level`s; zero violations for benign scenarios.

- [ ] **Step 1:** Write failing tests: `check_process_realism("startup_01").ok is True`, `"flow_balance"` check present, level-bounds check present, deterministic across runs.
- [ ] **Step 2:** Run — FAIL (module missing).
- [ ] **Step 3:** Implement `realism.py` per interfaces.
- [ ] **Step 4:** Run — PASS.
- [ ] **Step 5:** Commit `feat(realism): add process-realism assertion and evidence module`.

---

### Task 7: Docs evidence + ONBOARDING phase table

**Files:**
- Modify: `TECHNICAL_REPORT_NOTES.md`, `docs/ONBOARDING.md` (phase table + Available Scenarios rows).

**Interfaces:**
- Consumes: `RealismReport` output, scenario CLI.

- [ ] **Step 1:** Capture evidence via CLI:
  ```bash
  PYTHONPATH=src .venv/bin/python -m safeco.scenarios benign_spike_01 --seed 42 --fingerprint
  PYTHONPATH=src .venv/bin/python -m safeco.scenarios benign_duty_jitter_01 --seed 42 --fingerprint
  PYTHONPATH=src .venv/bin/python -m safeco.scenarios benign_setpoint_nudge_01 --seed 42 --fingerprint
  ```
- [ ] **Step 2:** Append the date-stamped realism evidence to `TECHNICAL_REPORT_NOTES.md`; update `ONBOARDING.md` phase table + scenario rows.
- [ ] **Step 3:** Commit `docs: record benign-anomaly process-realism evidence`.

---

### Task 8: Full verification gate

**Files:** none (verification only)

- [ ] **Step 1:** Run all four gates:
  ```bash
  .venv/bin/ruff check src tests
  .venv/bin/ruff format --check src tests
  PYTHONPATH=src .venv/bin/python -m pytest -q
  git diff --check
  ```
  Expected: all pass.
- [ ] **Step 2:** Smoke-test CLI fingerprint for a new benign scenario (matches `scenario_fingerprint`).
- [ ] **Step 3:** Final review of diff scope: only `scenarios.py`, `realism.py`, `test_anomalies.py`, `test_realism.py`, and the two doc files.
- [ ] **Step 4:** Commit any residual fixes if not green.
