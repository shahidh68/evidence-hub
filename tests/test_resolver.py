import os

from conftest import EXAMPLE_EVENT_ID

from fastapi.testclient import TestClient

from evidence_hub import readiness, registry, service
from evidence_hub.resolvers.manifest import ManifestResolver

MANIFEST = os.path.join(os.path.dirname(__file__), "evidence-manifest.json")
CLEAN_EVENT_ID = "11111111-1111-4111-8111-111111111111"


def test_resolves_data_policy_prompt_gaps_for_spec_example(store, source):
    service.evaluate_decision(store, source, EXAMPLE_EVENT_ID)
    before = readiness.build_readiness(store, EXAMPLE_EVENT_ID)

    resolver = ManifestResolver.from_path(MANIFEST)
    applied = service.resolve_decision(store, resolver, EXAMPLE_EVENT_ID)

    assert {"data_lineage_reference", "data_quality_check_reference",
            "policy_check_reference", "policy_version",
            "prompt_version_reference", "retention_classification",
            "privacy_classification"}.issubset(set(applied))

    after = readiness.build_readiness(store, EXAMPLE_EVENT_ID)
    assert after.audit_readiness_score > before.audit_readiness_score
    assert "data_lineage_reference" in after.resolved_gaps
    # Model gaps stay OPEN: the ledger logged reviewer metadata in model_version,
    # so there is no model_version to join the manifest on. Correctly unresolved.
    assert "model_registry_reference" in after.open_gaps


def test_resolves_model_gaps_for_clean_decision(store, source):
    service.evaluate_decision(store, source, CLEAN_EVENT_ID)
    resolver = ManifestResolver.from_path(MANIFEST)
    applied = service.resolve_decision(store, resolver, CLEAN_EVENT_ID)
    assert {"model_registry_reference", "model_approval_reference"}.issubset(set(applied))


def test_provenance_records_source_and_signature(store, source):
    service.evaluate_decision(store, source, EXAMPLE_EVENT_ID)
    resolver = ManifestResolver.from_path(MANIFEST)
    service.resolve_decision(store, resolver, EXAMPLE_EVENT_ID)

    updates = [u for u in registry.list_updates(store, EXAMPLE_EVENT_ID)
               if u.gap == "policy_check_reference"]
    assert updates, "expected a resolved update for policy_check_reference"
    upd = updates[-1]
    assert upd.status.value == "verified"
    assert upd.provenance.source_system.startswith("repo-manifest")
    assert upd.provenance.signature.startswith("sha256:")
    assert upd.artifact_refs.policy_check_reference == "opa:policy:loan-triage"


def test_resolution_is_idempotent(store, source):
    service.evaluate_decision(store, source, EXAMPLE_EVENT_ID)
    resolver = ManifestResolver.from_path(MANIFEST)
    first = service.resolve_decision(store, resolver, EXAMPLE_EVENT_ID)
    second = service.resolve_decision(store, resolver, EXAMPLE_EVENT_ID)
    assert first and second == []


def test_resolve_endpoint(monkeypatch, tmp_path):
    monkeypatch.setenv("EVIDENCE_MANIFEST_PATH", MANIFEST)
    monkeypatch.setenv("EVIDENCE_DB_URL", f"sqlite:///{tmp_path / 'resolve.db'}")
    from evidence_hub.api import create_app
    client = TestClient(create_app())

    # evaluate auto-resolves when a manifest is configured
    client.post("/evidence/evaluate", json={"event_id": EXAMPLE_EVENT_ID})
    view = client.get(f"/evidence/readiness/{EXAMPLE_EVENT_ID}").json()
    assert "policy_check_reference" in view["resolved_gaps"]

    # explicit resolve is idempotent (already auto-resolved)
    r = client.post("/evidence/resolve", json={"decision_id": EXAMPLE_EVENT_ID})
    assert r.status_code == 200
    assert r.json()["resolved"] == []
