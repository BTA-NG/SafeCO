from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
import json
import uuid


@dataclass(frozen=True)
class ProcessSnapshot:
    tank_level: float
    valve_state: str
    pump_state: str


@dataclass(frozen=True)
class Event:
    scenario_id: str
    ground_truth: str
    source: str
    command: str
    target: str
    value: Any
    mode: str
    process: ProcessSnapshot
    sequence_id: int
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def canonical_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

