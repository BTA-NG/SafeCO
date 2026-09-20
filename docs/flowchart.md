# SafeCO End-to-End Flow

Detailed data and control flow, from scenario scripts through detection to the
operator dashboard. For the high-level overview, see `docs/architecture.png`
(embedded in the README's "How It Works" section).

![SafeCO end-to-end flowchart](flowchart.png)

Solid arrows are data flow; dotted arrows are control signals and
secondary/offline paths. SafeCO stays advisory throughout: nothing in this
chart blocks, reverses, or issues a plant command — the detector only
describes what it observed, and a human decides.

## Source

```mermaid
flowchart TD
    subgraph SIM["Simulate"]
        SCN["Scenario scripts<br/>normal · benign · attack · jitter"]
        PLANT["PlantSimulator<br/>deterministic physics · seed"]
        MODBUS["Modbus TCP server<br/>localhost:5020 · writes validated"]
        SCN -->|"drives"| PLANT
        PLANT -->|"exposes registers"| MODBUS
    end

    subgraph INGEST["Collect"]
        COLL["EventCollector<br/>normalised Event contract"]
        ESTORE[("EventStore<br/>SQLite WAL · SHA-256 hash chain")]
        COLL -->|"append"| ESTORE
    end

    subgraph DETECT["Detect · detect(event, history)"]
        direction TB
        L1["1 · Safety invariants<br/>pump/valve · power · limits"]
        L2["2 · Mode transitions<br/>legal edges · recovery order"]
        L3["3 · Replay<br/>same command · changed context"]
        L4["4 · Rate + setpoint drift<br/>write bursts · cumulative drift"]
        L5["5 · Statistical baseline<br/>median/MAD · optional profile"]
        L1 --> L2 --> L3 --> L4 --> L5
    end

    subgraph SERVE["Serve"]
        ASTORE[("AlertStore<br/>separate SQLite DB")]
        API["FastAPI<br/>health · plant · events · alerts · scenarios"]
        SSE["SSE stream /api/stream<br/>snapshot then push on change"]
        BUS["ChangeBus<br/>state-changed notifications"]
        DASH["Operator dashboard<br/>no-build HTML/CSS/JS"]
        ASTORE --> API
        ESTORE -->|"reads"| API
        API -->|"serves"| SSE
        SSE -->|"snapshot + updates"| DASH
        DASH -->|"POST run · PATCH ack"| API
        API -.->|"publish on write"| BUS
        BUS -.->|"wake streams"| SSE
    end

    EVAL["Evaluation harness<br/>held-out replay → metrics"]

    PLANT -->|"on_command seam"| COLL
    MODBUS -.->|"validated client writes"| PLANT
    API -->|"run_scenario_and_persist"| SCN
    ESTORE -->|"event + history"| DETECT
    DETECT -->|"upsert alerts"| ASTORE
    SCN -.->|"held-out scenarios"| EVAL
    EVAL -.->|"replay through detect()"| DETECT
```

## Re-rendering

`flowchart.png` is rendered from the Mermaid block above via
[kroki.io](https://kroki.io) (mermaid-cli also works but needs a local
Chrome for Puppeteer). To regenerate:

```bash
# 1. Extract the fenced Mermaid block to /tmp/flowchart.mmd
.venv/bin/python -c "
import pathlib, re
text = pathlib.Path('docs/flowchart.md').read_text()
m = re.search(r'\`\`\`mermaid\n(.*?)\n\`\`\`', text, re.DOTALL)
pathlib.Path('/tmp/flowchart.mmd').write_text(m.group(1) + '\n')
"
# 2. Render through Kroki (diagram is zlib-compressed + base64url-encoded)
.venv/bin/python -c "
import base64, pathlib, zlib
src = pathlib.Path('/tmp/flowchart.mmd').read_text()
enc = base64.urlsafe_b64encode(zlib.compress(src.encode(), 9)).decode()
pathlib.Path('/tmp/kroki_url.txt').write_text(f'https://kroki.io/mermaid/png/{enc}')
"
curl -S --max-time 120 -o docs/flowchart.png "$(cat /tmp/kroki_url.txt)"
```
