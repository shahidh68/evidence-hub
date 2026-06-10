"""Append-only evidence registry and gap lifecycle (spec sections 5.3, 6.4, 10).

Every change is a new row. The current status of a gap is the status of its most
recent update. Lifecycle transitions are validated so a gap can't, for example,
jump from closed back to in_progress without going through rejected.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from .schemas import EvidenceUpdate, EvidenceUpdateRequest, UpdateStatus
from .store import Store

# Statuses that mean the gap is resolved.
RESOLVED = {UpdateStatus.verified, UpdateStatus.done, UpdateStatus.closed}

# Allowed transitions (spec section 10). None = the gap's first-ever update.
_ALLOWED: dict[UpdateStatus | None, set[UpdateStatus]] = {
    None: {UpdateStatus.open, UpdateStatus.in_progress, UpdateStatus.submitted},
    UpdateStatus.open: {UpdateStatus.in_progress, UpdateStatus.submitted, UpdateStatus.rejected},
    UpdateStatus.in_progress: {UpdateStatus.submitted, UpdateStatus.done, UpdateStatus.verified,
                               UpdateStatus.open, UpdateStatus.rejected},
    UpdateStatus.submitted: {UpdateStatus.verified, UpdateStatus.done, UpdateStatus.rejected,
                             UpdateStatus.in_progress},
    UpdateStatus.rejected: {UpdateStatus.in_progress, UpdateStatus.open},
    UpdateStatus.verified: {UpdateStatus.closed, UpdateStatus.done},
    UpdateStatus.done: {UpdateStatus.closed},
    UpdateStatus.closed: set(),
}


class InvalidTransition(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def current_gap_status(store: Store, decision_id: str, gap: str) -> UpdateStatus | None:
    latest: UpdateStatus | None = None
    for upd in store.list_updates(decision_id):  # ascending insertion order
        if upd.gap == gap:
            latest = upd.status
    return latest


def record_update(store: Store, req: EvidenceUpdateRequest,
                  bypass_lifecycle: bool = False) -> EvidenceUpdate:
    """Append a new evidence update, validating the lifecycle if it targets a gap.

    bypass_lifecycle=True is for automated authoritative attaches (resolvers and
    connectors): they don't *transition* a gap through a human workflow, they
    independently attach verified evidence, so the transition rules don't apply.
    """
    if req.gap and not bypass_lifecycle:
        prev = current_gap_status(store, req.decision_id, req.gap)
        allowed = _ALLOWED.get(prev, set())
        if req.status not in allowed:
            prev_label = prev.value if prev else "none"
            raise InvalidTransition(
                f"cannot move gap {req.gap!r} from {prev_label} to {req.status.value}; "
                f"allowed: {sorted(s.value for s in allowed)}"
            )

    update = EvidenceUpdate(
        update_id=f"eupd-{datetime.now(timezone.utc):%Y%m%d}-{uuid.uuid4().hex[:8]}",
        timestamp_utc=_now(),
        **req.model_dump(),
    )
    store.add_update(update)
    return update


def list_updates(store: Store, decision_id: str) -> list[EvidenceUpdate]:
    return store.list_updates(decision_id)


def resolved_gaps(store: Store, decision_id: str) -> set[str]:
    """Gaps whose latest update is in a resolved state."""
    latest: dict[str, UpdateStatus] = {}
    for upd in store.list_updates(decision_id):
        if upd.gap:
            latest[upd.gap] = upd.status
    return {gap for gap, status in latest.items() if status in RESOLVED}
