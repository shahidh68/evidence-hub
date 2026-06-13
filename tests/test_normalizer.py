import json
import os

from conftest import EXAMPLE_EVENT_ID, FIXTURES_DIR

from evidence_hub.normalizer import normalize


def _load(event_id):
    with open(os.path.join(FIXTURES_DIR, f"{event_id}.json"), encoding="utf-8") as fh:
        payload = json.load(fh)
    return payload["record"], payload.get("tamper")


def test_extracts_fields_from_ai_decision_output():
    record, tamper = _load(EXAMPLE_EVENT_ID)
    event, issues = normalize(record, tamper)

    assert event.decision.outcome == "approved"
    assert event.based_on.triage_event_id == "837c7889-2e27-4d1e-a4f5-ed68dce337a8"
    assert event.based_on.risk_event_id == "a0d2f06c-1a89-4d9a-8a18-360ea2eefe9f"
    assert event.input.input_data_hash.startswith("f8a0ab77")
    assert event.prompt.system_prompt_hash.startswith("c28dd58c")


def test_flags_reviewer_metadata_in_model_version():
    record, tamper = _load(EXAMPLE_EVENT_ID)
    event, issues = normalize(record, tamper)

    assert any(i.field == "model_version" for i in issues)
    # Reviewer name is recovered and model_version is treated as absent.
    assert event.decision.reviewer.name == "Shahid Hamid"
    assert event.model.model_version is None
    assert event.event_type == "human_review_decision"


def test_integrity_block_from_tamper_result():
    record, tamper = _load(EXAMPLE_EVENT_ID)
    event, _ = normalize(record, tamper)
    assert event.archive.integrity_status.value == "verified"
    assert event.archive.tamper_evidence is True
    assert event.archive.archive_type == "immutable_s3"


def test_clean_ai_decision_has_no_model_version_issue():
    record, tamper = _load("11111111-1111-4111-8111-111111111111")
    event, issues = normalize(record, tamper)
    assert event.model.model_name == "claims-risk-model"
    assert event.model.model_version == "claims-risk-model:12"
    assert not any(i.field == "model_version" for i in issues)
    assert event.event_type == "ai_decision"


def test_explicit_model_name_overrides_derived_name():
    record, tamper = _load("11111111-1111-4111-8111-111111111111")
    record["ai_decision_output"]["model_name"] = "consumer-credit-risk"
    event, issues = normalize(record, tamper)

    assert event.model.model_name == "consumer-credit-risk"
    assert event.model.model_version == "claims-risk-model:12"
    assert not any(i.field == "model_version" for i in issues)


def test_extracts_governance_references_from_ai_decision_output():
    record, tamper = _load("11111111-1111-4111-8111-111111111111")
    record["ai_decision_output"].update({
        "policy_check_reference": "opa:policy:loan-triage",
        "policy_result": "pass",
        "policy_version": "2026.06",
        "monitoring_snapshot_reference": "monitoring:snapshot:2026-06-13",
        "drift_status": "within_threshold",
        "performance_status": "within_threshold",
        "fairness_test_reference": "fairness:test:run-42",
        "override_flag": False,
        "retention_classification": "7y",
    })

    event, issues = normalize(record, tamper)

    assert event.controls.policy_check_reference == "opa:policy:loan-triage"
    assert event.controls.policy_result == "pass"
    assert event.controls.policy_version == "2026.06"
    assert event.controls.monitoring_snapshot_reference == "monitoring:snapshot:2026-06-13"
    assert event.controls.drift_status == "within_threshold"
    assert event.controls.performance_status == "within_threshold"
    assert event.controls.fairness_test_reference == "fairness:test:run-42"
    assert event.controls.override_flag is False
    assert event.controls.retention_classification == "7y"
    assert not any(i.field == "model_version" for i in issues)
