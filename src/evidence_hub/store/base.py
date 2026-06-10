"""Storage abstraction for the Evidence Hub.

The Hub keeps its evidence data behind a pluggable `Store` — the same pattern as
`LedgerSource` and `Resolver`. Local dev uses `SqlStore` (SQLite); AWS uses
`DynamoStore`. All persistence is append-only: no method ever overwrites an
existing item. "Latest" is always derived by reading the most-recent item of a
type for a decision.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional, Protocol

from ..schemas import (
    AuditPack,
    EvidenceEvaluation,
    EvidenceUpdate,
    NormalizedDecisionEvent,
)


def new_seq() -> str:
    """A lexically sortable, unique sequence token (high-res time + random).

    Zero-padded nanoseconds keep string ordering aligned with insertion order;
    the uuid suffix breaks ties within the same nanosecond.
    """
    return f"{time.time_ns():020d}#{uuid.uuid4().hex[:8]}"


class Store(Protocol):
    # ── writes (all append-only) ──
    def add_snapshot(self, decision_id: str, event_id: str, tenant_id: Optional[str],
                     record: dict[str, Any], tamper: Optional[dict[str, Any]]) -> None: ...
    def add_normalized(self, event: NormalizedDecisionEvent) -> None: ...
    def add_evaluation(self, evaluation: EvidenceEvaluation) -> None: ...
    def add_update(self, update: EvidenceUpdate) -> None: ...
    def add_pack(self, pack: AuditPack) -> None: ...
    def add_audit_log(self, action: str, decision_id: Optional[str] = None,
                      actor: Optional[str] = None, detail: Optional[dict] = None) -> None: ...

    # ── reads ──
    def latest_evaluation(self, decision_id: str) -> Optional[EvidenceEvaluation]: ...
    def latest_normalized(self, decision_id: str) -> Optional[NormalizedDecisionEvent]: ...
    def latest_snapshot(self, decision_id: str) -> Optional[dict[str, Any]]: ...
    def list_updates(self, decision_id: str) -> list[EvidenceUpdate]: ...
    def list_packs(self) -> list[AuditPack]: ...
    def list_decision_ids(self) -> list[str]: ...
