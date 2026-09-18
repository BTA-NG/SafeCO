# SafeCO Technical Report Notes

Source of truth for the ICSC 2026 technical report (maximum 4 pages).
Every claim below is tied to a file, test, command, or stored artifact.
Do not add unverified claims.

---

## What SafeCO is (one sentence)

SafeCO is a local-first monitor that watches commands sent to a simulated
water plant, detects the ones that are unsafe, explains why, and tells a
human — it never blocks or changes anything on its own.

---

## The problem we solve

Industrial control systems accept commands over protocols like Modbus. A
command can be perfectly valid according to the protocol (correct register,
correct value) but still dangerous given the current state of the plant.
For example: turning on a pump when the inlet valve is closed, or raising
the tank level above the safety limit.

SafeCO catches these "valid but unsafe" commands.

---

## The fictional plant: Adupe Municipal Water Station

- A water tank with an inlet valve, outlet valve, and pump.
- Registers follow the Modbus convention (read/write, 0x addresses).
- The plant has a target level (default 70%) and a high-level safety
  limit (default 90%).
- The simulator is deterministic: same seed = same commands = same result.
- Plant model: `src/safeco/plant.py`
- Register map: `docs/plant_contract.md`

---

## How it works (the pipeline)

```
Simulator  →  EventCollector  →  SQLite  →  Detector  →  Alerts
  (generates     (normalises      (stores      (checks     (advises
   commands)      into Event       with hash    rules +     the human)
                  contract)        chain)       baseline)
```

1. **Simulator** generates commands (open valve, start pump, etc.)
2. **Collector** wraps each command into a normalised Event record
3. **SQLite** stores every event with a SHA-256 hash chain (tamper evidence)
4. **Detector** evaluates each event against 5 layers of checks
5. **Alerts** are generated with severity, evidence, and recommendations
6. **Dashboard** shows everything to the operator in real time

---

## The 5 detection layers

| Layer | What it checks | Example |
|-------|---------------|---------|
| 1 | Protocol invariants | Pump on but inlet valve closed |
| 2 | State transitions | Mode change without proper sequence |
| 3 | Replay / sequence | Same command sent twice, or recovery out of order |
| 4 | Command rate | Too many commands too fast |
| 5 | Statistical baseline | Tank level deviates beyond learned normal range |

Layers 1-4 are deterministic rules. Layer 5 uses a median/MAD
statistical profile trained only from benign (normal) scenarios.

---

## What SafeCO detects (attack types)

| Attack | What happens | Expected alert |
|--------|-------------|----------------|
| Injection | Unsafe pump command injected | `unsafe_pump_start` |
| Replay | Old command re-sent | `command_replay` |
| Mistimed | Recovery command in wrong order | `recovery_out_of_sequence` |
| Drift | Target level gradually moved toward limit | `setpoint_drift` |
| Baseline | Process value outside learned normal range | `baseline_deviation` |

---

## Scenario categories

**Normal (no attack expected):**
- `startup_01` — system boots up
- `extended_normal_01` — ~969 seconds of normal operation
- `benign_noise_01` — normal operation with sensor noise
- `benign_spike_01` — brief tank-level blip, self-restoring
- `benign_duty_jitter_01` — drain/fill timing varies ±15%
- `benign_setpoint_nudge_01` — small target-level blip
- `maintenance_01` — maintenance mode with authorised changes

**Attack (alert expected):**
- `attack_injection_01` / `attack_injection_jitter_01`
- `attack_replay_01` / `attack_replay_jitter_01`
- `attack_mistimed_01` / `attack_mistimed_jitter_01`
- `attack_drift_01` / `attack_drift_jitter_01`
- `attack_baseline_low_tank_01`
- `attack_baseline_high_limit_01`
- `attack_baseline_mode_context_01`

The `_jitter_01` variants use the same attack commands but vary the
timing. This proves detection relies on process context, not fixed
clock offsets.

---

## Evaluation results

The evaluator (`src/safeco/evaluation.py`) replays scenarios through
the detector and reports precision, recall, and detection latency.

**Key results (seed 42):**

| Scenario | Events | Alerts | Expected alert |
|----------|--------|--------|----------------|
| `startup_01` | 3 | 0 | — |
| `benign_noise_01` | 10 | 0 | — |
| `attack_injection_01` | 1 | 1 | `unsafe_pump_start` |
| `attack_baseline_high_limit_01` | 5 | 1 | `baseline_deviation` |

Precision and recall are both 1.0 across the evaluated scenarios.
The baseline-only anomaly scenarios (`attack_baseline_*`) produce
alerts that rules alone would miss, demonstrating Layer 5's added
coverage.

**Important:** These are synthetic, scenario-based results. They
demonstrate reproducibility and detector behaviour, not operational
performance in a real plant.

---

## The operator dashboard

A vanilla HTML/CSS/JS dashboard (no build step, no framework) served
by the FastAPI backend at `/`.

**What it shows:**
- Plant state: mode, power, pump/valve states, target/limit levels
- Animated SVG tank with flowing water waves, Target and Limit markers
- Alerts: severity, evidence, confidence, recommendations, ack button
- Events: filterable by scenario, paginated, with full event details
- Scenarios: select, set seed, run, see results appear
- System health: feed status, event count, hash chain integrity

**How it updates:** 2-second HTTP polling (with SSE transport in progress
via a parallel PR). Refreshes immediately after scenario runs,
acknowledgement, filter changes, or manual button click.

**What it does NOT do:**
- Acknowledgement is record-only — it does not change plant state

**Dashboard screenshots needed for report:**
1. Plant state tab (showing tank with waves and markers)
2. Alerts tab (showing an attack alert with evidence)
3. Scenarios tab (showing scenario selector and run result)
4. System health tab (showing feed status and hash chain)

---

## Known limitations

- The dashboard runner builds events from the simulator's true state, not
  observed telemetry snapshots. Benign anomaly scenarios (noise, spikes,
  setpoint nudges) that perturb only the observed layer will not show the
  perturbed values in the dashboard event history. The evaluation CLI
  uses observed snapshots and may therefore differ.
- Alert acknowledgement is record-only and never changes plant state.
- The confirmed simulator-action concept is not implemented.
- Results are based on deterministic synthetic scenarios, not real plant data.

---

## What is NOT implemented (do not claim these)

- Autonomous shutdown or blocking of commands
- Engineer-confirmed simulator action (documented but not built)
- Real plant data or operational dataset
- Real Modbus adapter to physical hardware
- Electricity support or power-grid modelling

---

## Accuracy guardrails (read before writing the report)

1. Adupe is fictional. Never imply it is a real facility.
2. Modbus validity ≠ process safety. A valid Modbus write can still be unsafe.
3. The hash chain detects stored-event tampering, not fake sensors.
4. Internet loss ≠ loss of the local control feed. These are different.
5. Critical alerts recommend checks; a human decides what to do.
6. Baseline training uses ONLY benign tuning scenarios. Never imply
   validation or held-out scenarios were used for training.
7. All results are synthetic and scenario-based.

---

## Verification checklist (for the report)

Run from repo root:

```bash
.venv/bin/ruff check src tests          # Lint
.venv/bin/ruff format --check src tests # Format
PYTHONPATH=src .venv/bin/python -m pytest -q  # Tests
git diff --check                         # Whitespace
```

Current status: 277 tests passing, 28 third-party warnings
(Starlette/FastAPI deprecations under Python 3.14, not failures).

---

## Report structure (4 pages max)

1. **Problem & approach** — What SafeCO does, why it matters (1 paragraph)
2. **Architecture** — Simulator → Collector → SQLite → Detector → Alerts
3. **Detection** — 5 layers, baseline training, attack types
4. **Evaluation** — Scenarios, results, dashboard screenshots, limitations

Keep each section tight. Screenshots will take ~1 page. Text must fit
in ~3 pages.
