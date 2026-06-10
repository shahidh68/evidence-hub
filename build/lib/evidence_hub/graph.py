"""Evidence graph construction (spec sections 5.5, 6.6).

Builds edges linking a decision to its triage/risk events, its archive, and any
artifacts attached through evidence updates.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from . import registry
from .schemas import EvidenceGraphEdge, NormalizedDecisionEvent, Relation
from .store import Store


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _edge(frm: str, to: str, relation: Relation, source: str) -> EvidenceGraphEdge:
    return EvidenceGraphEdge(
        edge_id=f"edge-{uuid.uuid4().hex[:10]}",
        **{"from": frm},
        to=to,
        relation=relation,
        created_at=_now(),
        source=source,
    )


def build_graph(store: Store, event: NormalizedDecisionEvent) -> list[EvidenceGraphEdge]:
    decision_node = f"decision:{event.decision_id}"
    edges: list[EvidenceGraphEdge] = []

    if event.based_on.triage_event_id:
        edges.append(_edge(decision_node, f"triage_event:{event.based_on.triage_event_id}",
                           Relation.based_on, "ledger"))
    if event.based_on.risk_event_id:
        edges.append(_edge(decision_node, f"risk_event:{event.based_on.risk_event_id}",
                           Relation.based_on, "ledger"))
    if event.archive.archive_type:
        edges.append(_edge(decision_node, f"archive:{event.archive.archive_type}",
                           Relation.archived_in, "ledger"))
    if event.input.input_data_hash:
        edges.append(_edge(decision_node, f"input_hash:{event.input.input_data_hash[:16]}",
                           Relation.has_hash, "ledger"))
    if event.decision.reviewer.name:
        edges.append(_edge(decision_node, f"reviewer:{event.decision.reviewer.name}",
                           Relation.approved_by, "ledger"))

    # Artifacts attached via evidence updates.
    for upd in registry.list_updates(store, event.decision_id):
        for ref_name, ref_val in upd.artifact_refs.model_dump().items():
            if ref_val:
                edges.append(_edge(decision_node, f"{ref_name}:{ref_val}",
                                   Relation.remediated_by, "evidence_registry"))
    return edges
