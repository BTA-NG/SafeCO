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

The current API milestone covers the core dashboard-facing routes:

- `GET /api/health`
- `GET /api/events`
- `GET /api/events/{event_id}`
- `GET /api/events/after/{event_id}`
- `GET /api/plant/state`
- `GET /api/alerts`
- `GET /api/alerts/unacknowledged`
- `GET /api/alerts/{alert_id}`
- `PATCH /api/alerts/{alert_id}/ack`

## Deferred work

Scenario control endpoints are intentionally deferred for the first pass. They are not part of the current dashboard milestone and are documented as future work rather than implemented prematurely.

## Running the API

From the repository root:

```bash
Set-Location ".\BTA-NG\SafeCO"
$env:PYTHONPATH = "src"
python -m uvicorn safeco.app:app --reload --host 127.0.0.1 --port 8000
```

The default app object is exposed in `src/safeco/app.py`.

## Local data source

The service uses the shared SQLite event store created by `EventStore` in `src/safeco/storage.py`.

## Notes

- The dashboard must treat SafeCO as advisory-only.
- The API never issues or blocks control actions.
- This layer exists to surface current state, raw event history, and alert explanation for engineers.
- A future scenario-control router may be added once the core dashboard endpoints are stable.
