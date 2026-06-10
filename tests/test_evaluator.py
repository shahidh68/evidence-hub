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


def test_recommended_actions_have_owners():
    event, issues = _normalized(EXAMPLE_EVENT_ID)
    result = evaluate(event, issues)
    owners = {a.action: a.owner for a in result.recommended_actions}
    assert any("model_registry_reference" in a for a in owners)
    # Model gaps route to ModelOps, policy to Compliance.
    model_action = next(a for a in result.recommended_actions
                        if "model_registry_reference" in a.action)
    assert model_action.owner == "ModelOps"
