"""Read-only access to the immutable audit ledger.

Three interchangeable sources selected by LEDGER_SOURCE:

  fixtures  - local JSON files (offline; no network)
  sandbox   - the public ledger sandbox (shared sandbox-public tenant)
  live      - a deployed ledger (AUDIT_API_URL + AUDIT_READ_KEY)

The Hub only ever reads. It never writes to or mutates the ledger (spec 3).
sandbox/live use stdlib urllib against the ledger's two read endpoints, so the
deployed container needs no extra dependencies.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional, Protocol

from .config import Settings


class LedgerError(RuntimeError):
    pass


class LedgerSource(Protocol):
    def list_decisions(
        self, from_ts: Optional[str] = None, to_ts: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]: ...

    def get_decision(self, event_id: str) -> tuple[dict[str, Any], Optional[dict[str, Any]]]:
        """Return (record, tamper_check_result). tamper may be None if unknown."""
        ...


class FixtureLedgerSource:
    """Reads `{event_id}.json` files of the form {"record": {...}, "tamper": {...}}."""

    def __init__(self, fixtures_dir: str) -> None:
        self.dir = fixtures_dir

    def _load(self, event_id: str) -> dict[str, Any]:
        path = os.path.join(self.dir, f"{event_id}.json")
        if not os.path.exists(path):
            raise LedgerError(f"no fixture for event_id {event_id!r} at {path}")
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    def list_decisions(self, from_ts=None, to_ts=None, limit=100):
        out: list[dict[str, Any]] = []
        for name in sorted(os.listdir(self.dir)):
            if not name.endswith(".json"):
                continue
            with open(os.path.join(self.dir, name), "r", encoding="utf-8") as fh:
                payload = json.load(fh)
            rec = payload.get("record", payload)
            ts = rec.get("timestamp")
            if from_ts and ts and ts < from_ts:
                continue
            if to_ts and ts and ts > to_ts:
                continue
            out.append(rec)
        return out[:limit]

    def get_decision(self, event_id: str):
        payload = self._load(event_id)
        return payload.get("record", payload), payload.get("tamper")


class HttpLedgerSource:
    """Reads a deployed ledger (sandbox or live) over its two GET endpoints.

    Uses stdlib urllib (no SDK / aiohttp) so the deployed container is
    self-contained. Endpoints match the ledger's read API:
      GET /audit/logs?from=&to=                     -> {items: [...]}
      GET /audit/events/{event_id}/history          -> TamperCheckResult
    """

    def __init__(self, api_url: str, read_key: str, timeout_s: float = 10.0) -> None:
        if not api_url or not read_key:
            raise LedgerError(
                "live/sandbox ledger source needs AUDIT_API_URL and AUDIT_READ_KEY"
            )
        self.base = api_url.rstrip("/")
        self.read_key = read_key
        self.timeout = timeout_s

    def _get(self, path: str, params: Optional[dict[str, Any]] = None) -> Any:
        url = self.base + path
        if params:
            q = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
            if q:
                url += f"?{q}"
        req = urllib.request.Request(
            url, headers={"Accept": "application/json", "x-api-key": self.read_key},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise LedgerError(f"ledger GET {path} failed: HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise LedgerError(f"ledger GET {path} unreachable: {exc.reason}") from exc

    def list_decisions(self, from_ts=None, to_ts=None, limit=100):
        result = self._get("/audit/logs", {"from": from_ts, "to": to_ts})
        items = result.get("items", []) if isinstance(result, dict) else []
        return items[:limit]

    def get_decision(self, event_id: str):
        path = f"/audit/events/{urllib.parse.quote(event_id, safe='')}/history"
        tamper = self._get(path)  # current + archived copy + integrity
        record = tamper.get("current_record") or tamper.get("archived_record") or {}
        if not record:
            raise LedgerError(f"ledger returned no record for event_id {event_id!r}")
        return record, tamper


def make_source(settings: Settings) -> LedgerSource:
    if settings.ledger_source == "fixtures":
        return FixtureLedgerSource(settings.fixtures_dir)
    return HttpLedgerSource(settings.audit_api_url, settings.audit_read_key)
