"""Explainable robust statistical baseline for SafeCO detector Layer 5.

The baseline learns simple numeric ranges from benign scenario event
traces. It is intentionally small and transparent: no opaque model, no
external data, and no use of ground-truth labels during scoring.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from statistics import median

from .alerts import Alert, ReasonCode, build_alert
from .events import Event

MIN_GROUP_SAMPLES = 3
"""Minimum events required before a baseline group is scored."""

MIN_OUTLIER_FEATURES = 2
"""Number of unusual features needed before emitting one baseline alert."""

MAD_SCALE = 6.0
"""Conservative robust range multiplier to avoid noisy false positives."""


@dataclass(frozen=True)
class FeatureVector:
    """Numeric representation of one event for baseline scoring."""

    mode: str
    command: str
    target: str
    value: float | None
    tank_level: float
    target_level: float | None
    high_level_limit: float | None
    recent_target_writes: float

    @property
    def group_key(self) -> str:
        """Return the context group this event should be compared within."""
        return f"{self.mode}/{self.command}/{self.target}"

    def numeric_features(self) -> dict[str, float]:
        """Return feature names and available numeric values."""
        values: dict[str, float] = {
            "tank_level": self.tank_level,
            "recent_target_writes": self.recent_target_writes,
        }
        if self.value is not None:
            values["value"] = self.value
        if self.target_level is not None:
            values["target_level"] = self.target_level
        if self.high_level_limit is not None:
            values["high_level_limit"] = self.high_level_limit
        return values


@dataclass(frozen=True)
class RobustRange:
    """Median/MAD-backed normal range for one numeric feature."""

    median: float
    mad: float
    lower: float
    upper: float
    sample_count: int

    def contains(self, value: float) -> bool:
        """Return whether ``value`` is inside the learned robust range."""
        return self.lower <= value <= self.upper


@dataclass(frozen=True)
class BaselineGroup:
    """Learned normal feature ranges for one mode/command/target group."""

    key: str
    feature_ranges: Mapping[str, RobustRange]
    sample_count: int


@dataclass(frozen=True)
class BaselineProfile:
    """Complete learned baseline keyed by mode/command/target."""

    groups: Mapping[str, BaselineGroup]
    training_scenarios: tuple[str, ...]
    seed: int


def _numeric(value) -> float | None:
    """Return ``value`` as float when it is numeric, otherwise ``None``."""
    if isinstance(value, int | float):
        return float(value)
    return None


def extract_features(event: Event, history: Sequence[Event] = ()) -> FeatureVector:
    """Extract baseline features from an event and same-run history.

    Args:
        event: Current event being modelled.
        history: Earlier events from the same logical run.

    Returns:
        A feature vector for robust baseline training or scoring.

    """
    recent = [*history[-9:], event]
    return FeatureVector(
        mode=event.mode,
        command=event.command,
        target=event.target,
        value=_numeric(event.value),
        tank_level=event.process.tank_level,
        target_level=event.process.target_level,
        high_level_limit=event.process.high_level_limit,
        recent_target_writes=float(
            sum(1 for candidate in recent if candidate.target == event.target)
        ),
    )


def _robust_range(values: Sequence[float]) -> RobustRange:
    """Build a conservative median/MAD range for observed values."""
    centre = float(median(values))
    deviations = [abs(value - centre) for value in values]
    mad = float(median(deviations))
    if mad == 0.0:
        lower = min(values)
        upper = max(values)
    else:
        lower = centre - MAD_SCALE * mad
        upper = centre + MAD_SCALE * mad
    return RobustRange(
        median=centre,
        mad=mad,
        lower=lower,
        upper=upper,
        sample_count=len(values),
    )


def train_baseline(
    traces: Mapping[str, Sequence[Event]],
    *,
    seed: int = 42,
) -> BaselineProfile:
    """Train a robust profile from benign scenario traces.

    Args:
        traces: Mapping of scenario ID to events. Callers are responsible
            for passing benign traces only.
        seed: Seed recorded for provenance.

    Returns:
        A deterministic baseline profile.

    """
    grouped: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    counts: dict[str, int] = defaultdict(int)
    for events in traces.values():
        history: list[Event] = []
        for event in events:
            features = extract_features(event, history)
            counts[features.group_key] += 1
            for name, value in features.numeric_features().items():
                grouped[features.group_key][name].append(value)
            history.append(event)

    groups = {
        key: BaselineGroup(
            key=key,
            feature_ranges={
                name: _robust_range(values)
                for name, values in sorted(feature_values.items())
                if len(values) >= MIN_GROUP_SAMPLES
            },
            sample_count=counts[key],
        )
        for key, feature_values in sorted(grouped.items())
        if counts[key] >= MIN_GROUP_SAMPLES
    }
    return BaselineProfile(
        groups=groups,
        training_scenarios=tuple(sorted(traces)),
        seed=seed,
    )


def check_baseline(
    event: Event,
    history: Sequence[Event],
    profile: BaselineProfile,
) -> list[Alert]:
    """Score an event against a trained baseline profile.

    Args:
        event: Current event under evaluation.
        history: Earlier events from the same logical run.
        profile: Learned benign baseline profile.

    Returns:
        Zero alerts when the event is normal or unsupported by the profile,
        otherwise one explainable ``BASELINE_DEVIATION`` alert.

    """
    features = extract_features(event, history)
    group = profile.groups.get(features.group_key)
    if group is None or group.sample_count < MIN_GROUP_SAMPLES:
        return []

    outside: dict[str, dict[str, float]] = {}
    numeric_features = features.numeric_features()
    for name, observed in numeric_features.items():
        learned = group.feature_ranges.get(name)
        if learned is None or learned.contains(observed):
            continue
        outside[name] = {
            "observed": observed,
            "lower": learned.lower,
            "upper": learned.upper,
            "median": learned.median,
            "mad": learned.mad,
        }

    if len(outside) < MIN_OUTLIER_FEATURES:
        return []

    evidence = {
        "scenario_id": event.scenario_id,
        "sequence_id": event.sequence_id,
        "timestamp": event.timestamp,
        "command": event.command,
        "target": event.target,
        "value": event.value,
        "mode": event.mode,
        "source": event.source,
        "ground_truth": event.ground_truth,
        "baseline_group": features.group_key,
        "features_outside_range": sorted(outside),
        "features_text": ", ".join(sorted(outside)),
        "observed": outside,
        "training_scenarios": profile.training_scenarios,
    }
    return [build_alert(event.event_id, ReasonCode.BASELINE_DEVIATION, evidence)]
