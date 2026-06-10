"""Per-decision JSON audit pack generator (spec sections 5.6, 9.6).

Assembles a single exportable package from everything the Hub knows about a
decision: the ledger record, tamper-evidence, normalized event, evidence
evaluation, current readiness, remediation history, and the evidence graph.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from . import graph, readiness, registry
from .db import LedgerEventSnapshot, NormalizedDecisionEventRow
from .schemas import AuditPack, EvidenceStatus, NormalizedDecisionEvent


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class AuditPackError(RuntimeError):
    pass


def _latest_snapshot(session, decision_id: str) -> LedgerEventSnapshot | None:
    return (
        session.query(LedgerEventSnapshot)
        .filter(LedgerEventSnapshot.decision_id == decision_id)
        .order_by(LedgerEventSnapshot.id.desc())
        .first()
    )


def _latest_normalized(session, decision_id: str) -> NormalizedDecisionEvent | None:
    row = (
        session.query(NormalizedDecisionEventRow)
        .filter(NormalizedDecisionEventRow.decision_id == decision_id)
        .order_by(NormalizedDecisionEventRow.id.desc())
        .first()
    )
    return NormalizedDecisionEvent.model_validate(row.payload) if row else None


def build_audit_pack(session, decision_id: str) -> AuditPack:
    snapshot = _latest_snapshot(session, decision_id)
    normalized = _latest_normalized(session, decision_id)
    evaluation = readiness.latest_evaluation(session, decision_id)
    if snapshot is None or normalized is None or evaluation is None:
        raise AuditPackError(
            f"decision {decision_id!r} has not been evaluated yet; call /evidence/evaluate first"
        )

    view = readiness.build_readiness(session, decision_id)
    updates = registry.list_updates(session, decision_id)
    edges = graph.build_graph(session, normalized)

    sections = {
        "decision_summary": {
            "decision_id": decision_id,
            "event_type": normalized.event_type,
            "timestamp_utc": normalized.timestamp_utc,
            "tenant_id": normalized.tenant_id,
            "outcome": normalized.decision.outcome,
            "human_in_loop": normalized.human_in_loop,
        },
        "ledger_record": snapshot.record,
        "tamper_evidence": snapshot.tamper,
        "human_review": normalized.decision.model_dump(),
        "model_evidence": normalized.model.model_dump(),
        "data_evidence": normalized.input.model_dump(),
        "prompt_evidence": normalized.prompt.model_dump(),
        "controls": normalized.controls.model_dump(),
        "linked_events": normalized.based_on.model_dump(),
        "evidence_evaluation": evaluation.model_dump(),
        "open_gaps": view.open_gaps if view else evaluation.missing_evidence,
        "remediation_history": [u.model_dump(mode="json") for u in updates],
        "evidence_graph": [e.model_dump(by_alias=True) for e in edges],
    }

    readiness_status = view.current_evidence_status if view else evaluation.evidence_status
    return AuditPack(
        audit_pack_id=f"apack-{uuid.uuid4().hex[:10]}",
        status="generated",
        scope="per_decision",
        decision_id=decision_id,
        format="json",
        generated_at=_now(),
        readiness_status=EvidenceStatus(readiness_status),
        sections=sections,
    )
