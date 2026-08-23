# Adupe Municipal Water Station Plant Contract

Adupe is a fictional, representative Nigerian municipal water facility. It is not a digital twin of any named facility. The model contains one storage tank, inlet pump, inlet valve, outlet valve, level/flow telemetry, operating mode, power source, target level and high-level limit.

## Register map

| Address | Type | Name | Encoding |
|---:|---|---|---|
| 0 | Coil R/W | Pump command | 0 off, 1 on |
| 1 | Coil R/W | Inlet valve command | 0 closed, 1 open |
| 2 | Coil R/W | Outlet valve command | 0 closed, 1 open |
| 100 | Input R | Tank level | percent x 100 |
| 101 | Input R | Net flow | signed engineering value x 100 |
| 102 | Input R | Pump state | 0 off, 1 on |
| 103 | Input R | Inlet valve state | 0 closed, 1 open |
| 104 | Input R | Outlet valve state | 0 closed, 1 open |
| 105 | Input R | Operating mode | enum in plant.py |
| 106 | Input R | Power source | enum in plant.py |
| 200 | Holding R/W | Target level | percent x 100 |
| 201 | Holding R/W | High-level limit | percent x 100 |
| 202 | Holding R/W | Mode command | enum in plant.py |

## Safety and detection semantics

- Starting the pump with the inlet valve closed is a valid Modbus command but an unsafe process action.
- A tank above its configured high-level limit during normal operation is unsafe.
- The target level must remain below the high-level limit.
- Gradual changes are evaluated cumulatively, not only one write at a time.
- Grid loss and a properly sequenced generator transfer are legitimate recovery activity.
- SafeCO observes and advises; the simulator still applies valid protocol commands so their consequences can be demonstrated.

## Demo scenarios

Normal: startup, steady demand, controlled shutdown, authorised setpoint maintenance, grid outage, generator recovery.

Attacks: injected pump command, old command replay, valid command in an unsafe state, slow high-level/setpoint drift.

## Normal scenario catalogue (foundation handoff)

Run any scenario with a fixed seed:

    PYTHONPATH=src .venv/bin/python - <<'EOF'
    from safeco.scenarios import run_scenario
    result = run_scenario("startup_01", seed=42)
    print(result.final_state)
    EOF

| Scenario ID | Ground truth | Expected outcome |
|---|---|---|
| startup_01 | normal | SHUTDOWN -> inlet open -> pump on -> RUNNING; no invariant violations; level rises |
| steady_running_01 | normal | 121 s pump duty cycle; level stays below high-level limit throughout |
| controlled_shutdown_01 | normal | pump off -> inlet closed -> demand drain -> SHUTDOWN; no violations |
| grid_recovery_01 | normal | grid loss -> pump stop -> RECOVERY -> generator transfer -> STARTUP -> RUNNING on GENERATOR; benign |

Snapshots carry a `phase` key matching the step names above. Every applied command is
available via `result.commands` / the simulator's `on_command` callback for downstream
collection. Each `ScenarioResult` records its seed and generator version so any dataset
can be regenerated exactly.
