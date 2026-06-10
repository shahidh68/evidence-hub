import pytest

from evidence_hub import registry
from evidence_hub.schemas import ArtifactType, EvidenceUpdateRequest, UpdateStatus

DECISION = "a92ffa42-27a8-4e46-81d6-b9b1a654077f"


def _req(gap, status, **kw):
    return EvidenceUpdateRequest(
        decision_id=DECISION, gap=gap, owner="Data Governance",
        action=f"Attach {gap}", status=status, **kw,
    )


def test_updates_are_append_only(session):
    registry.record_update(session, _req("data_lineage_reference", UpdateStatus.in_progress))
    registry.record_update(session, _req("data_lineage_reference", UpdateStatus.verified))
    session.commit()

    updates = registry.list_updates(session, DECISION)
    # Both rows persist; nothing is overwritten.
    assert len(updates) == 2
    assert [u.status for u in updates] == [UpdateStatus.in_progress, UpdateStatus.verified]


def test_resolved_gaps_reflect_latest_status(session):
    registry.record_update(session, _req("policy_check_reference", UpdateStatus.in_progress))
    registry.record_update(session, _req("policy_check_reference", UpdateStatus.verified))
    session.commit()
    assert "policy_check_reference" in registry.resolved_gaps(session, DECISION)


def test_illegal_transition_rejected(session):
    registry.record_update(session, _req("model_registry_reference", UpdateStatus.open))
    session.commit()
    # open -> verified is not a legal jump (must go through in_progress/submitted).
    with pytest.raises(registry.InvalidTransition):
        registry.record_update(session, _req("model_registry_reference", UpdateStatus.verified))


def test_first_update_cannot_start_closed(session):
    with pytest.raises(registry.InvalidTransition):
        registry.record_update(session, _req("model_approval_reference", UpdateStatus.closed))
