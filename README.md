# SafeCO

SafeCO is a local-first, advisory cybersecurity monitor for unsafe industrial
control commands. The ICSC 2026 prototype monitors **Adupe Municipal Water
Station**, a fictional municipal water facility, through a deterministic Modbus
TCP simulator.

SafeCO detects commands that are protocol-valid but unsafe in the current
process context. It preserves the event evidence, explains the finding, assigns
severity and confidence, recommends an engineer check, and records human
acknowledgement.

> SafeCO never autonomously blocks, reverses, delays, or issues a consequential
> plant-control command. Detect -> explain -> recommend -> human decides.

## What the demo proves

- Normal startup, shutdown, maintenance, recovery, and demand scenarios are
  accepted without treating every unusual condition as an attack.
- Injection, replay, mistimed-command, setpoint-drift, and statistical-baseline
  scenarios produce reproducible events and explainable alerts.
- Events and alerts persist locally in SQLite; event records form a
  tamper-evident SHA-256 hash chain.
- The dashboard shows plant state, event history, alert evidence,
  acknowledgement state, and degraded visibility when fresh events stop.
- Seeds, generator versions, scenario fingerprints, and held-out evaluation
  splits make results reproducible.

## Architecture

```text
Scenario / Modbus command
          |
          v
Deterministic plant simulator
          |
          v
EventCollector -> SQLite EventStore -> layered detector -> AlertStore
                                                   |
                                                   v
                                      FastAPI + operator dashboard
```

The detector layers are:

1. Process safety invariants.
2. Operating-mode and state-transition checks.
3. Replay and sequence checks.
4. Command-rate and cumulative setpoint-drift checks.
5. Optional robust median/MAD baseline checks.

## Quick start

From the repository root:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt -r requirements-dev.txt
PYTHONPATH=src python -m uvicorn safeco.app:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000/>. If port `8000` is occupied, use another local
port, for example `--port 8001`.

The initial dashboard intentionally reports degraded visibility because no
plant event has been observed yet. Run a scenario to create the first local
event trace.

## Dashboard guide

- **Plant state** shows the latest observed operating mode, power source, pump,
  valves, target level, tank level, and high-level safety limit.
- **Alerts** shows detector findings, severity, confidence, evidence,
  recommended checks, and record-only acknowledgement.
- **Events** shows persisted commands and supports filtering by a registered
  scenario.
- **Scenarios** runs a deterministic simulator scenario with a chosen seed.
  The dashboard runner enables the same tuning-only statistical baseline used
  by evaluation, cached per seed for responsive repeated runs.
- **System health** distinguishes a healthy feed from stale or absent plant
  visibility while confirming whether local storage remains available.

`ground_truth` is the known label attached to synthetic evaluation data, such
as `normal`, `replay`, or `mistimed`. `source: scheduler` identifies the
simulator command channel used to reproduce the scenario; the detector does
not use ground truth to decide whether to alert.

## Recommended demo

Use seed `42` throughout so the run is reproducible.

1. Start from an empty demo database and show the initial degraded-visibility
   state.
2. Run `startup_01`; show the healthy feed, plant state, normal events, and no
   alerts.
3. Run `attack_injection_01`; show the HIGH unsafe-pump-start alert and its
   matching event evidence.
4. Run `attack_replay_01`; show replay detection after the plant context
   changes.
5. Acknowledge an alert and show that acknowledgement changes only the record,
   not plant state.
6. Run `benign_noise_01`; show that bounded telemetry noise produces events
   without an attack alert.
7. Allow the feed to become stale; show degraded visibility with last-known
   state and retained event history.

The local databases are `data/safeco.db` and `data/safeco_alerts.db`. Stop the
server and archive or remove those two demo files when a completely clean run
is required. Never remove the `data` directory broadly.

## Scenario and evaluation CLI

Run one deterministic scenario and print its fingerprint:

```bash
PYTHONPATH=src .venv/bin/python -m safeco.scenarios startup_01 \
  --seed 42 --fingerprint
```

Run the detector evaluation:

```bash
PYTHONPATH=src .venv/bin/python -m safeco.evaluation
```

Useful evaluation options include `--held-out`, `--without-baseline`,
`--compare`, and `--samples-json`.

## API summary

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/api/health` | Feed freshness, visibility, database, and event count |
| `GET` | `/api/plant/state` | Latest persisted process snapshot |
| `GET` | `/api/events` | Recent events, optionally filtered by `scenario_id` |
| `GET` | `/api/events/{event_id}` | One persisted event |
| `GET` | `/api/alerts` | Persistent detector alerts with acknowledgement filter |
| `PATCH` | `/api/alerts/{alert_id}/ack` | Record engineer acknowledgement only |
| `GET` | `/api/scenarios` | Discover runnable scenarios |
| `POST` | `/api/scenarios/{scenario_id}/run` | Run and persist a seeded scenario |

FastAPI's generated API documentation is available at `/docs` while the server
is running.

## Verification

Run all required checks before committing:

```bash
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
PYTHONPATH=src .venv/bin/python -m pytest -q
git diff --check
```

## Data and safety boundaries

- Adupe Municipal Water Station is fictional and representative. SafeCO does
  not connect to a real facility or use real operational data.
- Modbus protocol validity is not the same as process safety; SafeCO evaluates
  command context and process state.
- Hash-chain verification detects later modification of stored events. It does
  not prove that a sensor reading was truthful.
- The dashboard currently refreshes by HTTP polling. Server-Sent Events are a
  possible follow-up, not a claimed feature.
- The confirmed simulator-action concept is documented but not implemented in
  the current dashboard. All current acknowledgements are record-only.
- Evaluation results are synthetic and scenario-based, not a claim of
  production safety certification or field performance.

## Repository map

- `src/safeco/simulator.py`: deterministic water-process simulator.
- `src/safeco/scenarios.py`: normal, benign-anomaly, and attack scenarios.
- `src/safeco/modbus_server.py`: localhost Modbus TCP adapter.
- `src/safeco/events.py`: normalized event contract.
- `src/safeco/storage.py`: persistent event store and hash chain.
- `src/safeco/detector.py`: layered detector.
- `src/safeco/baseline.py`: robust statistical baseline.
- `src/safeco/evaluation.py`: scenario-level evaluation and metrics.
- `src/safeco/app.py`: FastAPI application and dashboard entry point.
- `src/safeco/api/static/`: no-build HTML, CSS, and JavaScript dashboard.
- `docs/plant_contract.md`: frozen plant/register and safety semantics.
- `TECHNICAL_REPORT_NOTES.md`: working evidence for the final four-page report.

## Contributing

Read `context.md`, `architecture.md`, and `docs/plant_contract.md` before
changing direction or shared interfaces. Engineering and Git workflow rules
are in `AGENTS.md` and `CONTRIBUTING.md`.
