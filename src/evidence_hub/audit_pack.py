"""Per-decision JSON audit pack generator (spec sections 5.6, 9.6).

Assembles a single exportable package from everything the Hub knows about a
decision: the ledger record, tamper-evidence, normalized event, evidence
evaluation, current readiness, remediation history, and the evidence graph.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from . import catalog, graph, readiness, registry
from .schemas import AuditPack, EvidenceStatus, NormalizedDecisionEvent
from .store import Store


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class AuditPackError(RuntimeError):
    pass


def _latest_normalized(store: Store, decision_id: str) -> NormalizedDecisionEvent | None:
    return store.latest_normalized(decision_id)


def _report_summary(decision_id: str, normalized: NormalizedDecisionEvent, view, evaluation) -> dict:
    score = view.audit_readiness_score if view else evaluation.audit_readiness_score
    status = (view.current_evidence_status if view else evaluation.evidence_status).value
    open_gaps = view.open_gaps if view else evaluation.missing_evidence
    resolved_gaps = view.resolved_gaps if view else []
    if open_gaps:
        recommendation = "Not audit-ready yet. Close the open evidence gaps before relying on this pack."
    else:
        recommendation = "Audit-ready on the evidence currently tracked by Evidence Hub."
    return {
        "decision_id": decision_id,
        "tenant_id": normalized.tenant_id,
        "outcome": normalized.decision.outcome,
        "model_version": normalized.model.model_version,
        "integrity_status": evaluation.integrity_status.value,
        "readiness_status": status,
        "audit_readiness_score": score,
        "open_gap_count": len(open_gaps),
        "resolved_gap_count": len(resolved_gaps),
        "recommendation": recommendation,
    }


def _gap_closure_plan(open_gaps: list[str]) -> list[dict]:
    return [
        {
            "gap": gap,
            "owner": catalog.owner_for(gap),
            "priority": catalog.priority_for(gap),
            "next_action": f"Add or verify {gap}.",
        }
        for gap in open_gaps
    ]


def build_audit_pack(store: Store, decision_id: str) -> AuditPack:
    snapshot = store.latest_snapshot(decision_id)
    normalized = store.latest_normalized(decision_id)
    evaluation = readiness.latest_evaluation(store, decision_id)
    if snapshot is None or normalized is None or evaluation is None:
        raise AuditPackError(
            f"decision {decision_id!r} has not been evaluated yet; call /evidence/evaluate first"
        )

    view = readiness.build_readiness(store, decision_id)
    updates = registry.list_updates(store, decision_id)
    edges = graph.build_graph(store, normalized)

    open_gaps = view.open_gaps if view else evaluation.missing_evidence
    sections = {
        "report_summary": _report_summary(decision_id, normalized, view, evaluation),
        "decision_summary": {
            "decision_id": decision_id,
            "event_type": normalized.event_type,
            "timestamp_utc": normalized.timestamp_utc,
            "tenant_id": normalized.tenant_id,
            "outcome": normalized.decision.outcome,
            "human_in_loop": normalized.human_in_loop,
        },
        "ledger_record": snapshot["record"],
        "tamper_evidence": snapshot["tamper"],
        "human_review": normalized.decision.model_dump(),
        "model_evidence": normalized.model.model_dump(),
        "data_evidence": normalized.input.model_dump(),
        "prompt_evidence": normalized.prompt.model_dump(),
        "controls": normalized.controls.model_dump(),
        "linked_events": normalized.based_on.model_dump(),
        "evidence_evaluation": evaluation.model_dump(),
        "open_gaps": open_gaps,
        "gap_closure_plan": _gap_closure_plan(open_gaps),
        "remediation_history": [u.model_dump(mode="json") for u in updates],
        "evidence_graph": [e.model_dump(by_alias=True) for e in edges],
    }

    readiness_status = view.current_evidence_status if view else evaluation.evidence_status
    return AuditPack(
        audit_pack_id=f"apack-{uuid.uuid4().hex[:10]}",
        status="generated",
        scope="per_decision",
        decision_id=decision_id,
        tenant_id=normalized.tenant_id,
        format="json",
        generated_at=_now(),
        readiness_status=EvidenceStatus(readiness_status),
        sections=sections,
    )
