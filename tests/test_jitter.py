"""Tests for deterministic attack timing-jitter variants."""

from safeco.scenarios import (
    ATTACK_JITTER_SCENARIOS,
    ATTACK_SCENARIOS,
    run_scenario,
    scenario_fingerprint,
)

JITTER_IDS = (
    "attack_injection_jitter_01",
    "attack_replay_jitter_01",
    "attack_mistimed_jitter_01",
    "attack_drift_jitter_01",
)

BASE_IDS = {
    "attack_injection_jitter_01": "attack_injection_01",
    "attack_replay_jitter_01": "attack_replay_01",
    "attack_mistimed_jitter_01": "attack_mistimed_01",
    "attack_drift_jitter_01": "attack_drift_01",
}


def command_payloads(result) -> list[tuple[str, float | int, str]]:
    """Return the ordered command payloads of a scenario result."""
    return [(c.target, c.value, c.kind) for c in result.commands]


def test_jitter_variants_registered_separately():
    assert set(JITTER_IDS) <= set(ATTACK_JITTER_SCENARIOS)
    assert set(JITTER_IDS).isdisjoint(ATTACK_SCENARIOS)


def test_jitter_variants_are_attacks():
    for variant in JITTER_IDS:
        base = BASE_IDS[variant]
        assert (
            run_scenario(variant, seed=42).ground_truth
            == run_scenario(base, seed=42).ground_truth
        )


def test_jitter_variants_are_deterministic_from_seed():
    for variant in JITTER_IDS:
        a = scenario_fingerprint(run_scenario(variant, seed=42))
        b = scenario_fingerprint(run_scenario(variant, seed=42))
        assert a == b
        assert a != scenario_fingerprint(run_scenario(variant, seed=43))


def test_jitter_changes_timing_but_keeps_commands():
    for variant in JITTER_IDS:
        base = BASE_IDS[variant]
        base_result = run_scenario(base, seed=42)
        jitter_result = run_scenario(variant, seed=42)
        assert command_payloads(base_result) == command_payloads(jitter_result)
        assert len(base_result.commands) == len(jitter_result.commands)
        assert scenario_fingerprint(base_result) != scenario_fingerprint(jitter_result)


def test_jitter_preserves_attack_violations():
    for variant in JITTER_IDS:
        base = BASE_IDS[variant]
        base_violations = run_scenario(base, seed=42).violations
        jitter_violations = run_scenario(variant, seed=42).violations
        assert jitter_violations == base_violations
