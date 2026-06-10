"""SQLAlchemy storage for the Evidence Hub (spec section 18).

Append-only / versioned tables get an autoincrement PK plus created_at; rows are
never updated in place. The current state of a decision is always *derived* by
replaying its evidence_update rows, never by mutating an earlier row.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .config import Settings


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


class EvidenceGraphEdgeRow(Base):
    __tablename__ = "evidence_graph_edge"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    edge_id: Mapped[str] = mapped_column(String, index=True)
    decision_id: Mapped[str] = mapped_column(String, index=True)
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
    """Evidence Hub's own access/action log (spec 12.3) — append-only."""
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
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, exist_ok=True)


def make_engine_and_session(settings: Settings):
    _ensure_sqlite_dir(settings.db_url)
    connect_args = {"check_same_thread": False} if settings.db_url.startswith("sqlite") else {}
    engine = create_engine(settings.db_url, connect_args=connect_args, future=True)
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False, future=True)


def write_audit_log(session, action: str, decision_id: str | None = None,
                    actor: str | None = None, detail: dict | None = None) -> None:
    session.add(AuditLogRow(action=action, decision_id=decision_id, actor=actor, detail=detail))
