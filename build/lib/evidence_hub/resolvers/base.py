"""Resolver interface.

A Resolver takes a normalized decision and returns references that fill specific
evidence gaps, sourced from somewhere authoritative. The repo manifest is the
first implementation; an MLflow/OPA connector would be another Resolver that
*verifies* what a manifest *asserts*.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol

from ..schemas import ArtifactType, NormalizedDecisionEvent


@dataclass(frozen=True)
class ResolvedRef:
    gap: str                      # evidence key this fills (e.g. "data_lineage_reference")
    value: str                    # the reference / classification value
    artifact_type: ArtifactType
    artifact_field: Optional[str] = None  # matching field in ArtifactRefs, if any


class Resolver(Protocol):
    def source_id(self) -> str: ...
    def signature(self) -> str: ...
    def resolve(self, event: NormalizedDecisionEvent) -> list[ResolvedRef]: ...
