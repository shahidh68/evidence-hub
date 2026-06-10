"""Current readiness roll-up (spec sections 5.4, 6.5).

Recomputed on demand from the latest evaluation plus the append-only evidence
updates for a decision. Resolved gaps add back their marginal weight to the score.
"""

from __future__ import annotations

from . import catalog, registry
from .db import EvidenceEvaluationRow, EvidenceUpdateRow
from .schemas import (
    EvidenceEvaluation,
    EvidenceReadinessView,
    EvidenceStatus,
    IntegrityStatus,
    RemediationItem,
    UpdateStatus,
)


def _marginal_weight(evidence_key: str) -> float:
    for cat in catalog.CATEGORIES:
        if evidence_key in cat.required:
            return cat.weight / len(cat.required)
    return 0.0


def latest_evaluation(session, decision_id: str) -> EvidenceEvaluation | None:
    row = (
        session.query(EvidenceEvaluationRow)
        .filter(EvidenceEvaluationRow.decision_id == decision_id)
        .order_by(EvidenceEvaluationRow.id.desc())
        .first()
    )
    return EvidenceEvaluation.model_validate(row.payload) if row else None


def build_readiness(session, decision_id: str) -> EvidenceReadinessView | None:
    evaluation = latest_evaluation(session, decision_id)
    if evaluation is None:
        return None

    resolved = registry.resolved_gaps(session, decision_id)
    missing = evaluation.missing_evidence

    open_gaps = [g for g in missing if g not in resolved]
    resolved_gaps = [g for g in missing if g in resolved]

    score = evaluation.audit_readiness_score + sum(_marginal_weight(g) for g in resolved_gaps)
    score = min(100, round(score))
    status = EvidenceStatus(catalog.status_for_score(score))

    # Active remediation = latest update per gap that isn't resolved.
    latest_by_gap: dict[str, RemediationItem] = {}
    for upd in registry.list_updates(session, decision_id):
        if upd.gap and upd.status not in registry.RESOLVED:
            latest_by_gap[upd.gap] = RemediationItem(
                gap=upd.gap, owner=upd.owner, status=upd.status, due_date=upd.due_date,
            )
    active_items = list(latest_by_gap.values())

    last_updated = _last_updated(session, decision_id, evaluation.evaluated_at)

    return EvidenceReadinessView(
        decision_id=decision_id,
        event_id=evaluation.event_id,
        tenant_id=None,
        current_evidence_status=status,
        audit_readiness_score=score,
        open_gaps=open_gaps,
        resolved_gaps=resolved_gaps,
        active_remediation_items=active_items,
        last_updated=last_updated,
        integrity_status=evaluation.integrity_status,
    )


def _last_updated(session, decision_id: str, fallback: str) -> str:
    row = (
        session.query(EvidenceUpdateRow)
        .filter(EvidenceUpdateRow.decision_id == decision_id)
        .order_by(EvidenceUpdateRow.id.desc())
        .first()
    )
    if row and row.payload.get("timestamp_utc"):
        return row.payload["timestamp_utc"]
    return fallback
