from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Iterable

from .events import Event

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    row_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    timestamp TEXT NOT NULL,
    scenario_id TEXT NOT NULL,
    ground_truth TEXT NOT NULL,
    source TEXT NOT NULL,
    command TEXT NOT NULL,
    target TEXT NOT NULL,
    value_json TEXT NOT NULL,
    mode TEXT NOT NULL,
    process_json TEXT NOT NULL,
    sequence_id INTEGER NOT NULL,
    raw_json TEXT NOT NULL,
    previous_hash TEXT NOT NULL,
    event_hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_scenario ON events(scenario_id);
"""


class EventStore:
    """SQLite event store with a tamper-evident hash chain."""

    def __init__(self, database: str | Path = "data/safeco.db") -> None:
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.database)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.executescript(SCHEMA)
        self.connection.commit()

    def append(self, event: Event) -> str:
        previous = self.connection.execute(
            "SELECT event_hash FROM events ORDER BY row_id DESC LIMIT 1"
        ).fetchone()
        previous_hash = previous["event_hash"] if previous else "0" * 64
        payload = f"{previous_hash}:{event.canonical_json()}".encode()
        event_hash = hashlib.sha256(payload).hexdigest()
        self.connection.execute(
            """INSERT INTO events (
                event_id, timestamp, scenario_id, ground_truth, source,
                command, target, value_json, mode, process_json, sequence_id,
                raw_json, previous_hash, event_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event.event_id,
                event.timestamp,
                event.scenario_id,
                event.ground_truth,
                event.source,
                event.command,
                event.target,
                json.dumps(event.value, sort_keys=True),
                event.mode,
                json.dumps(event.process.__dict__, sort_keys=True),
                event.sequence_id,
                json.dumps(event.raw, sort_keys=True),
                previous_hash,
                event_hash,
            ),
        )
        self.connection.commit()
        return event_hash

    def list_events(self, limit: int = 100) -> list[sqlite3.Row]:
        return list(
            self.connection.execute(
                "SELECT * FROM events ORDER BY row_id DESC LIMIT ?", (limit,)
            )
        )

    def verify_chain(self) -> tuple[bool, str | None]:
        previous_hash = "0" * 64
        rows: Iterable[sqlite3.Row] = self.connection.execute(
            "SELECT * FROM events ORDER BY row_id ASC"
        )
        for row in rows:
            if row["previous_hash"] != previous_hash:
                return False, row["event_id"]
            event_data = {
                "event_id": row["event_id"],
                "timestamp": row["timestamp"],
                "scenario_id": row["scenario_id"],
                "ground_truth": row["ground_truth"],
                "source": row["source"],
                "command": row["command"],
                "target": row["target"],
                "value": json.loads(row["value_json"]),
                "mode": row["mode"],
                "process": json.loads(row["process_json"]),
                "sequence_id": row["sequence_id"],
                "raw": json.loads(row["raw_json"]),
            }
            expected = hashlib.sha256(
                f"{previous_hash}:".encode()
                + json.dumps(event_data, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            if row["event_hash"] != expected:
                return False, row["event_id"]
            previous_hash = row["event_hash"]
        return True, None

    def close(self) -> None:
        self.connection.close()
