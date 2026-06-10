"""Pluggable storage backends for the Evidence Hub."""

from __future__ import annotations

from ..config import Settings
from .base import Store, new_seq
from .sql import SqlStore

__all__ = ["Store", "SqlStore", "make_store", "new_seq"]


def make_store(settings: Settings) -> Store:
    if settings.store == "dynamodb":
        from .dynamo import DynamoStore  # lazy: only import boto3 when needed
        if not settings.table_name:
            raise ValueError("EVIDENCE_TABLE_NAME is required for store=dynamodb")
        return DynamoStore(settings.table_name)
    return SqlStore(settings.db_url)
