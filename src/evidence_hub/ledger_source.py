"""Read-only access to the immutable audit ledger.

Three interchangeable sources selected by LEDGER_SOURCE:

  fixtures  - local JSON files (offline; no SDK, no network)
  sandbox   - the public ledger sandbox (shared sandbox-public tenant)
  live      - a deployed ledger (AUDIT_API_URL + AUDIT_READ_KEY)

The Hub only ever reads. It never writes to or mutates the ledger (spec 3).
The ai_audit_ledger SDK is imported lazily so fixtures mode needs no extra deps.
"""

from __future__ import annotations

import json
import os
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


class SdkLedgerSource:
    """Reads from a deployed ledger (sandbox or live) via the ai_audit_ledger SDK."""

    def __init__(self, api_url: str, read_key: str) -> None:
        if not api_url or not read_key:
            raise LedgerError(
                "live/sandbox ledger source needs AUDIT_API_URL and AUDIT_READ_KEY"
            )
        self.api_url = api_url
        self.read_key = read_key

    def _read_api(self):
        try:
            from ai_audit_ledger import read_api  # lazy: pulls in aiohttp
        except ImportError as exc:  # pragma: no cover - depends on install
            raise LedgerError(
                "ai_audit_ledger SDK not installed. Install the optional 'ledger' "
                "extra: pip install -e ../ai-audit-ledger/sdk/python"
            ) from exc
        return read_api

    def list_decisions(self, from_ts=None, to_ts=None, limit=100):
        api = self._read_api()
        result = api.list_decisions_sync(
            api_url=self.api_url, read_key=self.read_key,
            from_ts=from_ts, to_ts=to_ts,
        )
        items = result.get("items", []) if isinstance(result, dict) else []
        return items[:limit]

    def get_decision(self, event_id: str):
        api = self._read_api()
        # verify_decision returns the DynamoDB copy + the archived copy + integrity.
        tamper = api.verify_decision_sync(
            api_url=self.api_url, read_key=self.read_key, event_id=event_id,
        )
        record = tamper.get("current_record") or tamper.get("archived_record") or {}
        if not record:
            raise LedgerError(f"ledger returned no record for event_id {event_id!r}")
        return record, tamper


def make_source(settings: Settings) -> LedgerSource:
    if settings.ledger_source == "fixtures":
        return FixtureLedgerSource(settings.fixtures_dir)
    return SdkLedgerSource(settings.audit_api_url, settings.audit_read_key)
