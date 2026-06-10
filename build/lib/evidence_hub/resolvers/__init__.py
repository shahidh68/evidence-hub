"""Resolvers fill evidence gaps from authoritative sources (repo manifest first;
connectors later)."""

from __future__ import annotations

from typing import Optional

from ..config import Settings
from .base import Resolver, ResolvedRef
from .manifest import ManifestResolver

__all__ = ["Resolver", "ResolvedRef", "ManifestResolver", "make_resolver"]


def make_resolver(settings: Settings) -> Optional[Resolver]:
    if not settings.manifest_path:
        return None
    return ManifestResolver.from_path(settings.manifest_path)
