"""Evidence catalog and readiness weights (spec sections 7 and 8).

Single source of truth shared by the evaluator and the readiness view so the
two never drift. Each category lists the evidence keys that are *required* (count
toward the score) and *recommended* (informational). Evidence keys are the
canonical strings that appear in present_evidence / missing_evidence / gaps.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Category:
    key: str
    weight: int
    required: tuple[str, ...]
    recommended: tuple[str, ...] = ()
    # When False the category is skipped unless `human_in_loop` (set per-event).
    requires_human_loop: bool = False


# Category weights total 100 (spec section 8).
CATEGORIES: tuple[Category, ...] = (
    Category(
        key="decision",
        weight=10,
        required=("decision_id", "timestamp", "tenant_id", "outcome", "event_type"),
        recommended=("sequence_number", "use_case_id", "business_process", "risk_tier"),
    ),
    Category(
        key="integrity_archive",
        weight=15,
        required=("integrity_status", "tamper_evidence", "archive_type", "archive_timestamp"),
        recommended=("archive_uri_reference", "verification_hash", "retention_classification"),
    ),
    Category(
        key="model",
        weight=15,
        required=("model_name", "model_version", "model_registry_reference", "model_approval_reference"),
        recommended=("model_owner", "model_card_reference", "validation_report_reference"),
    ),
    Category(
        key="data",
        weight=15,
        required=("input_data_hash", "data_lineage_reference", "data_quality_check_reference"),
        recommended=("privacy_classification", "consent_or_legal_basis_reference"),
    ),
    Category(
        key="policy",
        weight=15,
        required=("policy_check_reference", "policy_result", "policy_version"),
        recommended=("control_ids", "exception_id", "approval_reference"),
    ),
    Category(
        key="human_review",
        weight=10,
        required=("reviewer_name", "review_outcome", "review_timestamp", "human_review_rationale"),
        recommended=("reviewer_role", "reviewer_authority_reference", "override_flag"),
        requires_human_loop=True,
    ),
    Category(
        key="monitoring",
        weight=10,
        required=("monitoring_snapshot_reference", "drift_status", "performance_status"),
        recommended=("fairness_test_reference", "last_validation_date"),
    ),
    Category(
        key="prompt",
        weight=5,
        required=("system_prompt_hash", "prompt_version_reference"),
        recommended=("prompt_approval_reference", "prompt_template_id"),
    ),
    Category(
        key="retention_privacy",
        weight=5,
        required=("retention_classification", "privacy_classification"),
        recommended=("consent_or_legal_basis_reference",),
    ),
)

# Sanity check: weights must sum to 100.
assert sum(c.weight for c in CATEGORIES) == 100, "category weights must total 100"


# Which team owns remediation for a given evidence key (spec sections 5.2 / 10).
_OWNER_BY_PREFIX: tuple[tuple[str, str], ...] = (
    ("model_", "ModelOps"),
    ("data_", "Data Governance"),
    ("input_data_hash", "Data Governance"),
    ("privacy_", "Data Governance"),
    ("retention_", "Data Governance"),
    ("policy_", "Compliance"),
    ("monitoring_", "ML Monitoring"),
    ("drift_", "ML Monitoring"),
    ("performance_", "ML Monitoring"),
    ("fairness_", "ML Monitoring"),
    ("human_review_", "Human Review Manager"),
    ("reviewer_", "Human Review Manager"),
    ("review_", "Human Review Manager"),
    ("prompt_", "Platform Engineering"),
    ("system_prompt_hash", "Platform Engineering"),
)

_HIGH_PRIORITY_PREFIXES = ("model_", "policy_", "data_", "input_data_hash")


def owner_for(evidence_key: str) -> str:
    for prefix, owner in _OWNER_BY_PREFIX:
        if evidence_key.startswith(prefix):
            return owner
    return "Compliance"


def priority_for(evidence_key: str) -> str:
    return "high" if evidence_key.startswith(_HIGH_PRIORITY_PREFIXES) else "medium"


def status_for_score(score: int) -> str:
    """Map a 0-100 readiness score to a status band (spec section 8)."""
    if score <= 30:
        return "incomplete"
    if score <= 70:
        return "partial"
    if score <= 90:
        return "ready_with_gaps"
    return "complete"


def all_required_keys() -> list[str]:
    keys: list[str] = []
    for cat in CATEGORIES:
        keys.extend(cat.required)
    return keys
