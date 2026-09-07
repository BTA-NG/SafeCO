# SafeCO Onboarding Guide

> **For:** New contributors and teammates who need to understand the codebase without reading every file.
> **Last updated:** 25 Aug 2026

## What SafeCO Is

SafeCO is an **advisory monitor for unsafe commands in a simulated industrial control system (ICS/SCADA)**. It was built for ICSC 2026 Track E (hackathon). The system simulates a Nigerian municipal water treatment plant (the "Adupe Municipal Water Station"), observes Modbus TCP commands applied to it, and flags unsafe-but-protocol-valid operations — never blocking them, only recording and advising.

**Core principle:** SafeCO observes and advises. The simulator still applies valid protocol commands so their consequences can be demonstrated.

## Architecture at a Glance

```
┌─────────────────────────────────────────────────────┐
│                   Modbus TCP Client                  │
│            (test script, attack tool, etc.)          │
└──────────────────────┬──────────────────────────────┘
                       │ writes coils / holding registers
                       ▼
┌─────────────────────────────────────────────────────┐
│              ModbusPlantServer                        │
│         (modbus_server.py — localhost TCP)           │
│   Watches writes → validates via simulator → stores  │
└──────────────────────┬──────────────────────────────┘
                       │ apply_coil / apply_holding
                       ▼
┌─────────────────────────────────────────────────────┐
│               PlantSimulator                         │
│            (simulator.py — core engine)              │
│   Enforces register contract, records commands,      │
│   advances physics, emits snapshots                  │
└──────────┬──────────────────────────┬───────────────┘
           │ on_command callback      │ step() → state
           ▼                          ▼
┌──────────────────────┐  ┌───────────────────────────┐
│    EventCollector     │  │       PlantState           │
│  (collector.py)       │  │     (plant.py — data)      │
│  Builds Event objects │  │  tank, valves, pump, mode  │
└──────────┬───────────┘  └───────────────────────────┘
           │ append()
           ▼
┌──────────────────────┐
│     EventStore        │
│  (storage.py — SQLite)│
│  SHA-256 hash chain   │
└──────────────────────┘
```

## Source Map — What Each File Does

### Core Domain (`src/safeco/`)

| File | Purpose | Key types |
|------|---------|-----------|
| `plant.py` | **Data model.** Defines the plant's physical state, register map, operating modes, and validation rules. Pure data — no logic beyond `validate()` and `tick()`. | `PlantState`, `OperatingMode`, `PowerSource`, `Register` |
| `events.py` | **Event contract.** Defines what an "event" looks like when persisted. Frozen dataclasses — the shared language between simulator, collector, and storage. | `Event`, `ProcessSnapshot` |
| `simulator.py` | **Core engine.** Applies Modbus commands to `PlantState`, enforces the register contract, records every command, advances physics on `step()`, and emits telemetry snapshots. | `PlantSimulator`, `CommandRecord`, `ProtocolError` |
| `collector.py` | **Bridge.** Translates simulator outputs (`CommandRecord`, `PlantState`) into `Event` objects and appends them to the store. | `EventCollector` |
| `storage.py` | **Persistence.** SQLite event store with a tamper-evident SHA-256 hash chain. Append-only. | `EventStore` |
| `runtime.py` | **Integration runner.** Wires simulator → collector → storage for demo/test runs. CLI entry point. | `run_sample()`, `run_simulator_sample()`, `main()` |
| `modbus_server.py` | **Network adapter.** Exposes the simulator as a standard Modbus TCP server on localhost. Validates writes *before* storing them in pymodbus. | `ModbusPlantServer`, `WatchedBlock` |
| `scenarios.py` | **Scenario library.** Pre-built deterministic test sequences (startup, shutdown, maintenance, extended normal). CLI runner. | `run_scenario()`, `ScenarioResult`, step factories |

### Documentation (`docs/`)

| File | Purpose |
|------|---------|
| `plant_contract.md` | Register map, safety semantics, scenario catalogue — the source of truth for the plant model |
| `ONBOARDING.md` | This file |
| `superpowers/` | Skill-related artifacts (ignore for SafeCO development) |

### Tests (`tests/`)

| File | What it tests |
|------|---------------|
| `test_simulator.py` | Simulator register contract, physics, command recording, ProtocolError |
| `test_scenarios.py` | All 6 normal scenarios, ground truth, fingerprint, CLI |
| `test_modbus_server.py` | Modbus TCP server wiring, rejected writes, tick/read |
| `test_storage.py` | EventStore append, hash chain, verify |
| `test_backend_integration.py` | End-to-end: simulator → collector → storage |

## Key Concepts

### 1. Register Map

The plant is controlled via Modbus registers (like a real SCADA system):

- **Coils** (addresses 0–2): Digital on/off commands — pump, inlet valve, outlet valve
- **Input registers** (addresses 100–106): Read-only telemetry — tank level, flow rate, states
- **Holding registers** (addresses 200–202): Read/write parameters — target level, high-level limit, mode command

### 2. Operating Modes

```
SHUTDOWN → STARTUP → RUNNING → MAINTENANCE → RUNNING
                                  ↓
                               RECOVERY (grid loss)
                                  ↓
                              STARTUP → RUNNING
```

- `SHUTDOWN` (0): Everything off
- `STARTUP` (1): Inlet open, preparing to run
- `RUNNING` (2): Normal operation
- `MAINTENANCE` (3): Authorised setpoint changes allowed
- `RECOVERY` (4): Grid loss — pump stopped, awaiting generator transfer

### 3. Advisory-Only Semantics

SafeCO **never blocks** unsafe commands. If you write a pump-on command while the inlet valve is closed, the simulator applies it and records the violation. This is intentional — the system demonstrates consequences so humans can see what goes wrong.

Violations are detected by `PlantState.validate()` and checked after every `step()`.

### 4. Deterministic Scenarios

Every scenario runs with a fixed seed. The same seed always produces the same commands, snapshots, and violations. This is critical for the competition — judges can reproduce any result exactly.

```python
from safeco.scenarios import run_scenario
result = run_scenario("startup_01", seed=42)
print(result.violations)  # always empty for normal scenarios
```

### 5. Tamper-Evident Hash Chain

Every event stored in SQLite is linked to the previous event's SHA-256 hash. This creates an append-only chain — modifying any past event breaks the chain, which `verify_chain()` detects.

## Data Flow — How a Command Travels

1. **Client writes** a coil or holding register via Modbus TCP
2. **`WatchedBlock.setValues()`** intercepts the write and calls the callback
3. **`ModbusPlantServer._on_coil_write()`** calls `simulator.apply_coil()`
4. **`PlantSimulator.apply_coil()`** validates the address, resolves the target, records a `CommandRecord`, and updates `PlantState`
5. **`on_command` callback** fires, passing the `CommandRecord` to `EventCollector`
6. **`EventCollector.record_simulator_command()`** builds an `Event` with a `ProcessSnapshot` and appends it to `EventStore`
7. **`EventStore.append()`** chains the hash and inserts the row
8. **Next `step()`** advances physics and checks for violations

## How to Run

### Quick test
```bash
PYTHONPATH=src .venv/bin/python -m pytest -q
```

### Run a scenario
```bash
PYTHONPATH=src .venv/bin/python -m safeco.scenarios startup_01 --seed 42 --fingerprint
```

### Run the Modbus server
```python
from safeco.modbus_server import ModbusPlantServer
from safeco.simulator import PlantSimulator

sim = PlantSimulator(seed=42)
server = ModbusPlantServer(sim, port=5020)
server.start()
# Now connect with any Modbus client to localhost:5020
```

### Run the integration demo
```bash
PYTHONPATH=src .venv/bin/python -m safeco.runtime
```

## Available Scenarios

| ID | What happens | Duration | Violations |
|----|-------------|----------|------------|
| `startup_01` | SHUTDOWN → inlet open → pump on → RUNNING | ~3s | None |
| `steady_running_01` | 6 demand drain/fill duty cycles | ~121s | None |
| `controlled_shutdown_01` | pump off → inlet close → drain → SHUTDOWN | ~24s | None |
| `grid_recovery_01` | grid loss → generator transfer → RUNNING | ~15s | None |
| `maintenance_01` | 5× +1% target raises, 5× restores | ~50s | None |
| `extended_normal_01` | A/B/C demand blocks + outlet service | ~969s | None |
| `benign_spike_01` | transient +3% tank-level blip, self-restoring | ~12s | None |
| `benign_duty_jitter_01` | drain/fill durations jittered ±15% | ~61s | None |
| `benign_setpoint_nudge_01` | observed target-level +0.5% blip, restore | ~9s | None |

## Coding Standards

- **Formatter/linter:** ruff (`pyproject.toml`). Rule sets: E/W, F, I, N, B, D.
- **Line length:** 88 columns.
- **Naming:** PEP 8. One exemption: `setValues` (pymodbus API).
- **Typing:** Annotate public signatures. Use `from __future__ import annotations`.
- **Docstrings:** Google Python Style (PEP 257).
- **Errors:** Raise `ProtocolError` with actionable messages. Never bare `except:`.
- **Determinism:** Seed-reproducible. Record generator version.
- **Comments:** Explain why, not what.

### Before every commit
```bash
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
PYTHONPATH=src .venv/bin/python -m pytest -q
git diff --check
```

## Git Workflow

- Branch per change: `feature/<name>`, `fix/<name>`, `docs/<name>`
- Commit style: `feat(scope): imperative description`
- Open PRs into `main`. Daniel reviews shared contracts.
- Do not commit: `.venv`, SQLite DBs, caches, credentials.

## Shared Contracts (Do Not Change Without Discussion)

These files define the system's shared interface. Changes require Daniel's review:

- `src/safeco/plant.py` — register map, operating modes, validation
- `src/safeco/events.py` — event contract
- `docs/plant_contract.md` — register map documentation
- `architecture.md` — system architecture
- `context.md` — project mission and decisions

## Where to Start

1. **Read** `docs/plant_contract.md` — understand the plant model
2. **Read** `src/safeco/plant.py` — see the data model in code
3. **Read** `src/safeco/simulator.py` — understand how commands are applied
4. **Run** `PYTHONPATH=src .venv/bin/python -m safeco.scenarios startup_01 --seed 42` — see it in action
5. **Read** `src/safeco/modbus_server.py` — see how it exposes over Modbus TCP
6. **Run** the test suite — verify everything works

## Project Phases

| # | Phase | Status |
|---|-------|--------|
| 1 | Foundation (simulator + 4 normal scenarios) | ✅ Done |
| 2 | Normal plant & data (maintenance, extended normal, CLI, fingerprints) | ✅ Done |
| 3 | Attacks (injection, replay, mistimed valid, slow drift) | ✅ Done |
| 4 | Detector support (process realism validation) | ⬜ 1–7 Sep (benign anomalies + realism evidence) |
| 5 | Hardening (attack timing variation, telemetry noise) | ⬜ 8–14 Sep |
| 6 | Submission (4-page report, architecture figures, demo) | ⬜ 15–20 Sep |
