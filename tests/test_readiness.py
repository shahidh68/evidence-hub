from conftest import EXAMPLE_EVENT_ID

from evidence_hub import readiness, registry, service
from evidence_hub.schemas import EvidenceUpdateRequest, UpdateStatus


def _resolve(session, gap):
    registry.record_update(session, EvidenceUpdateRequest(
        decision_id=EXAMPLE_EVENT_ID, gap=gap, owner="Data Governance",
        action=f"Attach {gap}", status=UpdateStatus.in_progress,
    ))
    registry.record_update(session, EvidenceUpdateRequest(
        decision_id=EXAMPLE_EVENT_ID, gap=gap, owner="Data Governance",
        action=f"Verify {gap}", status=UpdateStatus.verified,
    ))
    session.commit()


def test_readiness_improves_as_gaps_resolve(session, source):
    before = service.evaluate_decision(session, source, EXAMPLE_EVENT_ID)
    view0 = readiness.build_readiness(session, EXAMPLE_EVENT_ID)
    assert "data_lineage_reference" in view0.open_gaps
    assert "data_lineage_reference" not in view0.resolved_gaps

    _resolve(session, "data_lineage_reference")
    view1 = readiness.build_readiness(session, EXAMPLE_EVENT_ID)

    assert "data_lineage_reference" in view1.resolved_gaps
    assert "data_lineage_reference" not in view1.open_gaps
    assert view1.audit_readiness_score > before.audit_readiness_score


def test_active_remediation_items_listed(session, source):
    service.evaluate_decision(session, source, EXAMPLE_EVENT_ID)
    registry.record_update(session, EvidenceUpdateRequest(
        decision_id=EXAMPLE_EVENT_ID, gap="policy_check_reference", owner="Compliance",
        action="Attach OPA decision", status=UpdateStatus.in_progress,
    ))
    session.commit()

    view = readiness.build_readiness(session, EXAMPLE_EVENT_ID)
    gaps = {item.gap for item in view.active_remediation_items}
    assert "policy_check_reference" in gaps


def test_no_evaluation_returns_none(session):
    assert readiness.build_readiness(session, "does-not-exist") is None
