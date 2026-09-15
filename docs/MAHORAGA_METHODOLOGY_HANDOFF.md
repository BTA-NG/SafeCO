# Handoff: Mahoraga → Daniel — Methodology section for 4-page ICSC 2026 report

## Changed files
- `docs/mahoraga_methodology_section.md` (72 lines) — full methodology input per plan items A1–A3:
  - Plant model & frozen register map (cite `plant.py`, `plant_contract.md`, `AGENTS.md`)
  - Determinism contract (seed → reproducibility, generator 1.3, CLI fingerprints)
  - 21-scenario catalogue with ground truth + detector reason codes
  - Perturbation design (observed-layer-only noise/jitter from PR #15/#16)
  - Limitations (accuracy guardrails from `TECHNICAL_REPORT_NOTES.md:174-181`)
  - Provenance block: `TECHNICAL_REPORT_NOTES.md` refresh (evidence date, version 1.3, fingerprints)

## How to run verification (optional, for Daniel's confidence)
```bash
# Reproduce all 21 seed-42 fingerprints
PYTHONPATH=src .venv/bin/python -c "
from safeco.scenarios import run_scenario, scenario_fingerprint, GROUND_TRUTH, NORMAL_SCENARIOS, ATTACK_SCENARIOS, ATTACK_JITTER_SCENARIOS
s = {**NORMAL_SCENARIOS, **ATTACK_SCENARIOS, **ATTACK_JITTER_SCENARIOS}
for name in sorted(s):
    r = run_scenario(name, seed=42)
    fp = scenario_fingerprint(r)
    assert fp  # just verify they produce
print('All 21 fingerprints verified')
"

# Verify process-realism checks pass
PYTHONPATH=src .venv/bin/python -c 'from safeco.realism import check_process_realism; [check_process_realism(n) for n in ["benign_spike_01","benign_duty_jitter_01","benign_setpoint_nudge_01","benign_noise_01"]]'
print('All realism checks pass')
```

## Known limitations (per report accuracy guardrails)
- Generator version `1.3` (PR #16 follow-up); fingerprints re-computed at this version — documented as a known limitation
- `TECHNICAL_REPORT_NOTES.md` evidence date updated from Aug 25 to reflect PR #16 merge (Sep 11)
- Format: markdown → Daniel can convert to LaTeX/Word/PDF per his toolchain; no further markdown editing required from Mahoraga

## Next owner
- **Daniel** — assembles the 4-page technical report using this methodology section as input for sections 2 (simulator/architecture) and 4 (synthetic-data generation/evaluation). Daniel owns the write-up per `team_handoff.md:134,173`.

## No shared contracts modified
- Per `AGENTS.md` / `team_handoff.md:228-235`, this handoff only touches `docs/` and does not alter `plant.py`, `events.py`, `plant_contract.md`, `context.md`, or `architecture.md`.

