"""Minimal Secrets Manager reader (Python analogue of the ledger's secretsCache.ts).

Fetches a JSON secret once and caches it per ARN for the life of the process
(Lambda warm container), so cold start pays the only Secrets Manager call.
"""

from __future__ import annotations

import json
from typing import Any

_cache: dict[str, dict[str, Any]] = {}


def get_secret_json(secret_arn: str, *, refresh: bool = False) -> dict[str, Any]:
    if not refresh and secret_arn in _cache:
        return _cache[secret_arn]
    import boto3  # lazy: only needed in AWS
    client = boto3.client("secretsmanager")
    resp = client.get_secret_value(SecretId=secret_arn)
    data = json.loads(resp.get("SecretString") or "{}")
    _cache[secret_arn] = data
    return data
