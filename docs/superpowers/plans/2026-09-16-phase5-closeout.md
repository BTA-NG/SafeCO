# Phase 5 Close-out Implementation Plan

> **For agentic workers:** Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement task-by-task. Steps use `- [ ]` syntax.

**Goal:** Close out Phase 5 (hardening: attack timing variation + telemetry
noise) on `main`. The scenario work shipped in PR #16; this pass verifies and,
if needed, completes the two recorded Joseph/Daniel evaluation follow-ups
(`TECHNICAL_REPORT_NOTES.md` lines 134-138, 154-156), syncs the evidence docs,
flips the ONBOARDING phase table to Done, and lands everything behind a review
PR with no shared-contract changes.

**Background:** `observed_state_snapshots` mapping onto `Event.process` already
lives in `evaluation.py` (`_process_at` + `on_snapshot`), and jitter variants
are already counted in `ATTACK_EVALUATION_SCENARIOS`/`EXPECTED_ATTACK_ALERTS`
(`30a85c4`, `ab3c2e7`). The one open technical question is whether Layer 5
needs retraining on the noisy benign envelope: `BASELINE_TRAINING_SCENARIOS`
is still `{startup_01, steady_running_01, maintenance_01}`, excluding
`benign_noise_01`. Task 2 below answers it empirically before touching training.

**Branch:** `fix/phase5-closeout` off `origin/main` (per CONTRIBUTING.md
`fix/<short-description>`).

## Global Constraints (from AGENTS.md / CONTRIBUTING.md)

- Line length 88; ruff rule sets E/W, F, I, N, B, D. Gates:
  `.venv/bin/ruff check src tests`, `.venv/bin/ruff format --check src tests`,
  `PYTHONPATH=src .venv/bin/python -m pytest -q`, `git diff --check`.
- Deterministic: seed-reproducible; no wall-clock dependence in
  simulator/scenario code paths.
- Advisory-only semantics unchanged; this pass never touches scenario bodies or
  the detector.
- Shared contracts (`events.py`, `plant.py`, `plant_contract.md`,
  `architecture.md`, `context.md`): do NOT change.
- Scope: only `evaluation.py`, `baseline.py`, their tests, plus evidence docs.
  Never `scenarios.py` bodies (fingerprints must not drift).
- Commit style: `fix(scope): imperative description`; `docs: ...` for evidence.

---

### Task 1: Branch + baseline gates

- [ ] **Step 1:** Sync and branch:
  ```bash
  git status --short
  git fetch origin && git switch -c fix/phase5-closeout origin/main
  ```
- [ ] **Step 2:** Baseline gates (ruff + format + diff-check):
  ```bash
  .venv/bin/ruff check src tests
  .venv/bin/ruff format --check src tests
  git diff --check
  ```

---

### Task 2: Eval gate decides Layer-5 retrain vs regression lock

**Files:** none yet (verification only).

- [ ] **Step 1:** Run the heavy eval test with a relaxed timeout
  (~10 min; CI preferred — it exceeds default tool timeouts locally):
  ```bash
  PYTHONPATH=src .venv/bin/python -m pytest \
      tests/test_evaluation.py::test_evaluation_report_computes_recall_and_precision -q
  ```
- [ ] **Step 2:** Branch on the result:
  - **PASS** (precision/recall == 1.0): the 3σ-clamped noise is absorbed by
    the clean-trained robust MAD ranges. No retrain. Go to Task 3A.
  - **FAIL** (`benign_noise_01` trips `baseline_deviation`): the noisy envelope
    needs training. Go to Task 3B.

---

### Task 3A: Clean path — lock in the noisy true negative (PASS only)

**Files:** modify `tests/test_evaluation.py`.

- [ ] **Step 1:** Add a regression test asserting `benign_noise_01` evaluates
  as a true negative under the baseline-enabled report, e.g. extend the
  `test_evaluation_report_computes_recall_and_precision` coverage or a new
  `test_benign_noise_has_no_baseline_false_positive`.
- [ ] **Step 2:** Run the new test — PASS (test-first: it must pass on the
  unchanged code, proving it is a lock-in, not a fix).
- [ ] **Step 3:** Commit `test(evaluation): lock in benign-noise true negative`.

### Task 3B: Fail path — Layer-5 noisy-envelope retrain (FAIL only)

**Files:** modify `src/safeco/evaluation.py`, test in
`tests/test_evaluation.py`.

- [ ] **Step 1:** Failing regression: `benign_noise_01` is a baseline false
  positive in the report.
- [ ] **Step 2:** Add `benign_noise_01` to the Layer-5 training envelope
  (extend `BASELINE_TRAINING_SCENARIOS` explicitly — do NOT widen to all of
  `NORMAL_SCENARIOS`, since validation/held-out leakage is forbidden), via
  `train_baseline_from_scenarios` defaults.
- [ ] **Step 3:** Re-run the full eval gate. `benign_noise_01` must be a true
  negative AND the three `attack_baseline_*` scenarios must still detect (no
  sensitivity loss from wider ranges). Recall must stay 1.0.
- [ ] **Step 4:** Commit `fix(evaluation): train Layer 5 on noisy benign envelope`.

---

### Task 4: Sync evidence docs

**Files:** modify `TECHNICAL_REPORT_NOTES.md`, `docs/ONBOARDING.md`,
`docs/detector_evaluation.md`.

- [ ] **Step 1:** `TECHNICAL_REPORT_NOTES.md:134-138` — resolve the
  "hooking `ANOMALY_PLANS` into `events_for_scenario`" follow-up: observed
  telemetry now flows through `_process_at` (`30a85c4`/`ab3c2e7`).
- [ ] **Step 2:** `TECHNICAL_REPORT_NOTES.md:154-156` — resolve the
  `observed_state_snapshots` → `Event.process` note the same way, and record
  the Task 2/3 Layer-5 decision and its outcome.
- [ ] **Step 3:** `docs/ONBOARDING.md:192-199` — same stale handoff text
  (`Event.process` is no longer "the denoised true state" for evaluation).
- [ ] **Step 4:** `docs/detector_evaluation.md` — drop the resolved
  known-limitation entry.
- [ ] **Step 5:** Re-confirm the five seed-42 noise/jitter fingerprints via
  CLI (`python -m safeco.scenarios <id> --seed 42 --fingerprint`) — traces must
  be unchanged since no scenario body was touched.
- [ ] **Step 6:** Commit `docs: resolve Phase 5 evaluation follow-ups in evidence`.

---

### Task 5: Flip the phase table

**Files:** modify `docs/ONBOARDING.md`.

- [ ] **Step 1:** Flip Phase 5 `⬜ 8–14 Sep (in progress)` → `✅ Done` with
  date + PR #16 ref.
- [ ] **Step 2:** Commit `docs: mark Phase 5 complete` (may fold into Task 4's
  commit).

---

### Task 6: Full gate + PR

- [ ] **Step 1:** All four gates: ruff check, ruff format --check, full
  `pytest` (evaluation ~10 min — run on CI or a patient shell), `git diff
  --check`.
- [ ] **Step 2:** On a normal laptop/CI, run the two live-Modbus bind tests
  that cannot bind localhost in restricted environments; record the result in
  `TECHNICAL_REPORT_NOTES.md`.
- [ ] **Step 3:** Diff-scope review: only `evaluation.py`, `baseline.py`, test
  files, and the three docs.
- [ ] **Step 4:** Push branch, open PR into `main` flagged for **Joseph**
  (detector/eval owner) and **Daniel** (evidence/report), noting the resolved
  follow-ups and no shared-contract changes.
