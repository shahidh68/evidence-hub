from conftest import EXAMPLE_EVENT_ID

from fastapi.testclient import TestClient

from evidence_hub.api import create_app

client = TestClient(create_app())


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["ledger_source"] == "fixtures"


def test_full_flow_evaluate_update_readiness_pack():
    # 1. Evaluate
    r = client.post("/evidence/evaluate", json={"event_id": EXAMPLE_EVENT_ID})
    assert r.status_code == 200, r.text
    ev = r.json()
    assert ev["decision_id"] == EXAMPLE_EVENT_ID
    assert ev["evidence_status"] == "partial"
    assert "data_lineage_reference" in ev["missing_evidence"]

    # 2. Record an evidence update that resolves a gap
    for status in ("in_progress", "verified"):
        r = client.post("/evidence/evidence-update", json={
            "decision_id": EXAMPLE_EVENT_ID,
            "gap": "data_lineage_reference",
            "owner": "Data Governance",
            "action": "Attach data lineage reference",
            "status": status,
            "artifact_type": "data_lineage",
            "artifact_refs": {"data_lineage_reference": "atlas:lineage:dataset_12345"},
        })
        assert r.status_code == 200, r.text
    assert r.json()["status"] == "recorded"

    # 3. Readiness reflects the resolved gap
    r = client.get(f"/evidence/readiness/{EXAMPLE_EVENT_ID}")
    assert r.status_code == 200, r.text
    view = r.json()
    assert "data_lineage_reference" in view["resolved_gaps"]
    assert "data_lineage_reference" not in view["open_gaps"]

    # 4. Graph has the ledger-derived based_on edges
    r = client.get(f"/evidence/graph/{EXAMPLE_EVENT_ID}")
    assert r.status_code == 200, r.text
    relations = {(e["from"], e["relation"]) for e in r.json()}
    assert any(rel == "based_on" for _, rel in relations)

    # 5. Audit pack assembles the expected sections
    r = client.post("/audit-pack", json={
        "scope": "per_decision", "decision_id": EXAMPLE_EVENT_ID, "format": "json",
    })
    assert r.status_code == 200, r.text
    pack = r.json()
    assert pack["status"] == "generated"
    for section in ("ledger_record", "tamper_evidence", "evidence_evaluation",
                    "remediation_history", "evidence_graph"):
        assert section in pack["sections"]


def test_audit_pack_rejects_unsupported_scope():
    r = client.post("/audit-pack", json={"scope": "per_model", "decision_id": "x"})
    assert r.status_code == 400


def test_evaluate_unknown_event_404():
    r = client.post("/evidence/evaluate", json={"event_id": "00000000-0000-4000-8000-000000000000"})
    assert r.status_code == 404
