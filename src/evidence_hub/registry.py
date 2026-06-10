"""Append-only evidence registry and gap lifecycle (spec sections 5.3, 6.4, 10).

Every change is a new row. The current status of a gap is the status of its most
recent update. Lifecycle transitions are validated so a gap can't, for example,
jump from closed back to in_progress without going through rejected.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from .db import EvidenceUpdateRow
from .schemas import EvidenceUpdate, EvidenceUpdateRequest, UpdateStatus

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


def current_gap_status(session, decision_id: str, gap: str) -> UpdateStatus | None:
    rows = (
        session.query(EvidenceUpdateRow)
        .filter(EvidenceUpdateRow.decision_id == decision_id,
                EvidenceUpdateRow.gap == gap)
        .order_by(EvidenceUpdateRow.id.desc())
        .all()
    )
    if not rows:
        return None
    return UpdateStatus(rows[0].status)


def record_update(session, req: EvidenceUpdateRequest) -> EvidenceUpdate:
    """Append a new evidence update, validating the lifecycle if it targets a gap."""
    if req.gap:
        prev = current_gap_status(session, req.decision_id, req.gap)
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
    session.add(EvidenceUpdateRow(
        update_id=update.update_id,
        decision_id=update.decision_id,
        gap=update.gap,
        status=update.status.value,
        payload=update.model_dump(mode="json"),
    ))
    return update


def list_updates(session, decision_id: str) -> list[EvidenceUpdate]:
    rows = (
        session.query(EvidenceUpdateRow)
        .filter(EvidenceUpdateRow.decision_id == decision_id)
        .order_by(EvidenceUpdateRow.id.asc())
        .all()
    )
    return [EvidenceUpdate.model_validate(r.payload) for r in rows]


def resolved_gaps(session, decision_id: str) -> set[str]:
    """Gaps whose latest update is in a resolved state."""
    latest: dict[str, UpdateStatus] = {}
    for upd in list_updates(session, decision_id):
        if upd.gap:
            latest[upd.gap] = upd.status
    return {gap for gap, status in latest.items() if status in RESOLVED}
