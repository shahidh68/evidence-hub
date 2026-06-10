"""Current readiness roll-up (spec sections 5.4, 6.5).

Recomputed on demand from the latest evaluation plus the append-only evidence
updates for a decision. Resolved gaps add back their marginal weight to the score.
"""

from __future__ import annotations

from . import catalog, registry
from .schemas import (
    EvidenceEvaluation,
    EvidenceReadinessView,
    EvidenceStatus,
    RemediationItem,
)
from .store import Store


def _marginal_weight(evidence_key: str) -> float:
    for cat in catalog.CATEGORIES:
        if evidence_key in cat.required:
            return cat.weight / len(cat.required)
    return 0.0


def latest_evaluation(store: Store, decision_id: str) -> EvidenceEvaluation | None:
    return store.latest_evaluation(decision_id)


def build_readiness(store: Store, decision_id: str) -> EvidenceReadinessView | None:
    evaluation = latest_evaluation(store, decision_id)
    if evaluation is None:
        return None

    updates = store.list_updates(decision_id)
    resolved = registry.resolved_gaps(store, decision_id)
    missing = evaluation.missing_evidence

    open_gaps = [g for g in missing if g not in resolved]
    resolved_gaps = [g for g in missing if g in resolved]

    score = evaluation.audit_readiness_score + sum(_marginal_weight(g) for g in resolved_gaps)
    score = min(100, round(score))
    status = EvidenceStatus(catalog.status_for_score(score))

    # Active remediation = latest update per gap that isn't resolved.
    latest_by_gap: dict[str, RemediationItem] = {}
    for upd in updates:
        if upd.gap and upd.status not in registry.RESOLVED:
            latest_by_gap[upd.gap] = RemediationItem(
                gap=upd.gap, owner=upd.owner, status=upd.status, due_date=upd.due_date,
            )
    active_items = list(latest_by_gap.values())

    last_updated = evaluation.evaluated_at
    for upd in updates:
        if upd.timestamp_utc:
            last_updated = upd.timestamp_utc

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
