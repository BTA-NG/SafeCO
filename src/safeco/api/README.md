# SafeCO API

This directory contains the FastAPI service and operator dashboard for SafeCO.
SafeCO is a local-first advisory command monitor for industrial/utility control
systems; Adupe Municipal Water Station is the example site used for the demo.
The API is a read/advisory layer on top of the existing backend contracts in the
`safeco` package: it reads persisted events, exposes the latest plant snapshot,
serves detector alerts, and can run a scenario to generate that data.

## Purpose

The API is not the source of truth for plant behavior or detector logic. Those live in:

- `src/safeco/storage.py`
- `src/safeco/detector.py`
- `src/safeco/collector.py`
- `src/safeco/events.py`
- `src/safeco/alerts.py`
- `src/safeco/plant.py`

The FastAPI layer provides a clean interface for the dashboard and local operator tooling.

## Endpoints

All routes below are implemented and backed by persistent SQLite storage
(`EventStore` for events, `AlertStore` for alerts).

### Events (event store)

- `GET /api/health` — reports healthy vs degraded local collection feed
- `GET /api/events` — recent persisted events, optional `scenario_id` filter
- `GET /api/events/{event_id}` — single event, 404 if unknown
- `GET /api/events/after/{event_id}` — events after a checkpoint, 404 if unknown
- `GET /api/plant/state` — latest persisted process snapshot

### Alerts (alert store)

- `GET /api/alerts` — persisted detector alerts, most urgent first; `acknowledged`
  filter (`?acknowledged=false` pending, `?acknowledged=true` handled)
- `GET /api/alerts/{alert_id}` — single alert, 404 if unknown
- `PATCH /api/alerts/{alert_id}/ack` — record engineer acknowledgement (404 if unknown)

Alerts are keyed by the detector's deterministic `alert_id`, so acknowledgement
survives restarts and detector replay. Acknowledgement records that a human saw
the advisory finding; it never changes the plant.

### Scenarios (registry + execution)

- `GET /api/scenarios` — scenario IDs from the normal, attack, and timing-jitter
  attack registries
- `GET /api/scenarios/{scenario_id}` — registration status, 404 if unknown
- `POST /api/scenarios/{scenario_id}/run` — run a scenario (optional `seed`), persisting
  its events and any detector alerts; returns a summary (events, alerts,
  violations, reproducibility fingerprint), 404 if unknown

Running a scenario drives the simulator so its consequences can be observed and
explained. The execution path uses the deterministic tuning-only baseline for
the selected seed, so baseline-only attack fixtures produce their intended
findings in the dashboard as well as in evaluation. It never blocks a command
or acts on a real plant.

## Dashboard

A local operator console is served at `/`, with assets under `/static` (vanilla
HTML/CSS/JS — no build step). A fixed sidebar navigates five views over a live
feed-status indicator and a persistent health banner. It polls `/api/health`,
`/api/plant/state`, `/api/events`, and `/api/alerts` every 2 seconds and also
refreshes immediately after any operator action.

- **Plant state**: operating mode, power source, pump and valve status pills, and
  a tank-level bar with the high-level-limit marker.
- **Alerts**: the detector queue with an unacknowledged badge; all / unacknowledged
  / acknowledged filters; search by alert ID; and per-alert severity, the alert ID
  with a copy button, explanation, evidence, a confidence meter, and recommended
  action, with a record-only acknowledge button.
- **Events**: the recent event feed with a registered-scenario selector and
  ground-truth labels.
- **System health**: feed status, visibility, database availability, total events
  collected, and the last event timestamp.

The monitored-site identity is fixed to Adupe Municipal Water Station, the
fictional facility modelled by this submission. The palette is flat (light
content, a dark sidebar, status/severity colours) with a single subtle
gradient on the tank water fill for visual clarity. If the local
feed is lost the console keeps the last-known values and shows a
degraded-visibility banner. It never implies SafeCO acted automatically;
acknowledgement is an engineer record, not a plant action.


## Deferred work

- Any engineer-confirmed simulator action (write-back to the simulator after
  acknowledgement). This is safety-sensitive and changes plant-facing behavior, so
  it needs team agreement and Daniel's review of safety semantics before
  implementation. SafeCO stays advisory-only: there is no autonomous, timed, or
  unreviewed plant-changing command.

## Running the API

From the repository root:

```bash
PYTHONPATH=src .venv/bin/python -m uvicorn safeco.app:app \
  --host 127.0.0.1 --port 8000
```

Then open http://127.0.0.1:8000/ for the dashboard. The default app object is
exposed in `src/safeco/app.py`.

## Local data source

The service uses the shared SQLite stores created by `EventStore` and `AlertStore`.
Each shares a single connection across requests and serializes access with an
internal lock so concurrent FastAPI requests are safe.

## Notes

- The dashboard must treat SafeCO as advisory-only.
- The API never issues or blocks control actions.
- This layer surfaces current state, raw event history, and alert explanation for
  engineers, and can run a scenario to generate that data.
