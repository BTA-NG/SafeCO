# SafeCO Technical Report Notes

Source of truth for the ICSC 2026 technical report (maximum 4 pages).
Every claim below is tied to a file, test, command, or stored artifact.
Do not add unverified claims.

---

## Executive Summary

SafeCO is a local-first, advisory cybersecurity monitor for industrial control systems. It detects commands that are protocol-valid but unsafe in the current process context — the kind of commands that Modbus would happily deliver, but that could cause real harm depending on what the plant is doing right now.

Built for the ICSC 2026 hackathon, SafeCO monitors **Adupe Municipal Water Station**, a fictional municipal water facility, through a deterministic Modbus TCP simulator.

---

## The Problem

Industrial control systems accept commands over protocols like Modbus. A command can be perfectly valid according to the protocol (correct register, correct value) but still dangerous given the current state of the plant. For example: turning on a pump when the inlet valve is closed, or raising the tank level above the safety limit.

SafeCO catches these "valid but unsafe" commands.

---

## Architecture

<p align="center">
  <img src="docs/architecture.png" alt="SafeCO Architecture" width="800" />
</p>

**Pipeline:**
```
Simulator → EventCollector → SQLite → Detector → Alerts → Dashboard
```

1. **Simulator** generates commands (open valve, start pump, etc.)
2. **Collector** wraps each command into a normalised Event record
3. **SQLite** stores every event with a SHA-256 hash chain (tamper evidence)
4. **Detector** evaluates each event against 5 layers of checks
5. **Alerts** are generated with severity, evidence, and recommendations
6. **Dashboard** shows everything to the operator in real time

---

## Detection Layers

| Layer | What it checks | Example |
|-------|---------------|---------|
| 1 | Protocol invariants | Pump on but inlet valve closed |
| 2 | State transitions | Mode change without proper sequence |
| 3 | Replay / sequence | Same command sent twice, or recovery out of order |
| 4 | Command rate | Too many commands too fast |
| 5 | Statistical baseline | Tank level deviates beyond learned normal range |

Layers 1-4 are deterministic rules. Layer 5 uses a median/MAD statistical profile trained only from benign (normal) scenarios.

---

## Attack Types

| Attack | What happens | Expected alert |
|--------|-------------|----------------|
| Injection | Unsafe pump command injected | `unsafe_pump_start` |
| Replay | Old command re-sent | `command_replay` |
| Mistimed | Recovery command in wrong order | `recovery_out_of_sequence` |
| Drift | Target level gradually moved toward limit | `setpoint_drift` |
| Baseline | Process value outside learned normal range | `baseline_deviation` |

---

## Evaluation Results

The evaluator (`src/safeco/evaluation.py`) replays scenarios through the detector and reports precision, recall, and detection latency.

**Key results (seed 42):**

| Scenario | Events | Alerts | Expected alert |
|----------|--------|--------|----------------|
| `startup_01` | 3 | 0 | — |
| `benign_noise_01` | 10 | 0 | — |
| `attack_injection_01` | 1 | 1 | `unsafe_pump_start` |
| `attack_baseline_high_limit_01` | 5 | 1 | `baseline_deviation` |

Precision and recall are both 1.0 across the evaluated scenarios. The baseline-only anomaly scenarios (`attack_baseline_*`) produce alerts that rules alone would miss, demonstrating Layer 5's added coverage.

**Important:** These are synthetic, scenario-based results. They demonstrate reproducibility and detector behaviour, not operational performance in a real plant.

---

## Dashboard

A vanilla HTML/CSS/JS dashboard (no build step, no framework) served by the FastAPI backend at `/`.

**Features:**
- Plant state: mode, power, pump/valve states, target/limit levels
- Animated SVG tank with flowing water waves, Target and Limit markers
- Alerts: severity, evidence, confidence, recommendations, ack button
- Events: filterable by scenario, paginated, with full event details
- Scenarios: select, set seed, run, see results appear
- System health: feed status, event count, hash chain integrity

**How it updates:** The server pushes a full payload over Server-Sent Events
(`GET /api/stream`) on connect and again whenever stored state changes, so a new
finding appears as it lands rather than up to a poll interval later. The browser
reconnects on its own if the stream drops. The Refresh button, and actions whose
result the operator is waiting on — a scenario run or an acknowledgement —
re-read the REST endpoints directly. View-only controls (the alert filters, the
alert-id search and the event scenario filter) re-render what is already on
screen rather than re-reading the feed.

---

## Known Limitations

- **True vs observed state**: The dashboard runner builds events from the simulator's true state, not observed telemetry snapshots. Benign anomaly scenarios (noise, spikes, setpoint nudges) that perturb only the observed layer will not show the perturbed values in the dashboard event history. The evaluation CLI uses observed snapshots and may therefore differ.
- **Train/serve mismatch**: `train_baseline_from_scenarios` trains on observed features, while the dashboard feeds the same profile true-state features. This feature distribution mismatch is noted but produced no alerts on either path.
- **Alert acknowledgement**: Record-only — never changes plant state.
- **Confirmed simulator-action**: Documented but not implemented.
- **Results**: Based on deterministic synthetic scenarios, not real plant data.

---

## What is NOT Implemented

- Autonomous shutdown or blocking of commands
- Engineer-confirmed simulator action (documented but not built)
- Real plant data or operational dataset
- Real Modbus adapter to physical hardware
- Electricity support or power-grid modelling

---

## Accuracy Guardrails

1. Adupe is fictional. Never imply it is a real facility.
2. Modbus validity ≠ process safety. A valid Modbus write can still be unsafe.
3. The hash chain detects stored-event tampering, not fake sensors.
4. Internet loss ≠ loss of the local control feed. These are different.
5. Critical alerts recommend checks; a human decides what to do.
6. Baseline training uses ONLY benign tuning scenarios. Never imply validation or held-out scenarios were used for training.
7. All results are synthetic and scenario-based.

---

## Verification

Run from repo root:

```bash
.venv/bin/ruff check src tests          # Lint
.venv/bin/ruff format --check src tests # Format
PYTHONPATH=src .venv/bin/python -m pytest -q  # Tests
git diff --check                         # Whitespace
```

Current status: 277 tests passing, 28 third-party warnings (Starlette/FastAPI deprecations under Python 3.14, not failures).

---

## Report Structure (4 pages max)

1. **Problem & approach** — What SafeCO does, why it matters (1 paragraph)
2. **Architecture** — Simulator → Collector → SQLite → Detector → Alerts
3. **Detection** — 5 layers, baseline training, attack types
4. **Evaluation** — Scenarios, results, dashboard screenshots, limitations

Keep each section tight. Screenshots will take ~1 page. Text must fit in ~3 pages.
