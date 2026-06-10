"""SQLAlchemy-backed Store (SQLite by default; Postgres via connection string).

This is the local/dev backend and the original storage layer. Tables are
append-only: an autoincrement id gives insertion order, and "latest" is the
highest id of a type for a decision.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

from ..config import Settings
from ..schemas import (
    AuditPack,
    EvidenceEvaluation,
    EvidenceUpdate,
    NormalizedDecisionEvent,
)


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class LedgerEventSnapshot(Base):
    __tablename__ = "ledger_event_snapshot"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String, index=True)
    decision_id: Mapped[str] = mapped_column(String, index=True)
    tenant_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    record: Mapped[dict[str, Any]] = mapped_column(JSON)
    tamper: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class NormalizedDecisionEventRow(Base):
    __tablename__ = "normalized_decision_event"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    decision_id: Mapped[str] = mapped_column(String, index=True)
    event_id: Mapped[str] = mapped_column(String, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class EvidenceEvaluationRow(Base):
    __tablename__ = "evidence_evaluation"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evaluation_id: Mapped[str] = mapped_column(String, index=True)
    decision_id: Mapped[str] = mapped_column(String, index=True)
    event_id: Mapped[str] = mapped_column(String, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class EvidenceUpdateRow(Base):
    __tablename__ = "evidence_update"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    update_id: Mapped[str] = mapped_column(String, index=True)
    decision_id: Mapped[str] = mapped_column(String, index=True)
    gap: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class AuditPackRow(Base):
    __tablename__ = "audit_pack"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    audit_pack_id: Mapped[str] = mapped_column(String, index=True)
    decision_id: Mapped[str] = mapped_column(String, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class AuditLogRow(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action: Mapped[str] = mapped_column(String, index=True)
    decision_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    actor: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    detail: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


def _ensure_sqlite_dir(db_url: str) -> None:
    prefix = "sqlite:///"
    if db_url.startswith(prefix):
        path = db_url[len(prefix):]
        if path and path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)


class SqlStore:
    def __init__(self, db_url: str) -> None:
        _ensure_sqlite_dir(db_url)
        kwargs: dict[str, Any] = {"future": True}
        if db_url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
            # In-memory needs a single shared connection or each session sees a
            # fresh, empty database.
            if db_url in ("sqlite://", "sqlite:///:memory:"):
                kwargs["poolclass"] = StaticPool
        self.engine = create_engine(db_url, **kwargs)
        Base.metadata.create_all(self.engine)
        self._Session = sessionmaker(bind=self.engine, expire_on_commit=False, future=True)

    # ── writes ──
    def add_snapshot(self, decision_id, event_id, tenant_id, record, tamper):
        with self._Session() as s:
            s.add(LedgerEventSnapshot(event_id=event_id, decision_id=decision_id,
                                      tenant_id=tenant_id, record=record, tamper=tamper))
            s.commit()

    def add_normalized(self, event: NormalizedDecisionEvent):
        with self._Session() as s:
            s.add(NormalizedDecisionEventRow(
                decision_id=event.decision_id, event_id=event.event_id,
                payload=event.model_dump(mode="json")))
            s.commit()

    def add_evaluation(self, evaluation: EvidenceEvaluation):
        with self._Session() as s:
            s.add(EvidenceEvaluationRow(
                evaluation_id=evaluation.evaluation_id, decision_id=evaluation.decision_id,
                event_id=evaluation.event_id, payload=evaluation.model_dump(mode="json")))
            s.commit()

    def add_update(self, update: EvidenceUpdate):
        with self._Session() as s:
            s.add(EvidenceUpdateRow(
                update_id=update.update_id, decision_id=update.decision_id,
                gap=update.gap, status=update.status.value,
                payload=update.model_dump(mode="json")))
            s.commit()

    def add_pack(self, pack: AuditPack):
        with self._Session() as s:
            s.add(AuditPackRow(audit_pack_id=pack.audit_pack_id, decision_id=pack.decision_id,
                               payload=pack.model_dump(mode="json")))
            s.commit()

    def add_audit_log(self, action, decision_id=None, actor=None, detail=None):
        with self._Session() as s:
            s.add(AuditLogRow(action=action, decision_id=decision_id, actor=actor, detail=detail))
            s.commit()

    # ── reads ──
    def latest_evaluation(self, decision_id):
        with self._Session() as s:
            row = (s.query(EvidenceEvaluationRow)
                   .filter(EvidenceEvaluationRow.decision_id == decision_id)
                   .order_by(EvidenceEvaluationRow.id.desc()).first())
            return EvidenceEvaluation.model_validate(row.payload) if row else None

    def latest_normalized(self, decision_id):
        with self._Session() as s:
            row = (s.query(NormalizedDecisionEventRow)
                   .filter(NormalizedDecisionEventRow.decision_id == decision_id)
                   .order_by(NormalizedDecisionEventRow.id.desc()).first())
            return NormalizedDecisionEvent.model_validate(row.payload) if row else None

    def latest_snapshot(self, decision_id):
        with self._Session() as s:
            row = (s.query(LedgerEventSnapshot)
                   .filter(LedgerEventSnapshot.decision_id == decision_id)
                   .order_by(LedgerEventSnapshot.id.desc()).first())
            return {"record": row.record, "tamper": row.tamper} if row else None

    def list_updates(self, decision_id):
        with self._Session() as s:
            rows = (s.query(EvidenceUpdateRow)
                    .filter(EvidenceUpdateRow.decision_id == decision_id)
                    .order_by(EvidenceUpdateRow.id.asc()).all())
            return [EvidenceUpdate.model_validate(r.payload) for r in rows]

    def list_packs(self):
        with self._Session() as s:
            rows = s.query(AuditPackRow).order_by(AuditPackRow.id.desc()).all()
            return [AuditPack.model_validate(r.payload) for r in rows]

    def list_decision_ids(self):
        with self._Session() as s:
            rows = s.query(EvidenceEvaluationRow.decision_id).distinct().all()
            return [r[0] for r in rows]
