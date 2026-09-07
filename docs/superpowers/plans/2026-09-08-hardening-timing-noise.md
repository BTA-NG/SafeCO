# Attack Timing Variation & Telemetry Noise Implementation Plan

> **For agentic workers:** Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement task-by-task. Steps use `- [ ]` syntax.

**Goal:** Harden the SafeCO scenario library for Phase 5: realistic bounded telemetry noise on observed data, and deterministic attack-timing variation so detection must lean on process context rather than fixed clock offsets. Keep every trace seed-reproducible and invariant-safe.

**Architecture:** Reuse the Phase 4 observed-vs-true split. A new `telemetry_noise` anomaly kind perturbs observed snapshot telemetry (gaussian, 3σ-bounded) while leaving the true `PlantState` untouched. Attack builders become parametrized factories whose timing jitter is a deterministic function of the seed; variants register in a new `ATTACK_JITTER_SCENARIOS` registry separate from `ATTACK_SCENARIOS` so Joseph's exact-set assertion and eval id→reason mapping stay valid until he opts in. Provenance bumps to `safeco-scenarios/1.3`.

**Tech Stack:** Python 3, ruff, pytest, built-in `random`/`hashlib` (no new deps).

**Branch:** `feature/hardening-timing-noise` (per CONTRIBUTING.md `feature/<short-description>`)

## Global Constraints (from AGENTS.md / context.md)

- Line length 88; ruff rule sets E/W, F, I, N, B, D. Run `.venv/bin/ruff check src tests` and `.venv/bin/ruff format --check src tests`.
- Deterministic: seed-reproducible, retain `GENERATOR_VERSION`; no wall-clock dependence. New `random.Random(...)` uses `seed`+`scenario_id`+`GENERATOR_VERSION`, never wall clock.
- Advisory-only: telemetry noise never looks like an attack; ground truth stays `normal` for noisy benign scenarios, `attack` for jitter variants.
- Docstrings: Google style (PEP 257) on all public classes/methods/modules. No speculative TODOs; no bare `except:`. Public signatures annotated; `from __future__ import annotations`.
- Shared contracts (`events.py`, `plant.py`, `plant_contract.md`, `architecture.md`, `context.md`): do NOT change. `collector.py` event snapshots stay noise-free — the eval wiring that maps observed series onto `Event.process` is Joseph's handoff (Task 5 documents the seam; no eval code is touched here).
- Commit style: `feat(scope): imperative description`; branch per change.
- Verify gate before PR: ruff check, ruff format --check, pytest, `git diff --check`.

---

### Task 1: Sync `main`, write plan doc, create branch, baseline gate

**Files:**
- Create: this plan doc.
- Verify only: none.

**Interfaces:**
- Consumes: `origin/main` (post PR #15/#13). Fast-forward expected.

- [ ] **Step 1:** Fast-forward `main` and confirm no local uncommitted work conflicts (the two untracked dirs `docs/superpowers/plans/2026-08-22-*.md` and `src/safeco.egg-info/` are safe).
  ```bash
  git status --short
  git pull --ff-only origin main
  ```
- [ ] **Step 2:** Create branch:
  ```bash
  git switch -c feature/hardening-timing-noise
  ```
- [ ] **Step 3:** Baseline gate (full suite; evaluation takes ~10 min).

---

### Task 2: Bounded telemetry noise on observed snapshots

**Files:**
- Modify: `src/safeco/scenarios.py`, `src/safeco/realism.py`
- Test: `tests/test_anomalies.py` (or new `tests/test_noise.py`), `tests/test_realism.py`

**Interfaces:**
- Consumes: `_perturbed_observed` pipeline from Phase 4, `NORMAL_SCENARIOS`, `realism.py` check list.
- Produces:
  - `TELEMETRY_NOISE = "telemetry_noise"` kind constant.
  - `_apply_telemetry_noise(snapshot: dict, params: dict, rng: random.Random) -> dict`.
  - `benign_noise_01` in `NORMAL_SCENARIOS` (steady-running + bounded noise plan, ground truth `normal`), registered in `ANOMALY_PLANS`.
  - `realism._check_bounded_noise`.

- [ ] **Step 1:** Failing tests: `benign_noise_01` registered/normal/invariant-free/deterministic; observed differs from true by ≤ 3σ per sample with zero bulk drift; `realism.check_process_realism("benign_noise_01").ok`.
- [ ] **Step 2:** Run — FAIL (no kind/scenario/check yet).
- [ ] **Step 3:** Implement `TELEMETRY_NOISE` + `_apply_telemetry_noise` (clamped to physical range; `tank_level` and `flow_rate` only; gaussian via the scenario rng; per-sample |noise| ≤ 3 * scale).
- [ ] **Step 4:** Register `benign_noise_01` (steady-running duty cycles, noise scale ≈ 0.5 of a percent reading).
- [ ] **Step 5:** Add `realism._check_bounded_noise`; wire into `check_process_realism` for noisy benign scenarios.
- [ ] **Step 6:** Run — PASS.
- [ ] **Step 7:** Commit `feat(scenarios): add bounded telemetry-noise anomaly and benign_noise_01`.

---

### Task 3: Attack timing-jitter variants (split registry)

**Files:**
- Modify: `src/safeco/scenarios.py`
- Test: `tests/test_scenarios.py`, `tests/test_anomalies.py`

**Interfaces:**
- Consumes: existing attack step factories, `run_scenario`, `_execute`, `ScenarioResult`.
- Produces:
  - `ATTACK_JITTER_SCENARIOS: dict[str, Callable[[], list[Step]]]` (separate registry, ground truth `attack`).
  - Parametrized builders: `attack_injection_steps(timing_jitter: float = 0.0, seed_key: str | None = None)`, same for replay/mistimed/drift.
  - Four registered variants: `attack_injection_jitter_01`, `attack_replay_jitter_01`, `attack_mistimed_jitter_01`, `attack_drift_jitter_01`.
  - `run_scenario` name lookup extended to include `ATTACK_JITTER_SCENARIOS`.

- [ ] **Step 1:** Failing tests: variants present in the split registry, ground truth `attack`, deterministic from seed (jitter is a function of the seed), differ from the base attack fingerprint, and invariant-violation set stays the same as the base (jitter never masks the unsafe condition). `run_scenario` resolves them; determinism parametrization in `test_scenarios.py` extended to the new ids.
- [ ] **Step 2:** Run — FAIL (no registry/builders).
- [ ] **Step 3:** Implement jitter builders. Jitter targets the *approach* phases (pre-attack wait/silence for injection/replay/mistimed; inter-raise cadence for drift) using `d = d0 * (1 + fraction * (2*rng.random() - 1))` with a seed-keyed rng. Fix the seeded rng per call so the variant is fully reproducible.
- [ ] **Step 4:** Register the four variants; extend `run_scenario` lookup (NORMAL ∪ ATTACK ∪ ATTACK_JITTER). Do NOT touch `ATTACK_SCENARIOS`.
- [ ] **Step 5:** Run — PASS.
- [ ] **Step 6:** Commit `feat(scenarios): add deterministic attack timing-jitter variants`.

---

### Task 4: Provenance bump to 1.3

**Files:**
- Modify: `src/safeco/scenarios.py`
- Test: `tests/test_anomalies.py` (version assertion updated)

- [ ] **Step 1:** Update version regression test to expect `1.3`; run — FAIL.
- [ ] **Step 2:** Bump `GENERATOR_VERSION = "safeco-scenarios/1.3"`; run — PASS.
- [ ] **Step 3:** Commit `chore(scenarios): bump generator_version to 1.3`.

---

### Task 5: Evaluation handoff seam (no eval code touched)

**Files:**
- Modify: `src/safeco/scenarios.py`
- Test: `tests/test_anomalies.py`

**Interfaces:**
- Produces: `observed_state_snapshots(scenario_id, seed) -> list[dict]` — public helper returning the observed (anomaly/noise-perturbed) snapshot series for a scenario, identical to what `run_scenario().snapshots` produced with its registered plan.

- [ ] **Step 1:** Failing test: helper equals `run_scenario(...).snapshots` for a noisy/benign scenario and for a plain benign one.
- [ ] **Step 2:** Implement (thin wrapper over `run_scenario`), run — PASS.
- [ ] **Step 3:** Record the Joseph handoff note in `docs/ONBOARDING.md` and the PR body (map observed snapshots onto `Event.process` in `events_for_scenario`; `collector.py` event snapshots will then need the observed values — his call; Layer 5 baseline must retrain on the noisy benign envelope).
- [ ] **Step 4:** Commit `feat(scenarios): expose observed-state snapshots for evaluation handoff`.

---

### Task 6: Docs evidence + ONBOARDING

**Files:**
- Modify: `TECHNICAL_REPORT_NOTES.md`, `docs/ONBOARDING.md`

- [ ] **Step 1:** Capture seed-42 fingerprints via CLI for the five new scenarios (4 jitter + `benign_noise_01`).
- [ ] **Step 2:** Append date-stamped Phase 5 evidence to `TECHNICAL_REPORT_NOTES.md`; add `benign_noise_01` + jitter variants to ONBOARDING scenario table; flip Phase 5 to in progress.
- [ ] **Step 3:** Commit `docs: record hardening evidence (noise + timing jitter)`.

---

### Task 7: Full verification gate + PR

- [ ] **Step 1:** All four gates: ruff check, ruff format --check, full pytest, `git diff --check`.
- [ ] **Step 2:** Smoke-test CLI fingerprint for a jitter variant matches `scenario_fingerprint`.
- [ ] **Step 3:** Final diff-scope review: only `scenarios.py`, `realism.py`, test files, and the two doc files.
- [ ] **Step 4:** Push branch, open PR with Joseph/Daniel flags (no shared-contract changes; Joseph handoff + Layer-5 retrain note).