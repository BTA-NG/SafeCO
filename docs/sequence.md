# SafeCO Scenario-Run Sequence

Ordered runtime walkthrough of a single scenario run through detection to the
operator dashboard, plus the acknowledgement return path. For the static
system overview, see `docs/architecture.png`; for the full data-flow graph,
see [`docs/flowchart.md`](flowchart.md).

![SafeCO scenario-run sequence](sequence.png)

SafeCO stays advisory throughout: nothing here blocks, reverses, or issues a
plant command. Detection only describes what it observed; the engineer
acknowledges and decides.

## Source

```mermaid
sequenceDiagram
    actor Operator as Operator
    participant Dashboard as Dashboard
    participant API as FastAPI
    participant Runner as run_scenario_and_persist
    participant Sim as Simulator
    participant Collector as EventCollector
    participant EStore as EventStore
    participant Detect as detect()
    participant AStore as AlertStore
    participant Bus as ChangeBus
    participant Stream as SSE stream

    Operator->>Dashboard: select scenario + seed
    Dashboard->>API: POST /scenarios/{id}/run
    API->>Runner: run_scenario_and_persist()
    Runner->>Sim: run_scenario(on_command)
    loop per applied command
        Sim->>Runner: on_command(command, state)
        Runner->>Collector: record(state, command)
        Collector->>EStore: append(event)
        Runner->>Detect: detect(event, history)
        Note over Detect: 5 layers: invariants, transitions, replay, rate/drift, baseline
        Detect-->>Runner: alerts
        Runner->>AStore: upsert(alerts)
        Runner->>Runner: history.append(event)
    end
    Sim-->>Runner: result + fingerprint
    Runner-->>API: summary
    API->>Bus: publish()
    Bus->>Stream: wake subscribers
    Stream->>EStore: re-read events + plant
    Stream->>AStore: re-read alerts
    Stream-->>Dashboard: update frame
    Dashboard-->>Operator: events + alerts render
    Operator->>Dashboard: acknowledge alert
    Dashboard->>API: PATCH /alerts/{id}/ack
    API->>AStore: acknowledge(id)
    API->>Bus: publish()
    Bus->>Stream: wake subscribers
    Stream-->>Dashboard: update frame
```

## Re-rendering

`sequence.png` is rendered from the Mermaid block above via
[kroki.io](https://kroki.io). To regenerate:

```bash
# 1. Extract the fenced Mermaid block to /tmp/sequence.mmd
.venv/bin/python -c "
import pathlib, re
text = pathlib.Path('docs/sequence.md').read_text()
m = re.search(r'\`\`\`mermaid\n(.*?)\n\`\`\`', text, re.DOTALL)
pathlib.Path('/tmp/sequence.mmd').write_text(m.group(1) + '\n')
"
# 2. Render through Kroki (diagram is zlib-compressed + base64url-encoded)
.venv/bin/python -c "
import base64, pathlib, zlib
src = pathlib.Path('/tmp/sequence.mmd').read_text()
enc = base64.urlsafe_b64encode(zlib.compress(src.encode(), 9)).decode()
pathlib.Path('/tmp/kroki_seq_url.txt').write_text(f'https://kroki.io/mermaid/png/{enc}')
"
curl -S --max-time 120 -o docs/sequence.png "$(cat /tmp/kroki_seq_url.txt)"
```
