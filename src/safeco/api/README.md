# SafeCO API

This directory contains the FastAPI service for the SafeCO dashboard and local operator workflow. The API is intentionally a read layer on top of the existing backend contracts in the `safeco` package. It reads persisted events from SQLite, exposes the latest plant snapshot, and serves the alert feed for the dashboard.

## Purpose

The API is not the source of truth for plant behavior or detector logic. Those live in:

- `src/safeco/storage.py`
- `src/safeco/detector.py`
- `src/safeco/collector.py`
- `src/safeco/events.py`
- `src/safeco/alerts.py`
- `src/safeco/plant.py`

The FastAPI layer provides a clean interface for the dashboard and local operator tooling.

## Current milestone

The current API milestone covers the core dashboard-facing routes. Routes are
split below into **implemented** (backed by persisted data) and **scaffold**
(wiring for the dashboard that is not yet backed by durable storage).

### Implemented (backed by the SQLite event store)

- `GET /api/health` — reports healthy vs degraded local collection feed
- `GET /api/events` — recent persisted events, optional `scenario_id` filter
- `GET /api/events/{event_id}` — single event, 404 if unknown
- `GET /api/events/after/{event_id}` — events after a checkpoint, 404 if unknown
- `GET /api/plant/state` — latest persisted process snapshot
- `GET /api/scenarios` — scenario IDs derived from the actual
  `NORMAL_SCENARIOS` and `ATTACK_SCENARIOS` registries
- `GET /api/scenarios/{scenario_id}` — registration status, 404 if unknown

### Scaffold (in-memory only, not persisted — do not treat as complete)

- `GET /api/alerts`
- `GET /api/alerts/unacknowledged`
- `GET /api/alerts/{alert_id}`
- `PATCH /api/alerts/{alert_id}/ack`

The alert routes read and mutate an in-memory `app.state.alerts` list. They are
not populated by the detector and are not persisted, so alerts and their
acknowledgement state are lost on restart. Durable alert storage backed by the
shared alert contract is deferred to a future milestone. Alert retrieval and
acknowledgement must not be presented as finished features.

The scenario routes list and validate scenario IDs only. Scenario **execution**
(`run_scenario`) is intentionally deferred and not exposed. No route performs or
implies a confirmed simulator action; that remains future work.

## Deferred work

- Scenario **execution** endpoints (running a scenario through the API).
- Persistent alert storage and acknowledgement backed by the alert contract.
- Any engineer-confirmed simulator action. SafeCO stays advisory-only; the API
  never issues or blocks control actions.

## Running the API

From the repository root:

```bash
Set-Location ".\BTA-NG\SafeCO"
$env:PYTHONPATH = "src"
python -m uvicorn safeco.app:app --reload --host 127.0.0.1 --port 8000
```

The default app object is exposed in `src/safeco/app.py`.

## Local data source

The service uses the shared SQLite event store created by `EventStore` in
`src/safeco/storage.py`. The store shares a single connection across requests and
serializes access with an internal lock so concurrent FastAPI requests are safe.

## Notes

- The dashboard must treat SafeCO as advisory-only.
- The API never issues or blocks control actions.
- This layer exists to surface current state, raw event history, and alert
  explanation for engineers.
- Scenario discovery is available; scenario **execution** is deferred future work.
