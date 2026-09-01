# Detector Evaluation Notes

SafeCO's detector combines deterministic rules with an optional robust
statistical baseline. It detects direct safety invariant violations, invalid
operating transitions, replay-like command repetition, command-rate spikes,
cumulative setpoint drift, and multi-feature deviations from benign scenario
history.

Evaluation is scenario-level, not row-shuffled. Each scenario is replayed as one
logical run with its own detector history so transition, replay, and drift checks
cannot see events from another run.

## Metrics

The evaluation harness reports:

- Precision.
- Recall.
- False alerts per normal hour.
- TP/FP/TN/FN classification counts.
- Missed attack scenarios.
- Maintenance false positives.
- First detection sequence ID for each scenario.
- First detection event ID.
- Detection latency in events and seconds.

## Evaluation Commands

Layer 5 is enabled by default for evaluation/demo runs:

```bash
PYTHONPATH=src python -m safeco.evaluation
```

Run deterministic rules only:

```bash
PYTHONPATH=src python -m safeco.evaluation --without-baseline
```

Compare rule-only and baseline-enabled reports:

```bash
PYTHONPATH=src python -m safeco.evaluation --compare
```

Emit JSON metrics or sample event/alert evidence:

```bash
PYTHONPATH=src python -m safeco.evaluation --json
PYTHONPATH=src python -m safeco.evaluation --samples-json
```

## Scenario Splits

Scenarios are explicitly split into tuning, validation, and held-out sets. The
held-out set can be evaluated without running or tuning on the tuning scenarios.

## Known Limitations

- Replay detection depends on available same-run event history.
- Drift thresholds are conservative and hand-tuned.
- The statistical baseline is explainable and conservative, but it depends on
  the coverage of benign training scenarios.
- Synthetic scenarios are deterministic and may not cover all benign operator
  behaviour.
- Ground-truth labels are used only for evaluation, never for detection
  decisions.
- SafeCO is advisory-only and does not issue plant-control commands.
