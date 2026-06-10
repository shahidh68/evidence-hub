"""Aggregation queries that back the dashboard (spec section 14).

These read the Hub's own store and roll up evaluated decisions into the four
views the dashboard shows: decisions, gap queue, model-level, and audit packs.
"""

from __future__ import annotations

from . import catalog, readiness, registry
from .audit_pack import _latest_normalized
from .db import AuditPackRow, EvidenceEvaluationRow

_PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def evaluated_decision_ids(session) -> list[str]:
    rows = session.query(EvidenceEvaluationRow.decision_id).distinct().all()
    return [r[0] for r in rows]


def decision_rows(session) -> list[dict]:
    """Decision-level view (spec 14.1). Most at-risk (lowest score) first."""
    out: list[dict] = []
    for did in evaluated_decision_ids(session):
        ev = readiness.latest_evaluation(session, did)
        view = readiness.build_readiness(session, did)
        norm = _latest_normalized(session, did)
        if ev is None or view is None:
            continue
        out.append({
            "decision_id": did,
            "event_id": ev.event_id,
            "tenant_id": norm.tenant_id if norm else None,
            "timestamp_utc": norm.timestamp_utc if norm else None,
            "outcome": norm.decision.outcome if norm else None,
            "event_type": norm.event_type if norm else None,
            "model_version": (norm.model.model_version if norm else None) or "unspecified",
            "integrity_status": view.integrity_status.value,
            "audit_readiness_score": view.audit_readiness_score,
            "current_evidence_status": view.current_evidence_status.value,
            "open_gaps": len(view.open_gaps),
            "resolved_gaps": len(view.resolved_gaps),
            "risk_tier": ev.risk_assessment.risk_tier.value,
        })
    out.sort(key=lambda r: r["audit_readiness_score"])
    return out


def gap_queue(session) -> list[dict]:
    """Open gaps across all decisions (spec 14.2). High priority first."""
    items: list[dict] = []
    for did in evaluated_decision_ids(session):
        ev = readiness.latest_evaluation(session, did)
        view = readiness.build_readiness(session, did)
        if ev is None or view is None:
            continue
        active = {it.gap: it for it in view.active_remediation_items}
        for gap in view.open_gaps:
            it = active.get(gap)
            items.append({
                "gap": gap,
                "decision_id": did,
                "owner": it.owner if it else catalog.owner_for(gap),
                "priority": catalog.priority_for(gap),
                "status": it.status.value if it else "open",
                "due_date": it.due_date if it else None,
                "identified_at": ev.evaluated_at,
                "risk_tier": ev.risk_assessment.risk_tier.value,
            })
    items.sort(key=lambda x: _PRIORITY_ORDER.get(x["priority"], 3))
    return items


def model_rollup(session) -> list[dict]:
    """Model-level view (spec 14.3). Lowest average readiness first."""
    groups: dict[str, dict] = {}
    for did in evaluated_decision_ids(session):
        view = readiness.build_readiness(session, did)
        norm = _latest_normalized(session, did)
        if view is None:
            continue
        mv = (norm.model.model_version if norm and norm.model.model_version else "unspecified")
        g = groups.setdefault(mv, {"model_version": mv, "decisions": 0,
                                   "score_sum": 0, "open_gaps": 0, "integrity_verified": 0})
        g["decisions"] += 1
        g["score_sum"] += view.audit_readiness_score
        g["open_gaps"] += len(view.open_gaps)
        if view.integrity_status.value == "verified":
            g["integrity_verified"] += 1

    out = []
    for g in groups.values():
        n = g["decisions"] or 1
        out.append({
            "model_version": g["model_version"],
            "decisions": g["decisions"],
            "avg_readiness_score": round(g["score_sum"] / n),
            "open_gaps": g["open_gaps"],
            "integrity_verified": g["integrity_verified"],
        })
    out.sort(key=lambda r: r["avg_readiness_score"])
    return out


def audit_pack_rows(session) -> list[dict]:
    """Generated audit packs (spec 14.4). Newest first."""
    rows = session.query(AuditPackRow).order_by(AuditPackRow.id.desc()).all()
    return [{
        "audit_pack_id": r.audit_pack_id,
        "decision_id": r.decision_id,
        "scope": r.payload.get("scope"),
        "format": r.payload.get("format"),
        "created_at": r.payload.get("generated_at"),
        "readiness_status": r.payload.get("readiness_status"),
        "sections": list(r.payload.get("sections", {}).keys()),
    } for r in rows]
