# SafeCO Team Meeting Draft

## 1. Opening

“Thanks everyone. The purpose of this meeting is to align on exactly what we are building, who owns each part, how the components connect, and what we must complete next. Our priority is a working, explainable prototype, not unnecessary complexity.”

## 2. Product summary

We are building **SafeCO**, an advisory cybersecurity monitor for **Adupe Municipal Water Station**, a fictional Nigerian municipal water-pumping facility.

SafeCO monitors a simulated industrial process over **Modbus TCP** and detects commands that are technically valid but unsafe in the current process context.

The key idea is:

> A command may be valid, but the situation may make it dangerous.

SafeCO will detect command injection, replayed commands, valid commands issued at the wrong time, and gradual unsafe setpoint drift. It will explain and escalate the problem to an engineer, but it will not independently block, reverse, delay, or issue a plant-control command.

## 3. What the judges must see

The final demonstration should show:

1. Normal water-station operation.
2. Grid power failure.
3. Generator/recovery mode.
4. Legitimate restart accepted.
5. Legitimate maintenance accepted.
6. A valid malicious or replayed command.
7. The same command becoming unsafe because the plant state changed.
8. SafeCO detecting the contextual mismatch.
9. A plain-language dashboard alert.
10. Detection continuing during internet loss.
11. Stored events remaining available after reconnection.
12. Honest performance results, including failures.

## 4. System architecture

```text
Mahoraga's simulator
        ↓
Modbus TCP
        ↓
Daniel’s collector and event store
        ↓
Joseph's detector
        ↓
Ebi's API and dashboard
        ↓
Engineer decision
```

The components must use the existing contracts:

- `src/safeco/events.py`
- `src/safeco/plant.py`
- `docs/plant_contract.md`
- `architecture.md`
- `context.md`
- `team_handoff.md`

Nobody should create a separate event format, register map, or alert structure without team agreement.

## 5. Responsibilities

### Daniel: backend, integration, and final write-up

Daniel owns the event collector, SQLite storage, hash-chain verification, runtime orchestration, event replay, integration testing, backend/API contracts, offline local storage behaviour, component integration, final technical write-up, and submission.

Immediate milestone:

> Receive a plant snapshot or command, convert it into a SafeCO event, store it, verify the chain, and make it available to the detector and dashboard.

### Mahoraga: simulator and scenarios

Mahoraga owns the virtual Adupe plant, containing:

- Tank
- Inlet pump
- Inlet valve
- Outlet valve
- Tank-level sensor
- Flow reading
- Target-level setpoint
- High-level limit
- Grid power
- Generator power
- Operating modes

Required normal scenarios:

- Startup
- Steady running
- Controlled shutdown
- Legitimate maintenance
- Grid outage
- Generator recovery

Required attack scenarios:

- Command injection
- Replay
- Valid command in an unsafe state
- Slow setpoint drift

The simulator must use the documented Modbus register addresses, be deterministic using a seed, emit reproducible process states, keep physical behaviour simple and explainable, and not silently change the agreed safety semantics.

### Joseph: detector and evaluation

Joseph owns the detection engine and evaluation.

Detection should be implemented in this order:

1. Safety invariants
2. Replay checks
3. Rate and drift checks
4. Simple statistical baseline, only if needed

Initial safety rules include:

- Pump running with inlet valve closed
- Pump running without power
- Tank above high-level limit
- Target level not below high-level limit
- Invalid generator recovery sequence

Every alert must include alert ID, event ID, severity, reason code, title, explanation, evidence, recommended action, confidence, and acknowledgement state.

Joseph must evaluate complete held-out scenarios and report precision, recall, false alerts per normal hour, detection latency, per-attack results, legitimate-maintenance false positives, missed attacks, and limitations.

### Ebi: API and dashboard

Ebi owns the presentation layer.

The dashboard should show tank level, safe operating range, pump state, inlet valve state, outlet valve state, power source, operating mode, recent events, alert queue, alert details, acknowledgement action, scenario controls, and local connection/degraded visibility status.

Recommended stack:

- FastAPI
- Server-rendered HTML
- CSS
- Minimal JavaScript
- SQLite backend
- WebSocket or short polling

The dashboard will run locally at `http://127.0.0.1:8000`.

A 3D simulator is not required. A clear 2D process view is sufficient. A 3D visual may only be considered after all required functionality is complete and tested.

## 6. Nigerian operating context

We are using Adupe as a fictional representative Nigerian facility. Relevant conditions include grid outages, generator transfers, weak or absent internet connectivity, small operations teams, shared control-room devices, legitimate maintenance activity, changing demand periods, and the need for local operation.

Important accuracy rule:

> Internet loss is different from local control-network loss.

SafeCO should continue local collection and detection when the internet is unavailable. If it cannot receive local Modbus traffic, it must report degraded visibility rather than pretending it detected unseen commands.

## 7. Technology decisions

We will use Python, `pymodbus`, FastAPI, SQLite, HTML/CSS/JavaScript, `pytest`, and optionally Wireshark for showing Modbus traffic.

We are not building a real SCADA system, a connection to real infrastructure, a cloud platform, blockchain, an autonomous shutdown controller, a machine-learning-heavy system, or a 3D game/full digital twin.

## 8. Current project status

Completed:

- Track E scope
- Adupe context
- Architecture documents
- Team handoff document
- Plant-state model
- Modbus register contract
- Shared event contract
- SQLite event store
- Tamper-evident hash chain
- Event collector
- Deterministic sample runtime
- Automated tests

Current verification: **9 tests passing**.

Still required:

- Actual Modbus TCP simulator
- Normal and attack scenario runners
- Detector
- Alert storage/API
- Dashboard
- Offline/reconnect demonstration
- Evaluation metrics
- Final write-up
- Final submission package

## 9. Immediate milestone

The next shared milestone is:

> Start Adupe through Modbus, generate a normal plant event, store it in SQLite, pass it through the detector, and display the resulting process state in the dashboard.

The working path should become:

```text
Modbus command
→ Adupe plant state
→ EventCollector
→ SQLite
→ Detector
→ FastAPI
→ Dashboard alert
```

## 10. Collaboration rules

Every teammate should work on a separate branch, read the project documents before coding, keep changes within their ownership area, add tests with implementation changes, document interface changes, report known limitations honestly, and open a pull request instead of pushing unfinished work directly to `main`.

Every pull request must include what changed, how to run it, tests run, interface changes, known limitations, and a screenshot or sample output where relevant.

## 11. Decisions to confirm

We should leave the meeting with agreement on:

1. The four assigned ownership areas.
2. The Modbus register contract.
3. The event and alert contracts.
4. The exact normal and attack scenarios.
5. The local dashboard approach.
6. The demo sequence.
7. The next milestone and deadline.
8. The branch and pull-request workflow.
9. Features explicitly out of scope.

## 12. Closing statement

“Our success will not come from having the most complicated model. It will come from demonstrating that SafeCO understands the difference between a valid command and a safe command. Every component must support that claim, remain explainable, work locally, and show honest results.”
