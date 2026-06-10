"""Orchestration that ties ledger reads, normalization, evaluation and storage
together. Kept separate from the API so it can be unit-tested directly.
"""

from __future__ import annotations

from typing import Optional

from . import catalog, evaluator, registry
from .ledger_source import LedgerSource
from .normalizer import normalize
from .resolvers.base import Resolver
from .schemas import (
    ArtifactRefs,
    EvidenceEvaluation,
    EvidenceUpdateRequest,
    Provenance,
    UpdateStatus,
)
from .store import Store


def evaluate_decision(store: Store, source: LedgerSource, event_id: str,
                      actor: str | None = None,
                      resolver: Optional[Resolver] = None) -> EvidenceEvaluation:
    """Read one ledger event, normalize, evaluate, and persist all three.

    If a resolver is configured, automatically fill resolvable gaps afterward.
    The ledger is read-only; nothing here writes back to it.
    """
    record, tamper = source.get_decision(event_id)
    normalized, issues = normalize(record, tamper)
    evaluation = evaluator.evaluate(normalized, issues)

    store.add_snapshot(normalized.decision_id, normalized.event_id,
                       normalized.tenant_id, record, tamper)
    store.add_normalized(normalized)
    store.add_evaluation(evaluation)
    store.add_audit_log("readiness_score_recalculated",
                        decision_id=evaluation.decision_id, actor=actor,
                        detail={"score": evaluation.audit_readiness_score})

    if resolver is not None:
        resolve_decision(store, resolver, evaluation.decision_id, actor=actor)
    return evaluation


def resolve_decision(store: Store, resolver: Resolver, decision_id: str,
                     actor: str | None = None) -> list[str]:
    """Append verified evidence updates for any gaps the resolver can fill.

    Idempotent: already-resolved gaps are skipped. Each update carries the
    resolver's source id and content signature as provenance.
    """
    event = store.latest_normalized(decision_id)
    if event is None:
        raise ValueError(f"decision {decision_id!r} has not been evaluated yet")

    already = registry.resolved_gaps(store, decision_id)
    applied: list[str] = []
    for ref in resolver.resolve(event):
        if ref.gap in already:
            continue
        refs = ArtifactRefs()
        if ref.artifact_field:
            setattr(refs, ref.artifact_field, ref.value)
        req = EvidenceUpdateRequest(
            decision_id=decision_id,
            gap=ref.gap,
            owner=catalog.owner_for(ref.gap),
            action=f"Resolved {ref.gap} = {ref.value} from {resolver.source_id()}",
            status=UpdateStatus.verified,
            artifact_type=ref.artifact_type,
            artifact_refs=refs,
            linked_event_ids=[event.event_id],
            provenance=Provenance(
                source_system=resolver.source_id(),
                submitted_by="auto-resolver",
                signature=resolver.signature(),
            ),
        )
        registry.record_update(store, req, bypass_lifecycle=True)
        applied.append(ref.gap)

    store.add_audit_log("artifact_reference_attached", decision_id=decision_id,
                        actor=actor, detail={"resolved": applied, "source": resolver.source_id()})
    return applied
