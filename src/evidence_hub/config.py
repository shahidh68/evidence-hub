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

# The deployed AI Audit Ledger dashboard (CloudFront). Override with
# EVIDENCE_LEDGER_DASHBOARD_URL; blank string hides the cross-link.
_DEFAULT_LEDGER_DASHBOARD_URL = "https://d2pfirb2397ixy.cloudfront.net"


@dataclass(frozen=True)
class Settings:
    ledger_source: str          # "fixtures" | "sandbox" | "live"
    audit_api_url: str
    audit_read_key: str
    db_url: str
    fixtures_dir: str
    manifest_path: str | None = None   # repo evidence manifest, if configured
    store: str = "sqlite"              # "sqlite" | "dynamodb"
    table_name: str | None = None      # DynamoDB table name (store=dynamodb)
    admin_api_key: str | None = None   # if set, x-api-key is enforced
    secret_arn: str | None = None      # Secrets Manager ARN (AWS): admin + ledger keys
    ledger_dashboard_url: str = ""     # link shown in the Hub dashboard header


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

    admin_api_key = os.environ.get("EVIDENCE_ADMIN_KEY", "").strip() or None
    secret_arn = os.environ.get("EVIDENCE_SECRET_ARN", "").strip() or None

    # In AWS the admin key and ledger read key live in one Secrets Manager secret
    # ({"admin_api_key": ..., "ledger_read_key": ...}). Fill any gaps from it.
    if secret_arn and (not admin_api_key or not read_key):
        try:
            from .secrets import get_secret_json
            sec = get_secret_json(secret_arn)
            admin_api_key = admin_api_key or (sec.get("admin_api_key") or None)
            read_key = read_key or sec.get("ledger_read_key", "")
        except Exception:  # pragma: no cover - missing boto3/secret in local dev
            pass

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
        manifest_path=(os.environ.get("EVIDENCE_MANIFEST_PATH", "").strip() or None),
        store=os.environ.get("EVIDENCE_STORE", "sqlite").strip().lower(),
        table_name=(os.environ.get("EVIDENCE_TABLE_NAME", "").strip() or None),
        admin_api_key=admin_api_key,
        secret_arn=secret_arn,
        ledger_dashboard_url=os.environ.get(
            "EVIDENCE_LEDGER_DASHBOARD_URL", _DEFAULT_LEDGER_DASHBOARD_URL).strip(),
    )
