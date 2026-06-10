"""FastAPI surface for the Evidence Hub (spec section 9).

Routes:
  POST /evidence/evaluate            evaluate audit-readiness for a ledger event
  POST /evidence/evidence-update     append an evidence-remediation update
  GET  /evidence/readiness/{id}      current readiness roll-up
  GET  /evidence/graph/{id}          evidence graph edges
  POST /audit-pack                   per-decision JSON audit pack
  GET  /ledger/decisions             read-only passthrough to browse the ledger
  GET  /health

Auth/RBAC and external connectors are intentionally out of scope for this MVP.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import audit_pack as audit_pack_mod
from . import dashboard as dashboard_mod
from . import graph as graph_mod
from . import readiness as readiness_mod
from . import registry, service
from .config import get_settings
from .db import make_engine_and_session, write_audit_log
from .ledger_source import LedgerError, make_source
from .schemas import (
    AuditPack,
    EvidenceEvaluation,
    EvidenceGraphEdge,
    EvidenceReadinessView,
    EvidenceUpdateRequest,
)


# Request/response bodies must live at module scope: with `from __future__ import
# annotations` active, FastAPI resolves annotations via module globals, so locally
# defined models would be mistaken for query params.
class EvaluateRequest(BaseModel):
    event_id: str


class EvidenceUpdateResponse(BaseModel):
    status: str = "recorded"
    update_id: str


class AuditPackRequest(BaseModel):
    scope: str = "per_decision"
    decision_id: str
    format: str = "json"


def create_app() -> FastAPI:
    settings = get_settings()
    source = make_source(settings)
    _engine, SessionLocal = make_engine_and_session(settings)

    app = FastAPI(title="AI Decision Evidence Hub", version="0.1.0")
    app.state.settings = settings
    app.state.source = source
    app.state.SessionLocal = SessionLocal

    @contextmanager
    def get_session():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    # ── routes ──
    @app.get("/health")
    def health():
        return {"status": "ok", "ledger_source": settings.ledger_source}

    @app.get("/ledger/decisions")
    def ledger_decisions(from_ts: Optional[str] = None, to_ts: Optional[str] = None,
                         limit: int = 100):
        try:
            return {"items": source.list_decisions(from_ts, to_ts, limit)}
        except LedgerError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    @app.post("/evidence/evaluate", response_model=EvidenceEvaluation)
    def evaluate(req: EvaluateRequest):
        with get_session() as session:
            try:
                return service.evaluate_decision(session, source, req.event_id)
            except LedgerError as exc:
                raise HTTPException(status_code=404, detail=str(exc))

    @app.post("/evidence/evidence-update", response_model=EvidenceUpdateResponse)
    def evidence_update(req: EvidenceUpdateRequest):
        with get_session() as session:
            try:
                update = registry.record_update(session, req)
            except registry.InvalidTransition as exc:
                raise HTTPException(status_code=409, detail=str(exc))
            write_audit_log(session, "evidence_update_created",
                            decision_id=req.decision_id, detail={"gap": req.gap})
            session.commit()
            return EvidenceUpdateResponse(update_id=update.update_id)

    @app.get("/evidence/readiness/{decision_id}", response_model=EvidenceReadinessView)
    def readiness(decision_id: str):
        with get_session() as session:
            view = readiness_mod.build_readiness(session, decision_id)
            if view is None:
                raise HTTPException(status_code=404,
                                    detail=f"no evaluation for decision {decision_id!r}")
            write_audit_log(session, "evidence_pack_accessed", decision_id=decision_id)
            session.commit()
            return view

    @app.get("/evidence/graph/{decision_id}", response_model=list[EvidenceGraphEdge])
    def evidence_graph(decision_id: str):
        with get_session() as session:
            normalized = audit_pack_mod._latest_normalized(session, decision_id)
            if normalized is None:
                raise HTTPException(status_code=404,
                                    detail=f"no evaluation for decision {decision_id!r}")
            edges = graph_mod.build_graph(session, normalized)
            return edges

    @app.post("/audit-pack", response_model=AuditPack)
    def audit_pack(req: AuditPackRequest):
        if req.scope != "per_decision":
            raise HTTPException(status_code=400,
                                detail="only scope=per_decision is supported in this MVP")
        with get_session() as session:
            try:
                pack = audit_pack_mod.build_audit_pack(session, req.decision_id)
            except audit_pack_mod.AuditPackError as exc:
                raise HTTPException(status_code=404, detail=str(exc))
            from .db import AuditPackRow
            session.add(AuditPackRow(
                audit_pack_id=pack.audit_pack_id,
                decision_id=pack.decision_id,
                payload=pack.model_dump(mode="json"),
            ))
            write_audit_log(session, "audit_pack_generated", decision_id=req.decision_id,
                            detail={"audit_pack_id": pack.audit_pack_id})
            session.commit()
            return pack

    # ── dashboard data (spec section 14) ──
    @app.get("/dashboard/decisions")
    def dashboard_decisions():
        with get_session() as session:
            return dashboard_mod.decision_rows(session)

    @app.get("/dashboard/gaps")
    def dashboard_gaps():
        with get_session() as session:
            return dashboard_mod.gap_queue(session)

    @app.get("/dashboard/models")
    def dashboard_models():
        with get_session() as session:
            return dashboard_mod.model_rollup(session)

    @app.get("/dashboard/audit-packs")
    def dashboard_audit_packs():
        with get_session() as session:
            return dashboard_mod.audit_pack_rows(session)

    # ── static dashboard UI ──
    @app.get("/")
    def root():
        return RedirectResponse(url="/ui/")

    static_dir = os.path.join(os.path.dirname(__file__), "static")
    app.mount("/ui", StaticFiles(directory=static_dir, html=True), name="ui")

    return app


app = create_app()
