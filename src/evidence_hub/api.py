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
from .auth import make_admin_guard
from .config import get_settings
from .ledger_source import LedgerError, make_source
from .resolvers import make_resolver
from .schemas import (
    AuditPack,
    EvidenceEvaluation,
    EvidenceGraphEdge,
    EvidenceReadinessView,
    EvidenceUpdateRequest,
)
from .store import make_store


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


class ResolveRequest(BaseModel):
    decision_id: str


def create_app() -> FastAPI:
    settings = get_settings()
    source = make_source(settings)
    resolver = make_resolver(settings)
    store = make_store(settings)
    guard = make_admin_guard(settings)  # no-op unless EVIDENCE_ADMIN_* configured

    app = FastAPI(title="AI Decision Evidence Hub", version="0.1.0")
    app.state.settings = settings
    app.state.source = source
    app.state.resolver = resolver
    app.state.store = store

    protected = [Depends(guard)]

    # ── routes ──
    @app.get("/health")
    def health():
        return {"status": "ok", "ledger_source": settings.ledger_source,
                "store": settings.store,
                "ledger_dashboard_url": settings.ledger_dashboard_url}

    @app.get("/ledger/decisions", dependencies=protected)
    def ledger_decisions(from_ts: Optional[str] = None, to_ts: Optional[str] = None,
                         limit: int = 100):
        try:
            return {"items": source.list_decisions(from_ts, to_ts, limit)}
        except LedgerError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    @app.post("/evidence/evaluate", response_model=EvidenceEvaluation, dependencies=protected)
    def evaluate(req: EvaluateRequest):
        try:
            return service.evaluate_decision(store, source, req.event_id, resolver=resolver)
        except LedgerError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.post("/evidence/resolve", dependencies=protected)
    def resolve(req: ResolveRequest):
        if resolver is None:
            raise HTTPException(
                status_code=400,
                detail="no resolver configured; set EVIDENCE_MANIFEST_PATH",
            )
        try:
            applied = service.resolve_decision(store, resolver, req.decision_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        return {"decision_id": req.decision_id, "resolved": applied,
                "source": resolver.source_id(), "signature": resolver.signature()}

    @app.post("/evidence/evidence-update", response_model=EvidenceUpdateResponse,
              dependencies=protected)
    def evidence_update(req: EvidenceUpdateRequest):
        try:
            update = registry.record_update(store, req)
        except registry.InvalidTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        store.add_audit_log("evidence_update_created",
                            decision_id=req.decision_id, detail={"gap": req.gap})
        return EvidenceUpdateResponse(update_id=update.update_id)

    @app.get("/evidence/readiness/{decision_id}", response_model=EvidenceReadinessView,
             dependencies=protected)
    def readiness(decision_id: str):
        view = readiness_mod.build_readiness(store, decision_id)
        if view is None:
            raise HTTPException(status_code=404,
                                detail=f"no evaluation for decision {decision_id!r}")
        store.add_audit_log("evidence_pack_accessed", decision_id=decision_id)
        return view

    @app.get("/evidence/graph/{decision_id}", response_model=list[EvidenceGraphEdge],
             dependencies=protected)
    def evidence_graph(decision_id: str):
        normalized = store.latest_normalized(decision_id)
        if normalized is None:
            raise HTTPException(status_code=404,
                                detail=f"no evaluation for decision {decision_id!r}")
        return graph_mod.build_graph(store, normalized)

    @app.post("/audit-pack", response_model=AuditPack, dependencies=protected)
    def audit_pack(req: AuditPackRequest):
        if req.scope != "per_decision":
            raise HTTPException(status_code=400,
                                detail="only scope=per_decision is supported in this MVP")
        try:
            pack = audit_pack_mod.build_audit_pack(store, req.decision_id)
        except audit_pack_mod.AuditPackError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        store.add_pack(pack)
        store.add_audit_log("audit_pack_generated", decision_id=req.decision_id,
                            detail={"audit_pack_id": pack.audit_pack_id})
        return pack

    # ── dashboard data (spec section 14) ──
    @app.get("/dashboard/decisions", dependencies=protected)
    def dashboard_decisions():
        return dashboard_mod.decision_rows(store)

    @app.get("/dashboard/gaps", dependencies=protected)
    def dashboard_gaps():
        return dashboard_mod.gap_queue(store)

    @app.get("/dashboard/models", dependencies=protected)
    def dashboard_models():
        return dashboard_mod.model_rollup(store)

    @app.get("/dashboard/audit-packs", dependencies=protected)
    def dashboard_audit_packs():
        return dashboard_mod.audit_pack_rows(store)

    # ── static dashboard UI ──
    @app.get("/")
    def root():
        return RedirectResponse(url="/ui/")

    static_dir = os.path.join(os.path.dirname(__file__), "static")
    app.mount("/ui", StaticFiles(directory=static_dir, html=True), name="ui")

    return app


app = create_app()
