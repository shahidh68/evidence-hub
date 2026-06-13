"""Normalize a raw ledger record into a NormalizedDecisionEvent.

The real ledger record is deliberately minimal: model_version, two hashes, a
free-form ai_decision_output dict, and human_in_loop. Richer compliance fields
(reviewer, triage/risk links, outcome, notes) live *inside* ai_decision_output,
so this module pulls them out and flags structural misuse such as a reviewer
name stuffed into model_version (spec section 11.3).
"""

from __future__ import annotations

import re
from typing import Any, Optional

from .schemas import (
    ArchiveBlock,
    BasedOnBlock,
    ControlsBlock,
    DecisionBlock,
    InputBlock,
    IntegrityStatus,
    ModelBlock,
    NormalizedDecisionEvent,
    PromptBlock,
    Reviewer,
    SchemaIssue,
)

# A model_version that looks like a real model identifier, e.g. "claude-sonnet-4.7"
# or "claims-risk-model:12". Reviewer metadata does not match this shape.
_PLAUSIBLE_MODEL = re.compile(r"^[A-Za-z0-9][\w.\-]*(:[\w.\-]+)?$")
_REVIEWER_MARKERS = ("human-reviewer", "reviewer:", "human:", "reviewed-by")


def _get(d: dict[str, Any], *keys: str) -> Optional[Any]:
    for k in keys:
        v = d.get(k)
        if v not in (None, ""):
            return v
    return None


def _reviewer_from_output(output: dict[str, Any]) -> Reviewer:
    rv = output.get("reviewer")
    if isinstance(rv, dict):
        return Reviewer(
            name=rv.get("name"),
            id=rv.get("id"),
            role=rv.get("role"),
            authority_reference=rv.get("authority_reference"),
        )
    if isinstance(rv, str) and rv.strip():
        return Reviewer(name=rv.strip())
    # Some pipelines record reviewer_name / reviewer_id directly.
    name = _get(output, "reviewer_name")
    rid = _get(output, "reviewer_id")
    if name or rid:
        return Reviewer(name=name, id=rid)
    return Reviewer()


def _model_name_from_version(model_version: str) -> str:
    """Return the stable model family/name from a version-like identifier."""
    return model_version.split(":", 1)[0].strip() or model_version


def _model_block_from_version(model_version: str, output: dict[str, Any]) -> ModelBlock:
    return ModelBlock(
        model_name=_get(output, "model_name") or _model_name_from_version(model_version),
        model_version=model_version,
        model_registry_reference=_get(output, "model_registry_reference"),
        model_approval_reference=_get(output, "model_approval_reference"),
    )


def normalize(
    record: dict[str, Any],
    tamper: Optional[dict[str, Any]] = None,
) -> tuple[NormalizedDecisionEvent, list[SchemaIssue]]:
    """Return (normalized event, schema issues) for a single ledger record."""
    issues: list[SchemaIssue] = []
    output: dict[str, Any] = record.get("ai_decision_output") or {}
    if not isinstance(output, dict):
        output = {}

    event_id = record.get("event_id", "")
    raw_model_version = record.get("model_version")
    human_in_loop = bool(record.get("human_in_loop", False))

    # ── detect reviewer metadata misused as model_version (spec 11.3) ──
    reviewer = _reviewer_from_output(output)
    model_block = ModelBlock()
    misused_reviewer = False
    if isinstance(raw_model_version, str) and raw_model_version.strip():
        mv = raw_model_version.strip()
        lower = mv.lower()
        if any(marker in lower for marker in _REVIEWER_MARKERS):
            misused_reviewer = True
            issues.append(SchemaIssue(
                field="model_version",
                issue=f"model_version carries reviewer metadata ({mv!r}), not a model identifier.",
                recommendation="Record the reviewer in a reviewer field and set model_version "
                               "to the actual model, or null for a pure human-review event.",
            ))
            # Recover a reviewer name if we don't already have one.
            if not reviewer.name:
                name = mv.split(":", 1)[1].strip() if ":" in mv else None
                reviewer = Reviewer(name=name)
        elif not _PLAUSIBLE_MODEL.match(mv):
            issues.append(SchemaIssue(
                field="model_version",
                issue=f"model_version {mv!r} does not match a standard model-identifier format.",
                recommendation="Use a registry-style identifier, e.g. 'claims-risk-model:12'.",
            ))
            model_block = _model_block_from_version(mv, output)
        else:
            model_block = _model_block_from_version(mv, output)
    elif not human_in_loop:
        issues.append(SchemaIssue(
            field="model_version",
            issue="model_version is null for an AI decision with no human in the loop.",
            recommendation="Populate model_version with the deployed model identifier.",
        ))

    # event_type: reviewer metadata or human_in_loop => human review decision.
    if misused_reviewer or (human_in_loop and reviewer.name):
        event_type = "human_review_decision"
    else:
        event_type = "ai_decision"

    # ── decision block ──
    notes = _get(output, "notes", "rationale", "review_rationale")
    decision = DecisionBlock(
        outcome=_get(output, "outcome", "decision"),
        notes_present=bool(notes),
        rationale=notes,
        reviewer=reviewer,
    )

    # ── based_on links (may sit at top level or inside output) ──
    based_on = BasedOnBlock(
        triage_event_id=_get(record, "based_on_triage_event_id")
        or _get(output, "based_on_triage_event_id", "triage_event_id"),
        risk_event_id=_get(record, "based_on_risk_event_id")
        or _get(output, "based_on_risk_event_id", "risk_event_id"),
    )

    # ── input / prompt ──
    input_block = InputBlock(
        input_data_hash=record.get("input_data_hash"),
        data_lineage_reference=_get(output, "data_lineage_reference"),
        data_quality_check_reference=_get(output, "data_quality_check_reference"),
        privacy_classification=_get(output, "privacy_classification"),
    )
    prompt_block = PromptBlock(
        system_prompt_hash=record.get("system_prompt_hash"),
        prompt_version_reference=_get(output, "prompt_version_reference"),
    )

    # ── archive / integrity (from the tamper-evidence check) ──
    archive = _archive_block(record, tamper)

    controls = ControlsBlock(
        policy_check_reference=_get(output, "policy_check_reference"),
        policy_result=_get(output, "policy_result"),
        policy_version=_get(output, "policy_version"),
        fairness_test_reference=_get(output, "fairness_test_reference"),
        monitoring_snapshot_reference=_get(output, "monitoring_snapshot_reference"),
        drift_status=_get(output, "drift_status"),
        performance_status=_get(output, "performance_status"),
        override_flag=output.get("override_flag") if "override_flag" in output else None,
        retention_classification=_get(output, "retention_classification"),
    )

    event = NormalizedDecisionEvent(
        decision_id=event_id,
        event_id=event_id,
        event_type=event_type,
        sequence_number=record.get("sequence_no"),
        timestamp_utc=record.get("timestamp"),
        tenant_id=record.get("tenant_id"),
        human_in_loop=human_in_loop,
        decision=decision,
        model=model_block,
        input=input_block,
        prompt=prompt_block,
        based_on=based_on,
        controls=controls,
        archive=archive,
    )
    return event, issues


def _archive_block(
    record: dict[str, Any], tamper: Optional[dict[str, Any]]
) -> ArchiveBlock:
    if not tamper:
        return ArchiveBlock(integrity_status=IntegrityStatus.unknown)
    verified = bool(tamper.get("integrity_verified"))
    archived = tamper.get("archived_record") or {}
    has_archive = bool(archived)
    return ArchiveBlock(
        integrity_status=IntegrityStatus.verified if verified else IntegrityStatus.failed,
        tamper_evidence=verified,
        archive_type="immutable_s3" if has_archive else None,
        archive_timestamp=archived.get("timestamp") or record.get("timestamp") if has_archive else None,
        archive_uri_present=False,
    )
