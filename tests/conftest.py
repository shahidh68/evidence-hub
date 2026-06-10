"""Shared test configuration and fixtures.

All tests run with LEDGER_SOURCE=fixtures so they are fully offline (no SDK, no
network). The Evidence Hub's own storage uses a throwaway SQLite file.
"""

from __future__ import annotations

import os
import tempfile

import pytest

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
EXAMPLE_EVENT_ID = "a92ffa42-27a8-4e46-81d6-b9b1a654077f"

# Set before any evidence_hub import so the module-level app picks these up.
_TEST_DB = os.path.join(tempfile.gettempdir(), "evidence_hub_test.db")
os.environ["LEDGER_SOURCE"] = "fixtures"
os.environ["EVIDENCE_FIXTURES_DIR"] = FIXTURES_DIR
os.environ["EVIDENCE_DB_URL"] = f"sqlite:///{_TEST_DB}"
if os.path.exists(_TEST_DB):
    os.remove(_TEST_DB)


@pytest.fixture
def settings():
    from evidence_hub.config import Settings
    return Settings(
        ledger_source="fixtures",
        audit_api_url="",
        audit_read_key="",
        db_url="sqlite://",  # in-memory, single engine
        fixtures_dir=FIXTURES_DIR,
    )


@pytest.fixture
def session(settings):
    from evidence_hub.db import make_engine_and_session
    _engine, SessionLocal = make_engine_and_session(settings)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def source(settings):
    from evidence_hub.ledger_source import make_source
    return make_source(settings)
