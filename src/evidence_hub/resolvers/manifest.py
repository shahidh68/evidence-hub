"""Repo manifest resolver.

Resolves evidence references from a manifest the customer keeps in their repo,
joining only on fields the ledger actually records:

  models   keyed by `model_version`
  prompts  keyed by `system_prompt_hash`
  tenants  keyed by `tenant_id`  (per-tenant data/policy/retention defaults)

The manifest content is hashed (sha256) and that digest is recorded as the
provenance signature, so every resolved reference is traceable to an exact
manifest version even without git. JSON is supported natively; YAML needs the
optional `manifest` extra (pyyaml).
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from ..schemas import ArtifactType, NormalizedDecisionEvent
from .base import ResolvedRef

# evidence key -> matching ArtifactRefs field (only the ones that are true refs)
_REF_FIELD: dict[str, str] = {
    "model_registry_reference": "model_registry_reference",
    "model_approval_reference": "model_approval_reference",
    "data_lineage_reference": "data_lineage_reference",
    "data_quality_check_reference": "data_quality_check_reference",
    "policy_check_reference": "policy_check_reference",
}

_ARTIFACT_TYPE: dict[str, ArtifactType] = {
    "model_name": ArtifactType.model_registry,
    "model_registry_reference": ArtifactType.model_registry,
    "model_approval_reference": ArtifactType.model_approval,
    "data_lineage_reference": ArtifactType.data_lineage,
    "data_quality_check_reference": ArtifactType.data_quality,
    "privacy_classification": ArtifactType.other,
    "retention_classification": ArtifactType.retention,
    "policy_check_reference": ArtifactType.policy_check,
    "policy_version": ArtifactType.policy_check,
    "prompt_version_reference": ArtifactType.other,
}

_MODEL_KEYS = ("model_name", "model_registry_reference", "model_approval_reference")
_PROMPT_KEYS = ("prompt_version_reference",)
_TENANT_KEYS = (
    "data_lineage_reference", "data_quality_check_reference",
    "privacy_classification", "retention_classification",
    "policy_check_reference", "policy_version",
)


def _parse(path: str, raw: bytes) -> dict[str, Any]:
    if path.endswith((".yaml", ".yml")):
        try:
            import yaml  # lazy: optional dependency
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "YAML manifest requires pyyaml: pip install -e '.[manifest]'"
            ) from exc
        return yaml.safe_load(raw) or {}
    return json.loads(raw or b"{}")


class ManifestResolver:
    def __init__(self, manifest: dict[str, Any], source: str, raw: bytes) -> None:
        self.manifest = manifest or {}
        self.source = source
        self._sig = "sha256:" + hashlib.sha256(raw).hexdigest()

    @classmethod
    def from_path(cls, path: str) -> "ManifestResolver":
        with open(path, "rb") as fh:
            raw = fh.read()
        return cls(_parse(path, raw), source=os.path.basename(path), raw=raw)

    def source_id(self) -> str:
        return f"repo-manifest:{self.source}"

    def signature(self) -> str:
        return self._sig

    def resolve(self, event: NormalizedDecisionEvent) -> list[ResolvedRef]:
        out: list[ResolvedRef] = []
        m = self.manifest

        mv = event.model.model_version
        model_entry = (m.get("models") or {}).get(mv) if mv else None
        _collect(out, model_entry, _MODEL_KEYS)

        ph = event.prompt.system_prompt_hash
        prompt_entry = (m.get("prompts") or {}).get(ph) if ph else None
        _collect(out, prompt_entry, _PROMPT_KEYS)

        tenant_entry = (m.get("tenants") or {}).get(event.tenant_id) if event.tenant_id else None
        _collect(out, tenant_entry, _TENANT_KEYS)

        return out


def _collect(out: list[ResolvedRef], entry: dict[str, Any] | None, keys: tuple[str, ...]) -> None:
    if not entry:
        return
    for key in keys:
        val = entry.get(key)
        if val:
            out.append(ResolvedRef(
                gap=key, value=str(val),
                artifact_type=_ARTIFACT_TYPE.get(key, ArtifactType.other),
                artifact_field=_REF_FIELD.get(key),
            ))
