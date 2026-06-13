"""DynamoDB-backed Store (single-table, append-only).

Item layout
-----------
Decision-scoped items share a partition so one Query returns everything for a
decision in insertion order:

    pk = "DEC#<decision_id>"
    sk = "<TYPE>#<seq>"      TYPE ∈ {SNAP, NORM, EVAL, UPD};  seq = sortable token
    data = JSON string payload   (gap denormalized onto UPD items)

Index partitions answer the cross-decision queries:

    pk = "IDX#DECISIONS"  sk = "<decision_id>"          -> list_decision_ids
    pk = "IDX#PACKS"      sk = "<seq>"  data = pack JSON -> list_packs (desc)
    pk = "IDX#AUDITLOG"   sk = "<seq>"  data = entry JSON

"Latest of type" = Query begins_with(sk, "EVAL#") ScanIndexForward=False Limit=1.
Nothing is ever overwritten.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from ..schemas import (
    AuditPack,
    EvidenceEvaluation,
    EvidenceUpdate,
    NormalizedDecisionEvent,
)
from .base import new_seq


def _dec_pk(decision_id: str) -> str:
    return f"DEC#{decision_id}"


class DynamoStore:
    def __init__(self, table_name: str, *, client=None) -> None:
        import boto3  # lazy: only needed for the AWS backend
        resource = client or boto3.resource("dynamodb")
        self.table = resource.Table(table_name)

    # ── writes ──
    def _put(self, pk: str, sk: str, **extra: Any) -> None:
        self.table.put_item(Item={"pk": pk, "sk": sk, **extra})

    def _index_decision(self, decision_id: str, tenant: str | None) -> None:
        # Idempotent upserts: a global index (admin view) and, when known, a
        # per-tenant index so a scoped viewer only sees their own decisions.
        self._put("IDX#DECISIONS", decision_id)
        if tenant:
            self._put(f"IDX#TENANT#{tenant}", decision_id)

    def add_snapshot(self, decision_id, event_id, tenant_id, record, tamper):
        self._put(_dec_pk(decision_id), f"SNAP#{new_seq()}",
                  data=json.dumps({"record": record, "tamper": tamper}),
                  event_id=event_id, tenant_id=tenant_id or "")

    def add_normalized(self, event: NormalizedDecisionEvent):
        self._put(_dec_pk(event.decision_id), f"NORM#{new_seq()}",
                  data=json.dumps(event.model_dump(mode="json")))

    def add_evaluation(self, evaluation: EvidenceEvaluation):
        self._put(_dec_pk(evaluation.decision_id), f"EVAL#{new_seq()}",
                  data=json.dumps(evaluation.model_dump(mode="json")))
        self._index_decision(evaluation.decision_id, evaluation.tenant_id)

    def add_update(self, update: EvidenceUpdate):
        self._put(_dec_pk(update.decision_id), f"UPD#{new_seq()}",
                  data=json.dumps(update.model_dump(mode="json")), gap=update.gap or "")

    def add_pack(self, pack: AuditPack):
        seq = new_seq()
        body = json.dumps(pack.model_dump(mode="json"))
        self._put("IDX#PACKS", seq, data=body, decision_id=pack.decision_id)
        if pack.tenant_id:
            self._put(f"IDX#PACKS#{pack.tenant_id}", seq, data=body, decision_id=pack.decision_id)

    def add_audit_log(self, action, decision_id=None, actor=None, detail=None):
        entry = {"action": action, "decision_id": decision_id, "actor": actor,
                 "detail": detail, "created_at": datetime.now(timezone.utc).isoformat()}
        self._put("IDX#AUDITLOG", new_seq(), data=json.dumps(entry), action=action)

    # ── reads ──
    def _latest(self, decision_id: str, type_prefix: str) -> Optional[dict]:
        from boto3.dynamodb.conditions import Key
        resp = self.table.query(
            KeyConditionExpression=Key("pk").eq(_dec_pk(decision_id))
            & Key("sk").begins_with(f"{type_prefix}#"),
            ScanIndexForward=False, Limit=1,
        )
        items = resp.get("Items", [])
        return json.loads(items[0]["data"]) if items else None

    def latest_evaluation(self, decision_id):
        data = self._latest(decision_id, "EVAL")
        return EvidenceEvaluation.model_validate(data) if data else None

    def latest_normalized(self, decision_id):
        data = self._latest(decision_id, "NORM")
        return NormalizedDecisionEvent.model_validate(data) if data else None

    def latest_snapshot(self, decision_id):
        return self._latest(decision_id, "SNAP")  # {"record":..., "tamper":...}

    def list_updates(self, decision_id):
        from boto3.dynamodb.conditions import Key
        resp = self.table.query(
            KeyConditionExpression=Key("pk").eq(_dec_pk(decision_id))
            & Key("sk").begins_with("UPD#"),
            ScanIndexForward=True,
        )
        return [EvidenceUpdate.model_validate(json.loads(i["data"])) for i in resp.get("Items", [])]

    def list_packs(self, tenant=None):
        from boto3.dynamodb.conditions import Key
        pk = f"IDX#PACKS#{tenant}" if tenant is not None else "IDX#PACKS"
        resp = self.table.query(KeyConditionExpression=Key("pk").eq(pk), ScanIndexForward=False)
        return [AuditPack.model_validate(json.loads(i["data"])) for i in resp.get("Items", [])]

    def list_decision_ids(self, tenant=None):
        from boto3.dynamodb.conditions import Key
        pk = f"IDX#TENANT#{tenant}" if tenant is not None else "IDX#DECISIONS"
        resp = self.table.query(KeyConditionExpression=Key("pk").eq(pk))
        return [i["sk"] for i in resp.get("Items", [])]
