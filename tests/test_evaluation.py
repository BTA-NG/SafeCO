from safeco.alerts import ReasonCode
from safeco.evaluation import (
    ATTACK_EVALUATION_SCENARIOS,
    BASELINE_TRAINING_SCENARIOS,
    BENIGN_EVALUATION_SCENARIOS,
    DEFAULT_EVALUATION_SCENARIOS,
    EXPECTED_ATTACK_ALERTS,
    HELD_OUT_SCENARIOS,
    TUNING_SCENARIOS,
    VALIDATION_SCENARIOS,
    compare_rule_and_baseline,
    evaluate_scenario,
    evaluate_scenarios,
    events_for_scenario,
    main,
    sample_evidence_pairs,
    train_baseline_for_evaluation,
)
from safeco.scenarios import ATTACK_SCENARIOS, NORMAL_SCENARIOS


def test_expected_attack_mapping_covers_all_attack_scenarios():
    assert set(EXPECTED_ATTACK_ALERTS) == set(ATTACK_SCENARIOS)


def test_evaluation_splits_do_not_overlap():
    splits = [set(TUNING_SCENARIOS), set(VALIDATION_SCENARIOS), set(HELD_OUT_SCENARIOS)]
    assert splits[0].isdisjoint(splits[1])
    assert splits[0].isdisjoint(splits[2])
    assert splits[1].isdisjoint(splits[2])


def test_every_split_scenario_exists():
    known = set(DEFAULT_EVALUATION_SCENARIOS)
    assert set(TUNING_SCENARIOS) <= known
    assert set(VALIDATION_SCENARIOS) <= known
    assert set(HELD_OUT_SCENARIOS) <= known


def test_default_baseline_training_excludes_validation_and_held_out_scenarios():
    profile = train_baseline_for_evaluation()
    assert set(profile.training_scenarios) == set(BASELINE_TRAINING_SCENARIOS)
    assert set(profile.training_scenarios).isdisjoint(VALIDATION_SCENARIOS)
    assert set(profile.training_scenarios).isdisjoint(HELD_OUT_SCENARIOS)
    assert set(profile.training_scenarios) <= set(NORMAL_SCENARIOS)


def test_default_evaluation_scenarios_cover_registries():
    assert set(BENIGN_EVALUATION_SCENARIOS) == set(NORMAL_SCENARIOS)
    assert set(ATTACK_EVALUATION_SCENARIOS) == set(ATTACK_SCENARIOS)
    assert set(DEFAULT_EVALUATION_SCENARIOS) == {
        *NORMAL_SCENARIOS,
        *ATTACK_SCENARIOS,
    }


def test_benign_scenarios_have_no_expected_attack_reason():
    for scenario_id in BENIGN_EVALUATION_SCENARIOS:
        result = evaluate_scenario(scenario_id)
        assert result.expected_reason_code is None
        assert result.detected_expected is False
        assert result.actionable_alert_count == 0


def test_each_attack_detects_expected_reason_code():
    profile = train_baseline_for_evaluation()
    for scenario_id, reason_code in EXPECTED_ATTACK_ALERTS.items():
        result = evaluate_scenario(scenario_id, baseline_profile=profile)
        assert result.expected_reason_code == reason_code
        assert result.detected_expected is True
        assert reason_code in result.reason_codes
        assert result.first_detection_sequence_id is not None
        assert result.first_detection_event_id is not None
        assert result.detection_latency_events is not None
        assert result.detection_latency_s is not None
        assert result.classification == "TP"


def test_evaluation_report_computes_recall_and_precision():
    profile = train_baseline_for_evaluation()
    report = evaluate_scenarios(baseline_profile=profile)
    assert report.recall == 1.0
    assert report.precision == 1.0
    assert report.false_alerts_per_normal_hour == 0.0
    assert report.missed_attacks == ()
    assert report.classification.true_positive == len(ATTACK_SCENARIOS)
    assert report.classification.false_positive == 0
    assert report.classification.false_negative == 0
    assert report.classification.true_negative == len(NORMAL_SCENARIOS)


def test_maintenance_false_positives_are_counted_separately():
    report = evaluate_scenarios(("maintenance_01",))
    assert report.maintenance_false_positives == 0


def test_events_for_scenario_is_deterministic(tmp_path):
    first = events_for_scenario(
        "attack_drift_01",
        seed=42,
        database=tmp_path / "first.db",
    )
    second = events_for_scenario(
        "attack_drift_01",
        seed=42,
        database=tmp_path / "second.db",
    )
    assert [
        (event.command, event.target, event.value, event.mode, event.sequence_id)
        for event in first.events
    ] == [
        (event.command, event.target, event.value, event.mode, event.sequence_id)
        for event in second.events
    ]


def test_evaluation_trace_timestamps_are_deterministic_and_monotonic(tmp_path):
    first = events_for_scenario(
        "extended_normal_01", seed=42, database=tmp_path / "a.db"
    )
    second = events_for_scenario(
        "extended_normal_01", seed=42, database=tmp_path / "b.db"
    )
    first_timestamps = [event.timestamp for event in first.events]
    assert first_timestamps == [event.timestamp for event in second.events]
    assert first_timestamps == sorted(first_timestamps)


def test_registered_anomaly_changes_evaluated_event_features(tmp_path):
    noisy = events_for_scenario(
        "benign_noise_01",
        seed=42,
        database=tmp_path / "noisy.db",
    )
    clean = events_for_scenario(
        "benign_noise_01",
        seed=42,
        database=tmp_path / "clean.db",
        anomaly_plan=[],
    )
    assert len(noisy.events) == len(clean.events) > 0
    assert [
        (event.command, event.target, event.value, event.mode, event.sequence_id)
        for event in noisy.events
    ] == [
        (event.command, event.target, event.value, event.mode, event.sequence_id)
        for event in clean.events
    ]
    assert noisy.event_elapsed_s == clean.event_elapsed_s
    assert [event.process.tank_level for event in noisy.events] != [
        event.process.tank_level for event in clean.events
    ]


def test_held_out_evaluation_runs_without_tuning_scenarios():
    report = evaluate_scenarios(HELD_OUT_SCENARIOS)
    assert {result.scenario_id for result in report.scenarios} == set(
        HELD_OUT_SCENARIOS
    )
    assert ReasonCode.RECOVERY_OUT_OF_SEQUENCE in {
        code for result in report.scenarios for code in result.reason_codes
    }


def test_rule_only_and_baseline_reports_are_separate():
    comparison = compare_rule_and_baseline()
    assert comparison.rules_only.detector_mode == "rules_only"
    assert comparison.with_baseline.detector_mode == "with_baseline"
    assert comparison.rules_only.recall < comparison.with_baseline.recall
    assert comparison.with_baseline.recall == 1.0
    assert comparison.rules_only.missed_attacks


def test_baseline_mode_still_detects_all_expected_rule_alerts():
    profile = train_baseline_for_evaluation()
    for scenario_id, reason_code in EXPECTED_ATTACK_ALERTS.items():
        result = evaluate_scenario(scenario_id, baseline_profile=profile)
        assert result.detector_mode == "with_baseline"
        assert reason_code in result.reason_codes


def test_baseline_only_scenarios_differ_between_modes():
    profile = train_baseline_for_evaluation()
    for scenario_id in (
        "attack_baseline_high_limit_01",
        "attack_baseline_low_tank_01",
        "attack_baseline_mode_context_01",
    ):
        rules_only = evaluate_scenario(scenario_id)
        with_baseline = evaluate_scenario(scenario_id, baseline_profile=profile)
        assert rules_only.classification == "FN"
        assert ReasonCode.BASELINE_DEVIATION not in rules_only.reason_codes
        assert with_baseline.classification == "TP"
        assert ReasonCode.BASELINE_DEVIATION in with_baseline.reason_codes


def test_sample_evidence_pairs_include_event_and_alert():
    samples = sample_evidence_pairs(("attack_drift_01",))
    assert set(samples) == {"attack_drift_01"}
    assert samples["attack_drift_01"]["event"]["scenario_id"] == "attack_drift_01"
    assert samples["attack_drift_01"]["alert"]["reason_code"] == "setpoint_drift"


def test_cli_defaults_to_baseline(capsys):
    assert main([]) == 0
    output = capsys.readouterr().out
    assert "Mode: with_baseline" in output
    assert "Scenario table:" in output
    assert "scenario_id" in output
    assert "-+-" in output
    assert "attack_baseline_mode_context_01" in output
    assert " | baseline_anomaly | " in output


def test_cli_without_baseline_opts_out(capsys):
    assert main(["--without-baseline"]) == 0
    output = capsys.readouterr().out
    assert "Mode: rules_only" in output


def test_cli_can_emit_json(capsys):
    assert main(["--without-baseline", "--held-out", "--json"]) == 0
    output = capsys.readouterr().out
    assert '"detector_mode": "rules_only"' in output
    assert '"classification"' in output


def test_cli_can_emit_sample_json(capsys):
    assert main(["--without-baseline", "--samples-json"]) == 0
    output = capsys.readouterr().out
    assert '"attack_drift_01"' in output
    assert '"event"' in output
    assert '"alert"' in output
