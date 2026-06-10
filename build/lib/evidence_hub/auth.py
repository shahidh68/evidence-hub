"""Admin-key auth for the single-tenant deployment.

If an admin key is configured (directly via EVIDENCE_ADMIN_KEY, or via the AWS
Secrets Manager secret), every protected route requires a matching `x-api-key`
header. If no admin key is configured (local dev / tests), the guard is a no-op
so the app runs unauthenticated.
"""

from __future__ import annotations

from typing import Callable, Optional

from fastapi import Header, HTTPException

from .config import Settings


def make_admin_guard(settings: Settings) -> Callable:
    expected = settings.admin_api_key

    def guard(x_api_key: Optional[str] = Header(default=None, alias="x-api-key")) -> None:
        if not expected:
            return None  # auth disabled (no admin key configured)
        if not x_api_key or x_api_key != expected:
            raise HTTPException(status_code=401, detail="invalid or missing x-api-key")
        return None

    return guard
