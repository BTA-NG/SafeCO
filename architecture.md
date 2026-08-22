# ICSC 2026 Hackathon Architecture

## Decision

Build Track E: **Catching Unsafe Commands in Your Own Control System**.

The recommended product is **SafeCO**, a local-first, advisory OT command monitor for **Adupe Municipal Water Station**, a fictional Nigerian municipal pumping and storage facility. It runs a small water-tank process simulator over Modbus TCP, records commands and process state, detects commands that are valid but unsafe in context, and explains alerts to an engineer. It never automatically shuts down the process.

This is the best fit for a cybersecurity and development team because the team controls the plant model, can generate labelled attack data reproducibly, and can demonstrate both protocol security and process-aware detection without real infrastructure. The core design is intentionally small: simulator, event collector, rules/statistical detector, API, and operator UI.

## Goals and non-goals

Goals: detect malformed, replayed, wrong-state, and gradual unsafe setpoint commands; run on one laptop offline; explain every alert; preserve raw events; and provide advisory response only.

Non-goals: real industrial equipment, production safety certification, autonomous shutdown, blockchain, deep learning, or cloud dependency without measured benefit.

## System context

Attack and normal scripts feed a Modbus TCP simulator. The simulator feeds a collector and SQLite event store. A layered rules and baseline detector feeds a FastAPI service and engineer alert dashboard. The dashboard is a read/acknowledge client, not a control path.

## Components

### Reusable infrastructure adapter

The detector core consumes a normalized asset/event interface rather than water-specific names. Adupe is the reference adapter for the demo. A future electricity adapter could map feeder, breaker, voltage, frequency, and setpoint events into the same contract. We do not build or claim a second infrastructure simulator during this hackathon.

### Process simulator

Python model with tank level, inlet pump, inlet and outlet valves, flow, power source, setpoints, and modes: startup, running, maintenance, shutdown, recovery. Expose the register map in `src/safeco/plant.py` over Modbus TCP using pymodbus. Include deterministic seeds and a clock multiplier. Explicit invariants: pump cannot run without an open inlet path; tank level remains within safe limits; setpoint changes are rate-limited and authorised in maintenance; command sequences respect mode transitions; grid-to-generator recovery is legitimate when sequenced correctly.

### Scenarios and collector

Produce normal startup, steady running, shutdown, legitimate maintenance, grid outage and generator recovery, and four required attacks: command injection, replay, valid command at the wrong moment, and slow setpoint drift. Every event carries scenario ID and ground-truth label. Capture commands, responses, and telemetry in a common schema: timestamp, scenario_id, source, actor, command, target, value, mode, tank_level, valve_state, pump_state, sequence_id, ground_truth. Use SQLite WAL and retain raw JSON.

The Nigerian context improves realism but does not change the ground truth to fit a story. Grid loss, generator transfer and demand changes are benign scenarios unless an independently unsafe command occurs.

### Detector

Layer invariant rules, replay checks, rate/drift checks, and robust per-command/per-mode baselines using median/MAD or quantiles. Emit severity, reason code, evidence, and recommended action. Group related findings into incidents.

### API and dashboard

FastAPI endpoints: health, events, alerts, alert acknowledgement, scenario start, and metrics. A minimal browser UI shows live state, alert queue, event detail, and scenario selection. Use WebSocket or polling, with last-known state when disconnected.

### Evaluation

Use held-out scenarios. Report per-attack recall, precision, false alerts per normal hour, detection latency, confusion matrix, missed attacks, and legitimate maintenance allowed.

## Reliability and security

All components run locally. If the UI or network disappears, collection continues in SQLite and the dashboard catches up by event ID after reconnection. Uncertain cases become review alerts and never issue a control command. Bind Modbus to localhost, validate registers and schemas, and hash-chain append-only events for tamper evidence.

## Three-week delivery

1. Week 1: simulator, register map, normal scenarios, storage, deterministic replay.
2. Week 2: attacks, detector, evaluation harness, explanation format.
3. Week 3: dashboard, offline demo, tests, write-up, packaging, rehearsal.

## Definition of done

One command starts the demo. A judge can select a scenario, watch the process, see an alert within one second, read its explanation, inspect evidence, acknowledge it, and export metrics. Replay or modification is detected. Results regenerate from a documented seed.

## Alternatives

Tracks D and G are strong runner-ups with excellent synthetic data and dashboards. H is technically simplest but risks looking like a basic hashing utility. B and C require more privacy and healthcare workflow validation. A needs scarce fraud labels and careful false-positive economics. F needs real user testing. E best balances technical depth, controllable ground truth, and memorable demonstration.
