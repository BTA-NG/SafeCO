"""Persistent SQLite store for detector alerts and acknowledgement state.

The detector is pure and re-derives the same ``alert_id`` for a given
``(event_id, reason_code)`` pair every run (see ``alerts.derive_alert_id``).
This store uses that identity as the primary key so replaying the detector
over stored events is idempotent and never loses an engineer's
acknowledgement. It complements ``EventStore``: events are the raw record,
alerts are the explained findings the dashboard surfaces.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from .alerts import SEVERITY_RANK, Alert, Severity

SCHEMA = """
CREATE TABLE IF NOT EXISTS alerts (
    alert_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    severity TEXT NOT NULL,
    severity_rank INTEGER NOT NULL,
    reason_code TEXT NOT NULL,
    title TEXT NOT NULL,
    explanation TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    recommended_action TEXT NOT NULL,
    confidence REAL NOT NULL,
    acknowledged INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_alerts_ack ON alerts(acknowledged);
"""


class AlertStore:
    """SQLite persistence for alerts keyed by their deterministic id."""

    def __init__(self, database: str | Path = "data/safeco_alerts.db") -> None:
        """Open (or create) the alert database and ensure the schema exists.

        Args:
            database: Filesystem path for the database file. Parent
                directories are created automatically. Defaults to a file
                separate from ``EventStore`` so the two stores never hold
                competing writer connections to one SQLite file.

        """
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        # One connection is shared across FastAPI request threads; the lock
        # serializes access the same way EventStore does. busy_timeout is a
        # safety net if this store is ever pointed at a file another
        # connection also writes.
        self._lock = threading.Lock()
        self.connection = sqlite3.connect(self.database, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA busy_timeout=5000")
        self.connection.executescript(SCHEMA)
        self.connection.commit()

    def upsert(self, alert: Alert) -> None:
        """Persist an alert, preserving any existing acknowledgement.

        The detector may re-emit the same finding when it replays stored
        events. Re-inserting must not reset an alert an engineer already
        acknowledged, so the acknowledged flag is never overwritten here.

        Args:
            alert: The ``Alert`` to persist.

        """
        with self._lock:
            self.connection.execute(
                """INSERT INTO alerts (
                    alert_id, event_id, severity, severity_rank, reason_code,
                    title, explanation, evidence_json, recommended_action,
                    confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(alert_id) DO UPDATE SET
                    event_id=excluded.event_id,
                    severity=excluded.severity,
                    severity_rank=excluded.severity_rank,
                    reason_code=excluded.reason_code,
                    title=excluded.title,
                    explanation=excluded.explanation,
                    evidence_json=excluded.evidence_json,
                    recommended_action=excluded.recommended_action,
                    confidence=excluded.confidence
                """,
                (
                    alert.alert_id,
                    alert.event_id,
                    str(alert.severity),
                    SEVERITY_RANK[Severity(alert.severity)],
                    str(alert.reason_code),
                    alert.title,
                    alert.explanation,
                    json.dumps(alert.evidence, sort_keys=True),
                    alert.recommended_action,
                    alert.confidence,
                ),
            )
            self.connection.commit()

    def list_alerts(
        self, *, acknowledged: bool | None = None, limit: int = 100
    ) -> list[dict[str, object]]:
        """Return stored alerts ordered most-urgent-first.

        Results are ordered by severity rank (critical first) then alert id, so
        the dashboard queue shows the highest-severity findings at the top and
        the order is stable across polls.

        Args:
            acknowledged: If ``True`` return only acknowledged alerts, if
                ``False`` only unacknowledged; if ``None`` return both.
            limit: Maximum number of alerts to return.

        Returns:
            A list of alert dicts in the shared alert-contract shape.

        """
        query = "SELECT * FROM alerts"
        params: list[object] = []
        if acknowledged is not None:
            query += " WHERE acknowledged = ?"
            params.append(1 if acknowledged else 0)
        query += " ORDER BY severity_rank DESC, alert_id ASC LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = list(self.connection.execute(query, params))
        return [self._row_to_dict(row) for row in rows]

    def get(self, alert_id: str) -> dict[str, object] | None:
        """Return a single alert by its id.

        Args:
            alert_id: The deterministic alert identifier to look up.

        Returns:
            The alert dict, or ``None`` if no alert with that id is stored.

        """
        with self._lock:
            row = self.connection.execute(
                "SELECT * FROM alerts WHERE alert_id = ?", (alert_id,)
            ).fetchone()
        return self._row_to_dict(row) if row is not None else None

    def acknowledge(self, alert_id: str) -> bool:
        """Mark an alert as acknowledged.

        Acknowledgement is persisted so it survives restarts and detector
        replay (``upsert`` never clears it).

        Args:
            alert_id: The identifier of the alert to acknowledge.

        Returns:
            ``True`` if an alert with that id existed and was updated, ``False``
            otherwise (so callers can return 404 rather than false success).

        """
        with self._lock:
            cursor = self.connection.execute(
                "UPDATE alerts SET acknowledged = 1 WHERE alert_id = ?",
                (alert_id,),
            )
            self.connection.commit()
            return cursor.rowcount > 0

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, object]:
        """Convert a stored alert row into the shared alert-contract dict.

        The evidence column is stored as a JSON string; this parses it back into
        an object and coerces the integer acknowledged flag to a bool so the API
        emits the same shape the detector's ``Alert`` produces.

        Args:
            row: A ``sqlite3.Row`` from the alerts table.

        Returns:
            A JSON-friendly alert dict with evidence parsed and flags coerced.

        """
        return {
            "alert_id": row["alert_id"],
            "event_id": row["event_id"],
            "severity": row["severity"],
            "reason_code": row["reason_code"],
            "title": row["title"],
            "explanation": row["explanation"],
            "evidence": json.loads(row["evidence_json"]),
            "recommended_action": row["recommended_action"],
            "confidence": row["confidence"],
            "acknowledged": bool(row["acknowledged"]),
        }

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self.connection.close()
