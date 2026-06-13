import json
import os

from conftest import EXAMPLE_EVENT_ID, FIXTURES_DIR

from evidence_hub.evaluator import evaluate
from evidence_hub.normalizer import normalize


def _normalized(event_id):
    with open(os.path.join(FIXTURES_DIR, f"{event_id}.json"), encoding="utf-8") as fh:
        payload = json.load(fh)
    return normalize(payload["record"], payload.get("tamper"))


def test_spec_example_scores_partial():
    event, issues = _normalized(EXAMPLE_EVENT_ID)
    result = evaluate(event, issues)

    # Spec worked example: integrity-verified but only partially audit-ready (~45).
    assert result.evidence_status.value == "partial"
    assert 30 < result.audit_readiness_score <= 70
    assert result.integrity_status.value == "verified"


def test_spec_example_missing_evidence():
    event, issues = _normalized(EXAMPLE_EVENT_ID)
    result = evaluate(event, issues)

    expected_missing = {
        "model_registry_reference",
        "model_approval_reference",
        "data_lineage_reference",
        "data_quality_check_reference",
        "policy_check_reference",
        "monitoring_snapshot_reference",
        "human_review_rationale",
    }
    assert expected_missing.issubset(set(result.missing_evidence))
    assert "input_data_hash" in result.present_evidence
    assert "system_prompt_hash" in result.present_evidence


def test_model_name_is_present_when_model_version_identifies_model():
    event, issues = _normalized("11111111-1111-4111-8111-111111111111")
    result = evaluate(event, issues)

    assert "model_name" in result.present_evidence
    assert "model_name" not in result.missing_evidence
    assert "model_version" in result.present_evidence


def test_event_governance_fields_count_as_present_evidence():
    with open(os.path.join(FIXTURES_DIR, "11111111-1111-4111-8111-111111111111.json"),
              encoding="utf-8") as fh:
        payload = json.load(fh)

    payload["record"]["ai_decision_output"].update({
        "model_registry_reference": "mlflow:model:claims-risk-model:12",
        "model_approval_reference": "change-ticket:CR-4471",
        "data_lineage_reference": "atlas:lineage:dataset_12345",
        "data_quality_check_reference": "great-expectations:run_67890",
        "policy_check_reference": "opa:policy:loan-triage",
        "policy_result": "pass",
        "policy_version": "2026.06",
        "monitoring_snapshot_reference": "monitoring:snapshot:2026-06-13",
        "drift_status": "within_threshold",
        "performance_status": "within_threshold",
        "prompt_version_reference": "git:prompts/triage.md@a1b2c3",
        "privacy_classification": "pseudonymised",
        "retention_classification": "7y",
    })

    event, issues = normalize(payload["record"], payload.get("tamper"))
    result = evaluate(event, issues)

    for key in {
        "model_registry_reference",
        "model_approval_reference",
        "data_lineage_reference",
        "data_quality_check_reference",
        "policy_check_reference",
        "policy_result",
        "policy_version",
        "monitoring_snapshot_reference",
        "drift_status",
        "performance_status",
        "prompt_version_reference",
        "privacy_classification",
        "retention_classification",
    }:
        assert key in result.present_evidence
        assert key not in result.missing_evidence


def test_recommended_actions_have_owners():
    event, issues = _normalized(EXAMPLE_EVENT_ID)
    result = evaluate(event, issues)
    owners = {a.action: a.owner for a in result.recommended_actions}
    assert any("model_registry_reference" in a for a in owners)
    # Model gaps route to ModelOps, policy to Compliance.
    model_action = next(a for a in result.recommended_actions
                        if "model_registry_reference" in a.action)
    assert model_action.owner == "ModelOps"
