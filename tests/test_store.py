"""Store-contract tests: the same behavior must hold on SqlStore and DynamoStore.

DynamoStore runs against a moto-mocked DynamoDB table so no AWS is needed.
"""

import os

import pytest

from conftest import EXAMPLE_EVENT_ID

from evidence_hub import readiness, registry, service
from evidence_hub.resolvers.manifest import ManifestResolver
from evidence_hub.schemas import EvidenceUpdateRequest, UpdateStatus
from evidence_hub.store.sql import SqlStore

MANIFEST = os.path.join(os.path.dirname(__file__), "evidence-manifest.json")


@pytest.fixture(params=["sql", "dynamo"])
def any_store(request):
    if request.param == "sql":
        yield SqlStore("sqlite://")
        return

    moto = pytest.importorskip("moto")
    import boto3
    from evidence_hub.store.dynamo import DynamoStore

    os.environ.setdefault("AWS_DEFAULT_REGION", "eu-west-1")
    os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
    with moto.mock_aws():
        ddb = boto3.resource("dynamodb", region_name="eu-west-1")
        ddb.create_table(
            TableName="EvidenceHubTest",
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"},
                       {"AttributeName": "sk", "KeyType": "RANGE"}],
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"},
                                  {"AttributeName": "sk", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield DynamoStore("EvidenceHubTest", client=ddb)


def test_evaluate_resolve_readiness(any_store, source):
    ev = service.evaluate_decision(any_store, source, EXAMPLE_EVENT_ID)
    assert ev.evidence_status.value == "partial"

    # index + latest-of-type round-trips
    assert EXAMPLE_EVENT_ID in any_store.list_decision_ids()
    assert any_store.latest_evaluation(EXAMPLE_EVENT_ID).decision_id == EXAMPLE_EVENT_ID
    assert any_store.latest_normalized(EXAMPLE_EVENT_ID).event_id == EXAMPLE_EVENT_ID
    assert any_store.latest_snapshot(EXAMPLE_EVENT_ID)["record"]["event_id"] == EXAMPLE_EVENT_ID

    resolver = ManifestResolver.from_path(MANIFEST)
    applied = service.resolve_decision(any_store, resolver, EXAMPLE_EVENT_ID)
    assert "policy_check_reference" in applied

    view = readiness.build_readiness(any_store, EXAMPLE_EVENT_ID)
    assert "policy_check_reference" in view.resolved_gaps
    assert "model_registry_reference" in view.open_gaps  # model gap stays open


def test_updates_append_only_and_ordered(any_store):
    for status in (UpdateStatus.in_progress, UpdateStatus.verified):
        registry.record_update(any_store, EvidenceUpdateRequest(
            decision_id="d1", gap="data_lineage_reference", owner="x",
            action="a", status=status))
    ups = any_store.list_updates("d1")
    assert [u.status for u in ups] == [UpdateStatus.in_progress, UpdateStatus.verified]


def test_packs_listed_newest_first(any_store, source):
    from evidence_hub import audit_pack
    service.evaluate_decision(any_store, source, EXAMPLE_EVENT_ID)
    p1 = audit_pack.build_audit_pack(any_store, EXAMPLE_EVENT_ID)
    any_store.add_pack(p1)
    p2 = audit_pack.build_audit_pack(any_store, EXAMPLE_EVENT_ID)
    any_store.add_pack(p2)
    packs = any_store.list_packs()
    assert len(packs) == 2
    assert packs[0].audit_pack_id == p2.audit_pack_id  # newest first
