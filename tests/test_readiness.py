from conftest import EXAMPLE_EVENT_ID

from evidence_hub import readiness, registry, service
from evidence_hub.schemas import EvidenceUpdateRequest, UpdateStatus


def _resolve(store, gap):
    registry.record_update(store, EvidenceUpdateRequest(
        decision_id=EXAMPLE_EVENT_ID, gap=gap, owner="Data Governance",
        action=f"Attach {gap}", status=UpdateStatus.in_progress,
    ))
    registry.record_update(store, EvidenceUpdateRequest(
        decision_id=EXAMPLE_EVENT_ID, gap=gap, owner="Data Governance",
        action=f"Verify {gap}", status=UpdateStatus.verified,
    ))


def test_readiness_improves_as_gaps_resolve(store, source):
    before = service.evaluate_decision(store, source, EXAMPLE_EVENT_ID)
    view0 = readiness.build_readiness(store, EXAMPLE_EVENT_ID)
    assert "data_lineage_reference" in view0.open_gaps
    assert "data_lineage_reference" not in view0.resolved_gaps

    _resolve(store, "data_lineage_reference")
    view1 = readiness.build_readiness(store, EXAMPLE_EVENT_ID)

    assert "data_lineage_reference" in view1.resolved_gaps
    assert "data_lineage_reference" not in view1.open_gaps
    assert view1.audit_readiness_score > before.audit_readiness_score


def test_active_remediation_items_listed(store, source):
    service.evaluate_decision(store, source, EXAMPLE_EVENT_ID)
    registry.record_update(store, EvidenceUpdateRequest(
        decision_id=EXAMPLE_EVENT_ID, gap="policy_check_reference", owner="Compliance",
        action="Attach OPA decision", status=UpdateStatus.in_progress,
    ))

    view = readiness.build_readiness(store, EXAMPLE_EVENT_ID)
    gaps = {item.gap for item in view.active_remediation_items}
    assert "policy_check_reference" in gaps


def test_no_evaluation_returns_none(store):
    assert readiness.build_readiness(store, "does-not-exist") is None
