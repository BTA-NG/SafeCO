# Project Context

## Mission

For ICSC 2026, build SafeCO, an explainable prototype that helps an engineer catch unsafe commands at **Adupe Municipal Water Station**, a fictional Nigerian municipal pumping and storage facility. The chosen challenge is Track E, E1. Adupe is representative and must never be presented as a real facility or as modelling a named organisation's vulnerabilities.

## Constraints

- Selection closes 31 August 2026.
- Submission closes 21 September 2026 at 11:59 PM.
- Submit a working demo, technical write-up of at most four pages, and code link.
- No real personal data, real plant access, special hardware, or paid tools.
- Show normal operation, startup/shutdown, legitimate maintenance, four reproducible attacks, detector results, explanations, and offline behaviour.
- The system advises a human; it must not shut the process down automatically.

## Product statement

SafeCO observes commands and process state in a simulated water tank controlled over Modbus TCP. It identifies malformed, replayed, mistimed, and gradually unsafe commands, then presents equipment, evidence, severity, and next action in engineer-friendly language.

## Nigerian operating context

- Grid outages and generator/recovery transitions are expected operating events, not attacks by default.
- The station must keep collecting locally during weak or absent external connectivity.
- A small operations team may use a shared control-room device.
- Morning/evening demand, maintenance and restart activity can legitimately change the traffic baseline.
- SafeCO remains advisory because an incorrect automatic block could interrupt water service or prevent a safety action.

## Design principles

1. Simplest design that demonstrates the security claim.
2. Local-first and deterministic.
3. Explainability over model complexity.
4. Process safety over secrecy.
5. Every claim backed by a reproducible scenario and metric.
6. Uncertainty is visible.

## Stable decisions

- Python, pymodbus, FastAPI, SQLite, and a minimal browser UI.
- The product is named **SafeCO** and its Python package/import name is `safeco`.
- Rules and robust statistical baselines first; no neural model without measured gain.
- SQLite is the prototype system of record and raw events are retained.
- No blockchain, cloud service, or physical board.

## Demo narrative

Start Adupe in normal running. Simulate grid loss and a legitimate generator recovery/restart, which SafeCO accepts. Show legitimate maintenance accepted. Replay an earlier valid pump-start command after the process context has changed, then inject a valid pump-start while the flow path is closed and slowly drift the high-level setpoint. Disconnect the dashboard while local collection continues, reconnect, and show catch-up. End with held-out metrics and one known limitation.

## Risks and mitigations

- Clean synthetic data: add timing jitter, sensor noise, benign anomalies, and maintenance.
- Simulator overfitting: hold out complete scenarios.
- False positives: measure alerts per normal hour and use graded severity.
- Hidden evidence: link every alert to raw event and process snapshot.
- Scope creep: freeze the architecture and cut features before tests.

## Continuation protocol

Read this file and architecture.md before changing direction. Preserve the product statement, constraints, event schema, and advisory-only response. Any new dependency or model must satisfy a measured requirement. Every detector change needs a scenario test and updated evaluation. Never commit real personal or operational data.

## Open questions

- Detector thresholds after baseline experiments.
- Server-rendered HTML or a small React client.
- Screenshots and metric tables for the four-page report.
