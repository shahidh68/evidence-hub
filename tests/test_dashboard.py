from conftest import EXAMPLE_EVENT_ID

from fastapi.testclient import TestClient

from evidence_hub.api import create_app

client = TestClient(create_app())


def _seed():
    client.post("/evidence/evaluate", json={"event_id": EXAMPLE_EVENT_ID})


def test_dashboard_decisions():
    _seed()
    r = client.get("/dashboard/decisions")
    assert r.status_code == 200
    rows = r.json()
    row = next(d for d in rows if d["decision_id"] == EXAMPLE_EVENT_ID)
    assert row["current_evidence_status"] == "partial"
    assert row["open_gaps"] > 0
    assert row["integrity_status"] == "verified"


def test_dashboard_gap_queue():
    _seed()
    r = client.get("/dashboard/gaps")
    assert r.status_code == 200
    gaps = r.json()
    model_gap = next(g for g in gaps if g["gap"] == "model_registry_reference")
    assert model_gap["owner"] == "ModelOps"
    assert model_gap["priority"] == "high"


def test_dashboard_models_and_packs():
    _seed()
    assert client.get("/dashboard/models").status_code == 200
    # Generate a pack, then it should appear in the packs list.
    client.post("/audit-pack", json={"scope": "per_decision", "decision_id": EXAMPLE_EVENT_ID})
    packs = client.get("/dashboard/audit-packs").json()
    assert any(p["decision_id"] == EXAMPLE_EVENT_ID for p in packs)


def test_root_redirects_to_ui():
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (307, 308)
    assert r.headers["location"] == "/ui/"


def test_ui_index_served():
    r = client.get("/ui/")
    assert r.status_code == 200
    assert "Evidence Hub" in r.text
