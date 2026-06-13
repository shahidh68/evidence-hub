"""Evidence evaluator (spec sections 5.2, 6.3, 8).

Turns a NormalizedDecisionEvent (+ detected schema issues) into an
EvidenceEvaluation: which required evidence is present vs missing, a weighted
audit-readiness score, status band, integrity status, a coarse risk tier, and
recommended remediation actions with owners.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from . import catalog
from .schemas import (
    EvidenceEvaluation,
    EvidenceStatus,
    IntegrityStatus,
    NormalizedDecisionEvent,
    Priority,
    RecommendedAction,
    RiskAssessment,
    RiskTier,
    SchemaIssue,
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def presence_map(event: NormalizedDecisionEvent) -> dict[str, bool]:
    """Flatten the normalized event into evidence_key -> present?"""
    d, m, i, p = event.decision, event.model, event.input, event.prompt
    c, a, r = event.controls, event.archive, event.decision.reviewer

    def has(v) -> bool:
        return v not in (None, "")

    return {
        # decision
        "decision_id": has(event.decision_id),
        "timestamp": has(event.timestamp_utc),
        "tenant_id": has(event.tenant_id),
        "outcome": has(d.outcome),
        "event_type": has(event.event_type),
        "sequence_number": has(event.sequence_number),
        # integrity / archive
        "integrity_status": a.integrity_status != IntegrityStatus.unknown,
        "tamper_evidence": a.tamper_evidence is not None,
        "archive_type": has(a.archive_type),
        "archive_timestamp": has(a.archive_timestamp),
        # model
        "model_name": has(m.model_name),
        "model_version": has(m.model_version),
        "model_registry_reference": has(m.model_registry_reference),
        "model_approval_reference": has(m.model_approval_reference),
        # data
        "input_data_hash": has(i.input_data_hash),
        "data_lineage_reference": has(i.data_lineage_reference),
        "data_quality_check_reference": has(i.data_quality_check_reference),
        # policy
        "policy_check_reference": has(c.policy_check_reference),
        "policy_result": has(c.policy_result),
        "policy_version": has(c.policy_version),
        # human review
        "reviewer_name": has(r.name),
        "review_outcome": has(d.outcome),
        "review_timestamp": has(event.timestamp_utc),
        "human_review_rationale": d.notes_present,
        "reviewer_authority_reference": has(r.authority_reference),
        "override_flag": c.override_flag is not None,
        # monitoring
        "monitoring_snapshot_reference": has(c.monitoring_snapshot_reference),
        "drift_status": has(c.drift_status),
        "performance_status": has(c.performance_status),
        "fairness_test_reference": has(c.fairness_test_reference),
        # prompt
        "system_prompt_hash": has(p.system_prompt_hash),
        "prompt_version_reference": has(p.prompt_version_reference),
        # retention / privacy
        "retention_classification": has(c.retention_classification),
        "privacy_classification": has(i.privacy_classification),
    }


def _risk(event: NormalizedDecisionEvent) -> RiskAssessment:
    # Coarse heuristic; a real deployment would read a risk tier off the event.
    if event.based_on.risk_event_id:
        return RiskAssessment(
            risk_tier=RiskTier.medium,
            rationale="Linked to a risk assessment event; tier not explicitly recorded.",
        )
    return RiskAssessment(
        risk_tier=RiskTier.unknown,
        rationale="No explicit risk tier recorded on the decision.",
    )


def evaluate(
    event: NormalizedDecisionEvent,
    schema_issues: list[SchemaIssue] | None = None,
) -> EvidenceEvaluation:
    present = presence_map(event)
    schema_issues = schema_issues or []

    present_keys: list[str] = []
    missing_keys: list[str] = []
    weighted = 0.0

    for cat in catalog.CATEGORIES:
        if cat.requires_human_loop and not event.human_in_loop:
            # Category not applicable; award full weight so it doesn't penalise.
            weighted += cat.weight
            continue
        got = sum(1 for k in cat.required if present.get(k))
        total = len(cat.required)
        weighted += cat.weight * (got / total) if total else cat.weight
        for k in cat.required:
            (present_keys if present.get(k) else missing_keys).append(k)

    score = round(weighted)
    status = EvidenceStatus(catalog.status_for_score(score))

    actions = [
        RecommendedAction(
            action=f"Attach {gap}.",
            owner=catalog.owner_for(gap),
            priority=Priority(catalog.priority_for(gap)),
            deadline=None,
        )
        for gap in missing_keys
    ]

    return EvidenceEvaluation(
        evaluation_id=f"eval-{uuid.uuid4().hex[:12]}",
        decision_id=event.decision_id,
        event_id=event.event_id,
        tenant_id=event.tenant_id,
        evaluated_at=_now(),
        evidence_status=status,
        audit_readiness_score=score,
        integrity_status=event.archive.integrity_status,
        risk_assessment=_risk(event),
        present_evidence=present_keys,
        missing_evidence=missing_keys,
        schema_issues=schema_issues,
        recommended_actions=actions,
        summary=_summary(event, status, score, missing_keys),
    )


def _summary(event, status: EvidenceStatus, score: int, missing: list[str]) -> str:
    integ = event.archive.integrity_status.value
    head = f"Decision {event.decision_id} is {integ} integrity and {status.value} on evidence ({score}/100)."
    if missing:
        return head + f" Missing required evidence: {', '.join(missing)}."
    return head + " All required evidence present."
