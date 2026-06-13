"""Pydantic contract for the Evidence Hub (mirrors the spec, section 6).

These models are used both internally and as FastAPI request/response bodies.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── enums ────────────────────────────────────────────────────────────────────

class EvidenceStatus(str, Enum):
    complete = "complete"
    ready_with_gaps = "ready_with_gaps"
    partial = "partial"
    incomplete = "incomplete"


class IntegrityStatus(str, Enum):
    verified = "verified"
    unverified = "unverified"
    failed = "failed"
    unknown = "unknown"


class RiskTier(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    unknown = "unknown"


class Priority(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class UpdateStatus(str, Enum):
    open = "open"
    in_progress = "in_progress"
    submitted = "submitted"
    verified = "verified"
    done = "done"
    closed = "closed"
    rejected = "rejected"


class ArtifactType(str, Enum):
    model_registry = "model_registry"
    model_approval = "model_approval"
    data_lineage = "data_lineage"
    data_quality = "data_quality"
    policy_check = "policy_check"
    monitoring_snapshot = "monitoring_snapshot"
    fairness_test = "fairness_test"
    human_review = "human_review"
    retention = "retention"
    other = "other"


class Relation(str, Enum):
    based_on = "based_on"
    validated_by = "validated_by"
    approved_by = "approved_by"
    monitored_by = "monitored_by"
    explained_by = "explained_by"
    archived_in = "archived_in"
    remediated_by = "remediated_by"
    owned_by = "owned_by"
    has_hash = "has_hash"


# ── normalized decision event (spec 6.2) ─────────────────────────────────────

class Reviewer(BaseModel):
    name: Optional[str] = None
    id: Optional[str] = None
    role: Optional[str] = None
    authority_reference: Optional[str] = None


class DecisionBlock(BaseModel):
    outcome: Optional[str] = None
    notes_present: bool = False
    rationale: Optional[str] = None
    reviewer: Reviewer = Field(default_factory=Reviewer)


class ModelBlock(BaseModel):
    model_config = {"protected_namespaces": ()}

    model_name: Optional[str] = None
    model_version: Optional[str] = None
    model_registry_reference: Optional[str] = None
    model_approval_reference: Optional[str] = None


class InputBlock(BaseModel):
    input_data_hash: Optional[str] = None
    data_lineage_reference: Optional[str] = None
    data_quality_check_reference: Optional[str] = None
    privacy_classification: Optional[str] = None


class PromptBlock(BaseModel):
    system_prompt_hash: Optional[str] = None
    prompt_version_reference: Optional[str] = None


class BasedOnBlock(BaseModel):
    triage_event_id: Optional[str] = None
    risk_event_id: Optional[str] = None


class ControlsBlock(BaseModel):
    policy_check_reference: Optional[str] = None
    policy_result: Optional[str] = None
    policy_version: Optional[str] = None
    fairness_test_reference: Optional[str] = None
    monitoring_snapshot_reference: Optional[str] = None
    drift_status: Optional[str] = None
    performance_status: Optional[str] = None
    override_flag: Optional[bool] = None
    retention_classification: Optional[str] = None


class ArchiveBlock(BaseModel):
    integrity_status: IntegrityStatus = IntegrityStatus.unknown
    tamper_evidence: Optional[bool] = None
    archive_type: Optional[str] = None
    archive_timestamp: Optional[str] = None
    archive_uri_present: bool = False


class NormalizedDecisionEvent(BaseModel):
    decision_id: str
    event_id: str
    event_type: str
    sequence_number: Optional[int] = None
    timestamp_utc: Optional[str] = None
    tenant_id: Optional[str] = None
    human_in_loop: bool = False
    decision: DecisionBlock = Field(default_factory=DecisionBlock)
    model: ModelBlock = Field(default_factory=ModelBlock)
    input: InputBlock = Field(default_factory=InputBlock)
    prompt: PromptBlock = Field(default_factory=PromptBlock)
    based_on: BasedOnBlock = Field(default_factory=BasedOnBlock)
    controls: ControlsBlock = Field(default_factory=ControlsBlock)
    archive: ArchiveBlock = Field(default_factory=ArchiveBlock)


# ── evaluation result (spec 6.3) ─────────────────────────────────────────────

class SchemaIssue(BaseModel):
    field: str
    issue: str
    recommendation: str


class RecommendedAction(BaseModel):
    action: str
    owner: str
    priority: Priority
    deadline: Optional[str] = None


class RiskAssessment(BaseModel):
    risk_tier: RiskTier = RiskTier.unknown
    rationale: str = ""


class EvidenceEvaluation(BaseModel):
    evaluation_id: str
    decision_id: str
    event_id: str
    tenant_id: Optional[str] = None
    evaluated_at: str
    evidence_status: EvidenceStatus
    audit_readiness_score: int
    integrity_status: IntegrityStatus
    risk_assessment: RiskAssessment
    present_evidence: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    schema_issues: list[SchemaIssue] = Field(default_factory=list)
    recommended_actions: list[RecommendedAction] = Field(default_factory=list)
    summary: str = ""


# ── evidence update (spec 6.4) ───────────────────────────────────────────────

class Provenance(BaseModel):
    source_system: str = "Evidence Hub"
    submitted_by: Optional[str] = None
    signature: Optional[str] = None


class ArtifactRefs(BaseModel):
    model_config = {"protected_namespaces": ()}

    model_registry_reference: Optional[str] = None
    model_approval_reference: Optional[str] = None
    data_lineage_reference: Optional[str] = None
    data_quality_check_reference: Optional[str] = None
    policy_check_reference: Optional[str] = None
    fairness_test_reference: Optional[str] = None
    monitoring_snapshot_reference: Optional[str] = None
    human_review_reference: Optional[str] = None
    remediation_ticket_reference: Optional[str] = None


class EvidenceUpdateRequest(BaseModel):
    decision_id: str
    event_id: Optional[str] = None
    gap: Optional[str] = None
    owner: str
    action: str
    status: UpdateStatus = UpdateStatus.open
    artifact_type: ArtifactType = ArtifactType.other
    artifact_refs: ArtifactRefs = Field(default_factory=ArtifactRefs)
    due_date: Optional[str] = None
    completion_date: Optional[str] = None
    linked_event_ids: list[str] = Field(default_factory=list)
    provenance: Provenance = Field(default_factory=Provenance)


class EvidenceUpdate(EvidenceUpdateRequest):
    update_id: str
    event_type: str = "evidence_update"
    timestamp_utc: str


# ── readiness view (spec 6.5) ────────────────────────────────────────────────

class RemediationItem(BaseModel):
    gap: str
    owner: str
    status: UpdateStatus
    due_date: Optional[str] = None


class EvidenceReadinessView(BaseModel):
    decision_id: str
    event_id: str
    tenant_id: Optional[str] = None
    current_evidence_status: EvidenceStatus
    audit_readiness_score: int
    open_gaps: list[str] = Field(default_factory=list)
    resolved_gaps: list[str] = Field(default_factory=list)
    active_remediation_items: list[RemediationItem] = Field(default_factory=list)
    last_updated: str
    integrity_status: IntegrityStatus


# ── evidence graph edge (spec 6.6) ───────────────────────────────────────────

class EvidenceGraphEdge(BaseModel):
    edge_id: str
    from_: str = Field(alias="from")
    to: str
    relation: Relation
    created_at: str
    source: str = "ledger"

    model_config = {"populate_by_name": True}


# ── audit pack ───────────────────────────────────────────────────────────────

class AuditPack(BaseModel):
    audit_pack_id: str
    status: str
    scope: str
    decision_id: str
    tenant_id: Optional[str] = None
    format: str
    generated_at: str
    readiness_status: EvidenceStatus
    sections: dict[str, Any]
