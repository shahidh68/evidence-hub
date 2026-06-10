"""Environment-driven settings for the Evidence Hub.

The Hub never writes to the ledger; these settings only control how it *reads*
ledger events and where it stores its own append-only evidence data.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Public ledger sandbox (mirrors audit-ledger-mcp/src/sandbox.ts). The read key
# is intentionally public and scoped to the shared `sandbox-public` tenant.
SANDBOX_API_URL = "https://m3csva3l3h.execute-api.eu-west-1.amazonaws.com/prod"
SANDBOX_READ_KEY = "rk-sandbox-public-XaV3aHdmKH1ZbQl7LswUkTJYJLyGmLh8"
SANDBOX_TENANT = "sandbox-public"

_DEFAULT_DB_URL = "sqlite:///./data/evidence.db"


@dataclass(frozen=True)
class Settings:
    ledger_source: str          # "fixtures" | "sandbox" | "live"
    audit_api_url: str
    audit_read_key: str
    db_url: str
    fixtures_dir: str


def get_settings() -> Settings:
    source = os.environ.get("LEDGER_SOURCE", "sandbox").strip().lower()
    if source not in {"fixtures", "sandbox", "live"}:
        raise ValueError(
            f"LEDGER_SOURCE must be fixtures|sandbox|live, got {source!r}"
        )

    if source == "sandbox":
        api_url = SANDBOX_API_URL
        read_key = SANDBOX_READ_KEY
    else:
        api_url = os.environ.get("AUDIT_API_URL", "").strip()
        read_key = os.environ.get("AUDIT_READ_KEY", "").strip()

    fixtures_dir = os.environ.get(
        "EVIDENCE_FIXTURES_DIR",
        os.path.join(os.path.dirname(__file__), "..", "..", "tests", "fixtures"),
    )

    return Settings(
        ledger_source=source,
        audit_api_url=api_url,
        audit_read_key=read_key,
        db_url=os.environ.get("EVIDENCE_DB_URL", _DEFAULT_DB_URL),
        fixtures_dir=os.path.abspath(fixtures_dir),
    )
