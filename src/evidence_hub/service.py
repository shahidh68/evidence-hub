"""Orchestration that ties ledger reads, normalization, evaluation and storage
together. Kept separate from the API so it can be unit-tested directly.
"""

from __future__ import annotations

from . import evaluator
from .db import (
    EvidenceEvaluationRow,
    LedgerEventSnapshot,
    NormalizedDecisionEventRow,
    write_audit_log,
)
from .ledger_source import LedgerSource
from .normalizer import normalize
from .schemas import EvidenceEvaluation


def evaluate_decision(session, source: LedgerSource, event_id: str,
                      actor: str | None = None) -> EvidenceEvaluation:
    """Read one ledger event, normalize, evaluate, and persist all three.

    The ledger is read-only; nothing here writes back to it.
    """
    record, tamper = source.get_decision(event_id)
    normalized, issues = normalize(record, tamper)
    evaluation = evaluator.evaluate(normalized, issues)

    session.add(LedgerEventSnapshot(
        event_id=normalized.event_id,
        decision_id=normalized.decision_id,
        tenant_id=normalized.tenant_id,
        record=record,
        tamper=tamper,
    ))
    session.add(NormalizedDecisionEventRow(
        decision_id=normalized.decision_id,
        event_id=normalized.event_id,
        payload=normalized.model_dump(mode="json"),
    ))
    session.add(EvidenceEvaluationRow(
        evaluation_id=evaluation.evaluation_id,
        decision_id=evaluation.decision_id,
        event_id=evaluation.event_id,
        payload=evaluation.model_dump(mode="json"),
    ))
    write_audit_log(session, "readiness_score_recalculated",
                    decision_id=evaluation.decision_id, actor=actor,
                    detail={"score": evaluation.audit_readiness_score})
    session.commit()
    return evaluation
