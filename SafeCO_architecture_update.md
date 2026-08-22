# SafeCO Architecture Update

## Purpose

This document records the decisions from the latest team meeting. It is an architecture clarification, not an expansion of the hackathon scope.

The product remains **SafeCO**, an advisory cybersecurity monitor demonstrated against **Adupe Municipal Water Station**, a fictional Nigerian municipal water-pumping facility.

## Core product claim

SafeCO detects commands that are technically valid but unsafe in the current process context.

The system observes, explains, and advises. It never independently blocks, reverses, delays, or issues a consequential plant-control command.

Critical findings trigger immediate escalation, evidence preservation, recommended checks, and acknowledgement by an engineer. Detecting a safety-rule violation does not prove which control response is safe, so plant-changing actions remain human-in-the-loop. Any future automated action would require an explicitly configured and engineer-authorized policy with full audit logging; it is outside this submission's primary scope.

## Architecture boundary

The original implementation path remains:

```text
Adupe water simulator
        ↓
Modbus TCP
        ↓
Event collector
        ↓
SQLite event store
        ↓
Hybrid detector
        ↓
FastAPI API
        ↓
Local dashboard
        ↓
Engineer decision
```

The detector and event pipeline are being designed around a reusable normalized event interface. This allows future infrastructure adapters without making the detector itself water-specific.

```text
Infrastructure-specific process
        ↓
Infrastructure adapter
        ↓
Normalized SafeCO event
        ↓
Reusable storage, replay, and detector layers
        ↓
Alert contract and dashboard
```

### Scope clarification

The hackathon demonstration uses only Adupe's water process. We are not building a second electricity simulator. Electricity and other infrastructure are integration targets for future adapters, not additional deliverables for this submission.

We must describe this accurately as:

> SafeCO demonstrates contextual command detection using a simulated municipal water process. Its normalized event boundary is designed to support other infrastructure adapters, but those adapters are future work.

## Normalized event boundary

The reusable event envelope contains:

- Timestamp
- Scenario ID
- Source/actor
- Command type
- Target asset
- Command value
- Operating mode
- Telemetry snapshot
- Sequence ID
- Ground-truth label for evaluation

Water-specific state currently includes tank level, flow, pump, valves, power source, target level, and high-level limit. Future adapters may provide different telemetry under the same event envelope.

The existing source of truth is:

- `src/safeco/events.py`
- `src/safeco/plant.py`
- `docs/plant_contract.md`

Do not create a parallel event format or silently rename fields.

## Hybrid detector

SafeCO uses a layered hybrid detector:

### Layer 1: safety invariants

Infrastructure-specific rules identify definite physical hazards.

Adupe examples:

- Pump running with inlet valve closed
- Pump running without power
- Tank above high-level limit
- Target level at or above the high-level limit
- Invalid generator recovery sequence

### Layer 2: state-transition validation

Checks whether commands occur in a valid operating sequence.

Example recovery sequence:

```text
RUNNING
→ grid failure
→ pump stopped
→ RECOVERY
→ generator available
→ STARTUP
→ pump restart
→ RUNNING
```

A command can be valid in isolation but invalid during the current transition.

### Layer 3: replay and sequence checks

These checks are mostly infrastructure-independent. They detect duplicate sequence IDs, stale timestamps, repeated command fingerprints, and commands repeated outside their valid time window.

### Layer 4: rate and drift checks

These checks detect excessive command frequency and cumulative small changes, such as gradually raising a level setpoint.

### Layer 5: optional statistical baseline

Start with robust, explainable baselines such as median/MAD or quantile ranges. Consider `IsolationForest` only if evaluation shows a meaningful improvement. Do not add neural networks or opaque models.

ML is supplemental. It never replaces deterministic safety rules.

## Alert contract

Every alert must contain:

```json
{
  "alert_id": "uuid",
  "event_id": "uuid",
  "severity": "high",
  "reason_code": "unsafe_pump_start",
  "title": "Pump started with inlet path closed",
  "explanation": "A valid pump-start command was received while the inlet valve was closed.",
  "evidence": {},
  "recommended_action": "Confirm the command and inspect the inlet valve.",
  "confidence": 1.0,
  "acknowledged": false
}
```

The detector returns structured alerts. The API exposes them. The dashboard renders them. The dashboard must not implement a second copy of the detection logic.

## Synthetic-data pipeline

We generate all data using our deterministic simulator and scenario scripts. No real plant data, personal data, or assumed operational dataset is used.

### Benign scenarios

- Startup
- Steady running
- Controlled shutdown
- Legitimate maintenance
- Grid outage
- Generator recovery
- Demand variation
- Sensor noise and timing jitter

### Attack scenarios

- Command injection
- Replayed command
- Valid command in an unsafe state
- Slow setpoint/high-limit drift

Each scenario records its seed, scenario ID, generator version, command sequence, process snapshots, and ground-truth label.

### Evaluation split

Split by complete scenarios, never by random event rows from the same run:

```text
Tuning scenarios → threshold selection
Validation scenarios → adjustment
Held-out scenarios → final reported results
```

Report precision, recall, false alerts per normal hour, detection latency, per-attack results, legitimate-maintenance false positives, and missed attacks.

## Revised ownership

### Daniel

Backend, integration, event collector, SQLite storage, hash-chain verification, runtime, event replay, integration tests, final technical write-up, and submission.

### Mahoraga

Adupe process model, Modbus TCP simulator, normal scenarios, generator recovery, and reproducible attack scripts.

### Joseph

Hybrid detector, safety rules, replay/rate/drift checks, optional statistical baseline, held-out evaluation, metrics, and error analysis.

### Ebi

FastAPI service, local dashboard, process-state view, alert presentation, acknowledgement, connection/degraded status, offline display, screenshots, and API documentation.

## Accuracy and scope rules

- Adupe is fictional and representative, not a real facility or digital twin.
- Modbus-valid does not mean process-safe.
- Internet loss and local control-network loss are different conditions.
- SafeCO cannot detect traffic it cannot receive; it must show degraded visibility in that case.
- The hash chain detects later database modification; it does not prove original sensor truth.
- Describe a physical consequence only when the documented plant topology and implemented invariant support it.
- SafeCO advises; a human makes the operational decision.
- Do not claim electricity support has been implemented.
- Do not add 3D visuals, cloud deployment, blockchain, or complex ML before the required path works.

## Required integration path

```text
Modbus command
→ Adupe plant state
→ EventCollector
→ SQLite
→ Joseph's detector
→ FastAPI
→ Ebi's dashboard alert
```

The next shared acceptance test is:

> Start Adupe through Modbus, produce a normal plant event, persist it, run the detector, and display the resulting process state and alert status in the local dashboard.
