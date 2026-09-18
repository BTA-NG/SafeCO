# SafeCO — Track E Scope Alignment

Cross-reference of every ICSC 2026 Track E requirement against the SafeCO implementation.

---

## Challenge: E1 — Catching Unsafe Commands in Your Own Control System

### What to Build

| # | Challenge says... | We built... | Status |
|---|---|---|---|
| 1 | A working simulated process controlled over **Modbus TCP or MQTT**, showing normal running, start up, shut down and at least one legitimate maintenance activity | Water tank with pump, inlet/outlet valves over **Modbus TCP** (pymodbus). Scenarios: `startup_01`, `steady_running_01`, `controlled_shutdown_01`, `maintenance_01` | ✅ |
| 2 | Your own **attack scripts**: injecting a command, replaying old traffic, sending a valid command at the wrong moment, and slowly drifting a setpoint | `attack_injection_01`, `attack_replay_01`, `attack_mistimed_01`, `attack_drift_01` — each with a jitter variant to prove process-context detection | ✅ |
| 3 | Keep the code so your **data can be reproduced** | Deterministic seeds, generator versions (`GENERATOR_VERSION`), scenario fingerprints, seed-reproducible simulator | ✅ |
| 4 | A **detector**, tested on that data — catching the valid command that should not have been sent | 5-layer detector: (1) process safety invariants, (2) state transitions, (3) replay detection, (4) command rate / setpoint drift, (5) robust median/MAD baseline | ✅ |
| 5 | An **alert screen** that tells an engineer what happened, to which equipment, and why it matters, plus a clear statement of what your system does when it is unsure | Dashboard shows: severity, evidence, explanation, recommended action, confidence. Advisory-only design explicitly stated in README and code | ✅ |

### Things to Keep in Mind

| Challenge says... | We handle it... | Status |
|---|---|---|
| Assume the attacker can send **perfectly valid, well formatted** commands | All attack scenarios are protocol-valid Modbus writes | ✅ |
| **Keeping the plant running matters** more than keeping secrets. Blocking a genuine safety command can cause the accident you were trying to prevent | Advisory-only: never blocks, reverses, delays, or issues plant commands | ✅ |
| Normal traffic is very repetitive; **legitimate maintenance also looks unusual** | `maintenance_01` correctly accepted, 0 maintenance false positives | ✅ |
| The person reading alerts is **an engineer under pressure**, not a security specialist | Plain-language explanations, severity grading, confidence scores, recommended actions | ✅ |
| Your system **must not shut the process down by itself**. It advises. A human decides | Enforced in code, docs, README, and every API endpoint | ✅ |

### Rules That Apply to Every Track

| Rule | How we satisfy it |
|---|---|
| **No real personal data** | Fully synthetic — deterministic simulator generates all data |
| **Build something** | Working prototype: simulator, detector, API, dashboard |
| **A prototype is enough** | 292 tests, full evaluation with precision/recall metrics |
| **Spend nothing** | Python, pymodbus, FastAPI, SQLite — all free and open source |
| **Explain results honestly** | Known limitations documented: true-vs-observed state gap, train/serve mismatch |
| **Think about power and network cuts** | Grid outage + generator recovery scenario (`grid_recovery_01`); degraded-visibility banner in dashboard |

### Nigerian Operating Context

| Context item | How we address it |
|---|---|
| Grid outages are normal | `grid_recovery_01` — legitimate recovery, not an attack |
| Small operations team, shared device | Single-user dashboard, local-first, no cloud dependency |
| Morning/evening demand changes | Demand changes accepted as normal operating events |
| Advisory-only matters | Incorrect automatic block could interrupt water service |

---

## Evaluation Results (seed 42, with baseline)

| Metric | Value |
|---|---|
| **Precision** | 1.000 |
| **Recall** | 1.000 |
| **False alerts / normal hour** | 0.000 |
| **Maintenance false positives** | 0 |
| **Total scenarios** | 21 (10 normal, 7 attack, 4 jitter) |
| **Classification** | TP=11, FP=0, TN=10, FN=0 |

### Detection by attack type

| Attack | Detected | Latency | Alert |
|---|---|---|---|
| Injection | ✅ | 0s | `unsafe_pump_start` |
| Injection (jitter) | ✅ | 0s | `unsafe_pump_start` |
| Replay | ✅ | 5s | `command_replay` |
| Replay (jitter) | ✅ | 5.43s | `command_replay` |
| Mistimed | ✅ | 3s | `recovery_out_of_sequence` |
| Mistimed (jitter) | ✅ | 2.73s | `recovery_out_of_sequence` |
| Drift | ✅ | 16s | `setpoint_drift` |
| Drift (jitter) | ✅ | 15.68s | `setpoint_drift` |
| Baseline (high limit) | ✅ | 1s | `baseline_deviation` |
| Baseline (low tank) | ✅ | 1s | `baseline_deviation` |
| Baseline (mode context) | ✅ | 1s | `baseline_deviation` |

### Normal scenarios — all correctly accepted (no alerts)

`startup_01`, `steady_running_01`, `controlled_shutdown_01`, `grid_recovery_01`, `maintenance_01`, `extended_normal_01`, `benign_noise_01`, `benign_spike_01`, `benign_duty_jitter_01`, `benign_setpoint_nudge_01`

---

## Dashboard Screenshots (required for 4-page report)

1. **Plant state** — tank with animated waves, Target (70%) and Limit (90%) markers
2. **Alerts** — attack alert with severity, evidence, explanation, recommended action
3. **Scenarios** — scenario selector with seed input and run button
4. **System health** — feed status, event count, hash chain integrity

---

## Known Limitations (documented honestly)

1. **True vs observed state**: Dashboard runner builds events from simulator's true state, not observed telemetry snapshots. Benign anomaly scenarios that perturb only the observed layer will not show perturbed values in the dashboard event history.
2. **Train/serve mismatch**: Baseline trains on observed features, dashboard feeds true-state features. No false positives resulted from this, but the feature distribution gap is noted.
3. **Advisory only**: Acknowledgement is record-only and never changes plant state.
4. **Results are synthetic**: Scenario-based, not production performance claims.

---

**Conclusion: Every Track E requirement is fully covered. No gaps identified.**
