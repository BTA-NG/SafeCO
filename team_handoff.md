# SafeCO Team Handoff and Execution Plan

## Project

Track E — Catching Unsafe Commands in Your Own Control System.

Product: **SafeCO**, a local-first advisory monitor for **Adupe Municipal Water Station**, a fictional Nigerian municipal water-pumping system using Modbus TCP. It detects commands that are malformed, replayed, valid but unsafe in context, or gradually drifting into an unsafe range. It explains the alert; it does not automatically shut down the process.

This document is the working agreement for Daniel, Mahoraga, Ebi, and Joseph. Read it together with `architecture.md` and `context.md`. If a proposed feature conflicts with those files, stop and agree on a deliberate change before implementing it.

Repository workflow is defined in `CONTRIBUTING.md`. It covers branches, commits, pull requests, reviews, contracts, and local checks.

## Team ownership

| Person | Role | Primary ownership | Required handoff |
|---|---|---|---|
| Daniel | Backend, integrity, and integration engineer; team captain | Collector, SQLite storage, event hash-chain, runtime orchestration, integration, final demo, submission | Delivers working backend code and maintains decisions, risks, and release checklist |
| Mahoraga | OT simulator and scenarios engineer | Tank model, Modbus register map, normal operation, attack scripts, reproducible seeds | Documents register map, scenario steps, expected ground truth |
| Joseph | Detection and evaluation engineer | Layered detector, metrics, threshold tuning, held-out scenarios, error analysis | Publishes detector API, test fixtures, and evaluation report; consumes Daniel's event stream |
| Ebi | Platform/UI and documentation engineer | FastAPI, dashboard, offline behaviour, packaging, screenshots, API documentation | Maintains runbook, UI/API contract, and demo screen |

These assignments are defaults based on work boundaries, not assumptions about seniority. A person may help another owner, but each deliverable has one accountable owner.

## Teammate start guide

Before writing code, every teammate must read `context.md`, `architecture.md`, and `docs/plant_contract.md`, then run:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=src pytest -q
```

The expected starting result is seven passing tests. The product name is **SafeCO**; Python imports use `safeco`. Do not recreate the former package name.

### Daniel: backend and integration

Start from `src/safeco/events.py` and `src/safeco/storage.py`. Build a collector/runtime that converts commands and plant snapshots into `Event` records and appends them to `EventStore`. First handoff: one command produces and stores a normal Adupe telemetry event, verifies the chain, and can read it back. Do not implement autonomous command blocking.

### Mahoraga: simulator and scenarios

Start from `src/safeco/plant.py` and `docs/plant_contract.md`. Implement a deterministic Modbus TCP simulator using exactly the documented register addresses and encodings. First handoff: startup, steady running, controlled shutdown, and legitimate grid-to-generator recovery can run from a fixed seed and emit process snapshots. Do not rename registers or change safety semantics without team agreement.

Then add four separately reproducible attack scripts: command injection, replay, valid command in an unsafe state, and slow setpoint/high-limit drift. Each script must record scenario ID, seed, ground truth, command sequence, expected physical consequence, and known limitation.

### Joseph: detector and evaluation

Joseph consumes the `Event` contract in `src/safeco/events.py`; do not create a second event format. First handoff: a pure detector function accepts an event/history and returns zero or more alerts containing `alert_id`, `event_id`, `severity`, `reason_code`, `title`, `explanation`, `evidence`, `recommended_action`, `confidence`, and `acknowledged`.

Joseph implements in order: invariant rules, replay checks, rate/drift checks, then robust statistical baselines only if needed. Treat correctly sequenced maintenance, demand variation, grid loss, and generator recovery as benign. Keep complete scenarios held out for evaluation and report recall, precision, false alerts per normal hour, latency, and failures.

### Ebi: API and dashboard

Ebi builds against the shared event and alert contracts; do not invent dashboard-only state. First handoff: a local page displays tank level, pump, inlet/outlet valves, power source, operating mode, recent events, and an alert placeholder using backend data. The dashboard must continue locally without internet and clearly indicate degraded visibility if the local control feed is lost.

Ebi's alert presentation must answer what happened, affected equipment, current context, why it matters, confidence, evidence, and recommended human action. SafeCO is advisory; the interface must never imply that it automatically stopped equipment.

## Accuracy rules

- Adupe Municipal Water Station is fictional and representative, not a real facility or digital twin.
- Modbus-valid does not mean process-safe; contextual detection is the central claim.
- Internet loss and local control-network loss are different. SafeCO works without internet, but cannot detect unseen traffic when its local feed is unavailable.
- The hash chain detects later modification of stored events; it does not prove that the original sensor reading was truthful.
- A closed flow path is described as dangerous only where the documented plant topology and implemented invariant support that claim.
- The simulator may apply an unsafe but protocol-valid command for demonstration. SafeCO observes, explains, and advises; a human decides.
- Never tune or test on the same complete scenarios, and never hide missed attacks or false positives.

## Interfaces that must not drift

### Event contract

```json
{
  "event_id": "uuid",
  "timestamp": "ISO-8601 UTC",
  "scenario_id": "normal_running_01",
  "ground_truth": "normal|injection|replay|mistimed|drift|maintenance",
  "source": "scheduler|operator|attacker",
  "command": "write_register|read_register|telemetry",
  "target": "pump|inlet_valve|outlet_valve|level_setpoint",
  "value": 0,
  "mode": "startup|running|maintenance|shutdown",
  "process": {"tank_level": 55.2, "valve_state": "open", "pump_state": "on"},
  "sequence_id": 42,
  "raw": {}
}
```

Detector output must contain: `alert_id`, `event_id`, `severity`, `reason_code`, `title`, `explanation`, `evidence`, `recommended_action`, `confidence`, and `acknowledged`.

### Definition of ready

No component is integrated until it has a README, one command to run it, deterministic sample data, tests for its public behaviour, and a short note describing known limitations.

## Timeline

### 20–23 August: foundation

Daniel creates the repository layout, SQLite schema, event repository, event hash-chain, runtime entrypoint, issue board, branch rules, and a single `make demo`/equivalent command. Mahoraga defines the process model, register map, invariants, and normal scenarios. Joseph finalises detector input/output schemas and labelled fixtures. Ebi creates the FastAPI shell, health endpoint, and dashboard wireframe.

Exit criteria: a clean laptop can start the simulator, generate one normal event, store it, and retrieve it through the API.

The foundation must include the authoritative plant/register contract and tests for state transitions. Grid outage and correctly sequenced generator recovery are labelled benign.

### 24–27 August: normal plant and data

Mahoraga implements startup, running, maintenance, and shutdown with deterministic replay. Daniel implements collection, raw-event persistence, hash verification, and the first end-to-end integration. Joseph consumes the stored event stream for detector development. Ebi connects a live process-state view.

Exit criteria: normal operation runs for at least ten simulated minutes; maintenance is not falsely flagged; generated data can be recreated from a seed.

### 28–31 August: selection and attack generation

Mahoraga implements command injection, replay, mistimed valid command, and slow drift scenarios. Joseph labels expected outcomes and builds held-out scenario sets. Ebi adds scenario controls and an alert placeholder. Daniel wires each scenario into the runtime, verifies event integrity, confirms the Track E selection is submitted by 31 August, and freezes scope.

Exit criteria: each attack has a one-command reproducer, ground truth, expected safety impact, and a visible event trace.

### 1–7 September: detector and evaluation

Joseph implements invariant rules first, then replay, rate/drift, and baseline checks. Mahoraga validates process realism and adds benign anomalies. Ebi renders alert explanations and acknowledgement. Daniel builds the integration-test harness, event replay, API wiring, and integrity-failure tests.

Exit criteria: all four attack types are detected in the held-out set; metrics include recall, precision, false alerts per normal hour, and latency; known misses are documented.

### 8–14 September: hardening and demo

Ebi completes dashboard, offline queue/catch-up, evidence detail, and export. Joseph tunes thresholds without hiding failures. Mahoraga adds attack timing and telemetry noise. Daniel implements and validates local queue recovery, hash-chain verification, failure tests, security review, and full demo rehearsal.

Exit criteria: disconnecting the UI does not stop collection; reconnect catches up; uncertain alerts remain advisory; the complete demo works from a fresh checkout.

### 15–20 September: submission package

Daniel owns the release candidate, startup packaging, backend code review, final technical write-up, and submission folder. Ebi supplies dashboard screenshots and API documentation. Joseph supplies metric tables and error analysis. Mahoraga supplies simulator/attack methodology and architecture figures. All four rehearse a five-minute demo and a two-minute judge Q&A.

Exit criteria: code link, working demo, write-up (maximum four pages), run instructions, synthetic-data explanation, and video/screenshots are complete and tested.

### 21 September: submit

Submit before 11:59 PM, then verify the uploaded files can be downloaded and run. Do not make feature changes after the release candidate without a team decision.

## Daily operating rhythm

- 15-minute check-in: done, next, blocker.
- Each owner posts a short end-of-day note and updates the issue board.
- Integrate at least once daily; never wait until the final week.
- Blockers lasting more than four working hours are escalated to Daniel.
- Demo the current build every two days, even when incomplete.

## Step-by-step build order

1. Agree on the four invariants and register map.
2. Create the event and alert schemas before feature coding.
3. Build a deterministic normal simulator.
4. Persist raw and normalised events.
5. Add one normal dashboard view.
6. Add each attack as a reproducible scenario.
7. Implement deterministic rules before statistical baselines.
8. Add plain-language explanations linked to evidence.
9. Build held-out evaluation and report failures.
10. Add offline collection and reconnect replay.
11. Package one-command startup and clean-install test.
12. Rehearse, freeze, and submit.

## Acceptance tests

- Pump-start while inlet valve is closed creates a high-severity contextual alert within one second.
- Replaying an old command is identified even when its Modbus format is valid.
- Slow setpoint drift is detected before the tank leaves the safe range.
- Legitimate maintenance is accepted when the mode and actor are correct.
- A network/UI disconnect does not lose events.
- Every alert explains what happened, why it matters, evidence, confidence, and recommended human action.
- Metrics are computed on scenarios not used to tune thresholds.

## Handoff checklist

Every handoff includes: changed files, how to run, interface/schema changes, tests run, screenshots or sample output, known limitations, and the next owner. Never hand off only a verbal explanation. Use a small Markdown note in the issue or pull request.

## Scope control

Cut, in order: fancy visualisations, authentication, machine learning, multi-process deployment, and extra attack types. Never cut the simulator, four required attacks, explanations, evaluation, offline story, or reproducible run command.
