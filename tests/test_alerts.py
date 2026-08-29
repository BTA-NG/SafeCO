import json

import pytest

from safeco.alerts import (
    CONTRACT_FIELDS,
    SEVERITY_RANK,
    TEMPLATES,
    Alert,
    AlertContractError,
    ReasonCode,
    Severity,
    build_alert,
    derive_alert_id,
)


def test_every_reason_code_has_a_template():
    assert set(TEMPLATES) == set(ReasonCode)


def test_every_template_is_engineer_facing():
    for reason_code, template in TEMPLATES.items():
        assert template.title, reason_code
        assert template.explanation, reason_code
        assert template.recommended_action, reason_code
        assert 0.0 <= template.confidence <= 1.0, reason_code


def test_recommended_actions_never_claim_safeco_acted():
    # SafeCO is advisory. The interface must never imply it stopped equipment.
    forbidden = ("safeco stopped", "safeco has blocked", "automatically stopped")
    for reason_code, template in TEMPLATES.items():
        action = template.recommended_action.lower()
        for phrase in forbidden:
            assert phrase not in action, (reason_code, phrase)


def test_to_dict_uses_the_frozen_contract_field_order():
    alert = build_alert(
        "event-1",
        ReasonCode.PUMP_ACTIVE_DURING_RECOVERY,
        {},
    )
    assert tuple(alert.to_dict()) == CONTRACT_FIELDS


def test_to_dict_is_json_serialisable_with_plain_strings():
    alert = build_alert("event-1", ReasonCode.PUMP_ACTIVE_DURING_RECOVERY, {})
    payload = json.loads(alert.canonical_json())
    assert payload["reason_code"] == "pump_active_during_recovery"
    assert payload["severity"] == "high"
    assert payload["acknowledged"] is False


def test_alert_id_is_derived_and_idempotent():
    first = build_alert("event-1", ReasonCode.PUMP_ACTIVE_DURING_RECOVERY, {})
    second = build_alert("event-1", ReasonCode.PUMP_ACTIVE_DURING_RECOVERY, {})
    assert first.alert_id == second.alert_id
    assert first.alert_id == derive_alert_id(
        "event-1", ReasonCode.PUMP_ACTIVE_DURING_RECOVERY
    )


def test_alert_id_separates_events_and_reason_codes():
    same_event_other_code = derive_alert_id("event-1", ReasonCode.UNSAFE_PUMP_START)
    other_event_same_code = derive_alert_id(
        "event-2", ReasonCode.PUMP_ACTIVE_DURING_RECOVERY
    )
    baseline = derive_alert_id("event-1", ReasonCode.PUMP_ACTIVE_DURING_RECOVERY)
    assert len({baseline, same_event_other_code, other_event_same_code}) == 3


def test_explicit_alert_id_is_preserved():
    alert = Alert(
        event_id="event-1",
        reason_code=ReasonCode.UNSAFE_PUMP_START,
        severity=Severity.HIGH,
        title="t",
        explanation="e",
        alert_id="supplied",
    )
    assert alert.alert_id == "supplied"


def test_acknowledge_returns_a_new_alert():
    alert = build_alert("event-1", ReasonCode.PUMP_ACTIVE_DURING_RECOVERY, {})
    acknowledged = alert.acknowledge()
    assert acknowledged.acknowledged is True
    assert alert.acknowledged is False
    assert acknowledged.alert_id == alert.alert_id


def test_explanation_renders_observed_values():
    alert = build_alert(
        "event-1",
        ReasonCode.UNSAFE_PUMP_START,
        {"tank_level": 72.0501, "mode": "running"},
    )
    assert "72.05%" in alert.explanation
    assert "running mode" in alert.explanation


def test_missing_evidence_key_raises_a_named_error():
    with pytest.raises(AlertContractError, match="tank_level"):
        build_alert("event-1", ReasonCode.UNSAFE_PUMP_START, {"mode": "running"})


def test_unknown_reason_code_raises():
    with pytest.raises(AlertContractError, match="no alert template"):
        build_alert("event-1", "not_a_reason_code", {})


def test_out_of_range_confidence_raises():
    with pytest.raises(AlertContractError, match="0.0 to 1.0"):
        build_alert(
            "event-1",
            ReasonCode.PUMP_ACTIVE_DURING_RECOVERY,
            {},
            confidence=1.5,
        )


def test_severity_overrides_are_honoured():
    alert = build_alert(
        "event-1",
        ReasonCode.PUMP_ACTIVE_DURING_RECOVERY,
        {},
        severity=Severity.CRITICAL,
        confidence=0.5,
    )
    assert alert.severity is Severity.CRITICAL
    assert alert.confidence == 0.5


def test_severity_rank_covers_and_orders_every_severity():
    assert set(SEVERITY_RANK) == set(Severity)
    ranked = sorted(Severity, key=lambda s: SEVERITY_RANK[s])
    assert ranked == [
        Severity.LOW,
        Severity.MEDIUM,
        Severity.HIGH,
        Severity.CRITICAL,
    ]


def test_evidence_is_copied_not_aliased():
    evidence = {"tank_level": 10.0, "mode": "running"}
    alert = build_alert("event-1", ReasonCode.UNSAFE_PUMP_START, evidence)
    evidence["tank_level"] = 999.0
    assert alert.evidence["tank_level"] == 10.0
