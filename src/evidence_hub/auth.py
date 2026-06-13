"""Authentication and authorization for the Evidence Hub.

Two credentials, mirroring the ledger's "read key = read-only" model:

  * **Hub admin key** (`EVIDENCE_ADMIN_KEY` / the Secrets Manager secret) — full
    access, including the write actions (evaluate, resolve, evidence updates).
  * **Ledger read key** — the *same* key a user already uses for the ledger
    dashboard. The Hub validates it against the ledger, learns its tenant, and
    grants **read-only, tenant-scoped** access (view + export audit packs).

If no admin key is configured (local dev / tests), auth is disabled and every
caller is treated as a full-access admin — so the offline test suite is unchanged.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional

from fastapi import Header, HTTPException

from .config import Settings

ADMIN = "admin"
VIEWER = "viewer"

# A validation function: (api_url, key) -> (is_valid, tenant_or_None).
ValidateFn = Callable[[str, str], "tuple[bool, Optional[str]]"]


@dataclass(frozen=True)
class Principal:
    """Who is making the request and what tenant they may see."""
    role: str                  # ADMIN | VIEWER
    tenant: Optional[str]      # None = all tenants (admin / cross-tenant)


def _validate_against_ledger(api_url: str, key: str, timeout_s: float = 8.0) -> "tuple[bool, Optional[str]]":
    """Check a presented ledger read key by calling the ledger's read endpoint.

    HTTP 200 ⇒ the key is valid. The response's `tenant_id` is the scoped tenant
    (absent ⇒ a ledger admin "*" key, which we treat as cross-tenant: tenant None).
    Any error ⇒ not valid.
    """
    url = api_url.rstrip("/") + "/audit/logs"
    req = urllib.request.Request(
        url, headers={"Accept": "application/json", "x-api-key": key},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            if resp.status != 200:
                return False, None
            data = json.loads(resp.read().decode("utf-8"))
            tenant = data.get("tenant_id") if isinstance(data, dict) else None
            return True, (tenant or None)
    except (urllib.error.HTTPError, urllib.error.URLError, ValueError):
        return False, None


class LedgerKeyValidator:
    """Validates ledger read keys with a short-lived in-process cache.

    `validate_fn` is injectable so tests can stub out the network call.
    """

    def __init__(self, api_url: str, *, validate_fn: Optional[ValidateFn] = None,
                 ttl_s: float = 300.0) -> None:
        self._api_url = api_url
        self._validate = validate_fn or _validate_against_ledger
        self._ttl = ttl_s
        self._cache: dict[str, tuple[Optional[str], float]] = {}  # key -> (tenant, expiry)

    def validate(self, key: str) -> "tuple[bool, Optional[str]]":
        now = time.monotonic()
        cached = self._cache.get(key)
        if cached and cached[1] > now:
            return True, cached[0]
        valid, tenant = self._validate(self._api_url, key)
        if valid:
            self._cache[key] = (tenant, now + self._ttl)
        return valid, tenant


class Authenticator:
    """Resolves an `x-api-key` header to a `Principal`."""

    def __init__(self, settings: Settings, *,
                 validator: Optional[LedgerKeyValidator] = None) -> None:
        self.admin_key = settings.admin_api_key
        self.enabled = bool(self.admin_key)
        if validator is not None:
            self.validator: Optional[LedgerKeyValidator] = validator
        elif settings.audit_api_url:
            self.validator = LedgerKeyValidator(settings.audit_api_url)
        else:
            self.validator = None

    def resolve(self, x_api_key: Optional[str]) -> Principal:
        if not self.enabled:
            return Principal(ADMIN, None)  # auth disabled (local dev / tests)
        if not x_api_key:
            raise HTTPException(status_code=401, detail="missing x-api-key")
        if x_api_key == self.admin_key:
            return Principal(ADMIN, None)
        if self.validator is not None:
            valid, tenant = self.validator.validate(x_api_key)
            if valid:
                return Principal(VIEWER, tenant)
        raise HTTPException(status_code=401, detail="invalid x-api-key")


def make_dependencies(auth: Authenticator) -> "tuple[Callable, Callable]":
    """Build the FastAPI dependencies (require_viewer, require_admin)."""

    def require_viewer(
        x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
    ) -> Principal:
        return auth.resolve(x_api_key)

    def require_admin(
        x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
    ) -> Principal:
        principal = auth.resolve(x_api_key)
        if principal.role != ADMIN:
            raise HTTPException(status_code=403, detail="admin key required for this action")
        return principal

    return require_viewer, require_admin
