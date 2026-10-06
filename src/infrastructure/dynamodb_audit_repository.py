"""Durable, authorization-scoped audit chains for the Volcan Lambda."""
from __future__ import annotations

import hashlib
import os
import random
import time
from collections.abc import Iterable
from typing import Any

from src.application.durable_state import DurableStateError, StateConflict
from src.domain.audit_chain import GENESIS_HASH, ChainVerdict, seal, verify_chain
from src.domain.governed_action import ActionState, AuditLogRecord, GovernedAction
from src.infrastructure.dynamodb_state import (
    ACTION_RETENTION_SEC,
    DynamoStateStore,
    _decode,
    _json,
    _transaction_conflict,
)
from src.infrastructure.state_codec import action_to_dict, audit_from_dict, audit_to_dict

#: The public demo chain is one head shared by every anonymous visitor, so a
#: conflict on it is ordinary traffic, not a fault. Retries back off with
#: jitter; the budget stays far inside the Lambda timeout.
AUDIT_APPEND_ATTEMPTS = 24


def _backoff(attempt: int) -> None:
    time.sleep(random.uniform(0.002, 0.01) * min(attempt + 1, 8))

class DynamoAuditRepository:
    """Per-authority hash chains with atomic action finalization.

    The partition key is a one-way digest of the authenticated reviewer and
    repository scope. Callers must name the scopes they are authorized to
    read; there is no global audit listing. Like ``DynamoStateStore``, every
    write passes plain Python values to the resource client, which serializes
    them once.
    """

    is_durable = True

    def __init__(
        self,
        table_name: str,
        table: Any | None = None,
        client: Any | None = None,
    ) -> None:
        if not table_name.strip():
            raise ValueError("table_name must not be empty")
        self.table_name = table_name.strip()
        if table is None:
            import boto3

            resource = boto3.resource(
                "dynamodb", region_name=os.getenv("AWS_REGION", "eu-west-1")
            )
            table = resource.Table(self.table_name)
        self._table = table
        self._client = client or table.meta.client

    @staticmethod
    def partition_for_scope(scope: str) -> str:
        if not scope.strip():
            raise ValueError("audit scope must not be empty")
        digest = hashlib.sha256(scope.encode("utf-8")).hexdigest()
        return f"audit#{digest}"

    def append_audit_record(self, record: AuditLogRecord) -> AuditLogRecord:
        scope = record.audit_scope
        for attempt in range(AUDIT_APPEND_ATTEMPTS):
            head = self._head(scope)
            previous_sequence = int(head["sequence"]) if head else -1
            previous_hash = str(head["entry_hash"]) if head else GENESIS_HASH
            sealed = seal(record, previous_hash, previous_sequence + 1)
            try:
                self._transact_append(sealed, head)
                return sealed
            except Exception as exc:
                if _transaction_conflict(exc) and attempt + 1 < AUDIT_APPEND_ATTEMPTS:
                    _backoff(attempt)
                    continue
                if _transaction_conflict(exc):
                    raise StateConflict("audit head changed repeatedly before append") from exc
                raise DurableStateError("audit record could not be committed atomically") from exc
        raise StateConflict("audit append attempts exhausted")

    def finalize_action(
        self,
        namespace: str,
        action: GovernedAction,
        expected_state: ActionState,
        record: AuditLogRecord,
    ) -> AuditLogRecord:
        """Advance the action and its audit chain in one Dynamo transaction.

        If DynamoDB rejects or cannot confirm the transaction, no caller may
        report a terminal action without a chain record. An idempotency marker
        lets a retry recognize a transaction whose response was lost.
        """
        existing = self._completed_finalize(action, record)
        if existing is not None:
            return existing
        for attempt in range(AUDIT_APPEND_ATTEMPTS):
            head = self._head(record.audit_scope)
            previous_sequence = int(head["sequence"]) if head else -1
            previous_hash = str(head["entry_hash"]) if head else GENESIS_HASH
            sealed = seal(record, previous_hash, previous_sequence + 1)
            try:
                self._transact_finalize(namespace, action, expected_state, sealed, head)
                return sealed
            except Exception as exc:
                completed = self._completed_finalize(action, record)
                if completed is not None:
                    return completed
                if _transaction_conflict(exc) and attempt + 1 < AUDIT_APPEND_ATTEMPTS:
                    _backoff(attempt)
                    continue
                if _transaction_conflict(exc):
                    raise StateConflict(
                        "action or scoped audit head changed before finalization"
                    ) from exc
                raise DurableStateError(
                    "action and audit record could not be finalized atomically"
                ) from exc
        raise StateConflict("action finalization attempts exhausted")

    def _head_put(
        self, record: AuditLogRecord, head: dict[str, Any] | None
    ) -> dict[str, Any]:
        head_item = {
            "pk": self.partition_for_scope(record.audit_scope),
            "sk": "head",
            "kind": "audit_head",
            "sequence": record.sequence,
            "entry_hash": record.entry_hash,
        }
        operation: dict[str, Any] = {
            "TableName": self.table_name,
            "Item": head_item,
        }
        if head is None:
            operation["ConditionExpression"] = "attribute_not_exists(pk)"
        else:
            operation.update(
                ConditionExpression="#head = :expected AND #sequence = :previous",
                ExpressionAttributeNames={"#head": "entry_hash", "#sequence": "sequence"},
                ExpressionAttributeValues={
                    ":expected": str(head["entry_hash"]),
                    ":previous": int(head["sequence"]),
                },
            )
        return operation

    def _record_item(self, record: AuditLogRecord) -> dict[str, Any]:
        return {
            "pk": self.partition_for_scope(record.audit_scope),
            "sk": f"record#{record.sequence:020d}",
            "kind": "audit_record",
            "record_id": record.record_id,
            "payload_json": _json(audit_to_dict(record)),
        }

    def _transact_append(
        self, record: AuditLogRecord, head: dict[str, Any] | None
    ) -> None:
        self._client.transact_write_items(
            TransactItems=[
                {"Put": self._head_put(record, head)},
                {
                    "Put": {
                        "TableName": self.table_name,
                        "Item": self._record_item(record),
                        "ConditionExpression": "attribute_not_exists(pk)",
                    }
                },
            ]
        )

    @staticmethod
    def _outcome_hash(record: AuditLogRecord) -> str:
        return hashlib.sha256(record.execution_stdout.encode("utf-8")).hexdigest()

    def _marker_key(self, record: AuditLogRecord) -> dict[str, str]:
        digest = hashlib.sha256(record.record_id.encode("utf-8")).hexdigest()
        return {"pk": self.partition_for_scope(record.audit_scope), "sk": f"final#{digest}"}

    def _transact_finalize(
        self,
        namespace: str,
        action: GovernedAction,
        expected_state: ActionState,
        record: AuditLogRecord,
        head: dict[str, Any] | None,
    ) -> None:
        action_item = {
            **DynamoStateStore._action_key(namespace, action.action_id),
            "kind": "governed_action",
            "namespace": namespace,
            "state": action.state.value,
            "payload_hash": action.payload_hash,
            "payload_json": _json(action_to_dict(action)),
            "expires_at": int(action.expires_at_epoch) + ACTION_RETENTION_SEC,
        }
        marker = {
            **self._marker_key(record),
            "kind": "audit_finalization",
            "action_id": action.action_id,
            "payload_hash": action.payload_hash,
            "terminal_state": action.state.value,
            "outcome_hash": self._outcome_hash(record),
            "record_sk": f"record#{record.sequence:020d}",
            "entry_hash": record.entry_hash,
        }
        self._client.transact_write_items(
            TransactItems=[
                {
                    "Put": {
                        "TableName": self.table_name,
                        "Item": action_item,
                        "ConditionExpression": (
                            "#state = :expected AND payload_hash = :payload_hash"
                        ),
                        "ExpressionAttributeNames": {"#state": "state"},
                        "ExpressionAttributeValues": {
                            ":expected": expected_state.value,
                            ":payload_hash": action.payload_hash,
                        },
                    }
                },
                {"Put": self._head_put(record, head)},
                {
                    "Put": {
                        "TableName": self.table_name,
                        "Item": self._record_item(record),
                        "ConditionExpression": "attribute_not_exists(pk)",
                    }
                },
                {
                    "Put": {
                        "TableName": self.table_name,
                        "Item": marker,
                        "ConditionExpression": "attribute_not_exists(pk)",
                    }
                },
            ]
        )

    def _completed_finalize(
        self, action: GovernedAction, record: AuditLogRecord
    ) -> AuditLogRecord | None:
        marker = self._get(self._marker_key(record))
        if marker is None:
            return None
        matches = (
            marker.get("action_id") == action.action_id
            and marker.get("payload_hash") == action.payload_hash
            and marker.get("terminal_state") == action.state.value
            and marker.get("outcome_hash") == self._outcome_hash(record)
        )
        if not matches:
            raise StateConflict("audit finalization id is already bound to another outcome")
        row = self._get({"pk": marker["pk"], "sk": str(marker["record_sk"])})
        payload = _decode(row)
        if payload is None:
            raise DurableStateError("audit finalization marker has no corresponding record")
        return audit_from_dict(payload)

    def _get(self, key: dict[str, str]) -> dict[str, Any] | None:
        try:
            return self._table.get_item(Key=key, ConsistentRead=True).get("Item")
        except Exception as exc:
            raise DurableStateError("scoped audit state could not be read") from exc

    def _head(self, scope: str) -> dict[str, Any] | None:
        return self._get({"pk": self.partition_for_scope(scope), "sk": "head"})

    def _query_scope(self, scope: str) -> list[AuditLogRecord]:
        values = {":pk": self.partition_for_scope(scope), ":prefix": "record#"}
        try:
            response = self._table.query(
                KeyConditionExpression="pk = :pk AND begins_with(sk, :prefix)",
                ExpressionAttributeValues=values,
                ScanIndexForward=True,
                ConsistentRead=True,
            )
            items = list(response.get("Items", []))
            while response.get("LastEvaluatedKey"):
                response = self._table.query(
                    KeyConditionExpression="pk = :pk AND begins_with(sk, :prefix)",
                    ExpressionAttributeValues=values,
                    ExclusiveStartKey=response["LastEvaluatedKey"],
                    ScanIndexForward=True,
                    ConsistentRead=True,
                )
                items.extend(response.get("Items", []))
        except Exception as exc:
            raise DurableStateError("scoped audit records could not be read") from exc
        return [audit_from_dict(payload) for row in items if (payload := _decode(row))]

    def list_records(self, scopes: Iterable[str] | None = None) -> list[AuditLogRecord]:
        if scopes is None:
            raise DurableStateError("explicit authorized audit scopes are required")
        authorized = sorted({scope for scope in scopes if scope.strip()})
        records = [record for scope in authorized for record in self._query_scope(scope)]
        return sorted(records, key=lambda record: (record.audit_scope, record.sequence))

    def list_recent(self, scope: str, limit: int) -> list[AuditLogRecord]:
        """The newest ``limit`` records of one scope, oldest first.

        One descending query with a Limit, so a long public chain costs one
        bounded read rather than a walk of every record ever sealed.
        """
        if limit < 1:
            return []
        try:
            response = self._table.query(
                KeyConditionExpression="pk = :pk AND begins_with(sk, :prefix)",
                ExpressionAttributeValues={
                    ":pk": self.partition_for_scope(scope), ":prefix": "record#",
                },
                ScanIndexForward=False,
                Limit=limit,
                ConsistentRead=True,
            )
        except Exception as exc:
            raise DurableStateError("scoped audit records could not be read") from exc
        records = [
            audit_from_dict(payload)
            for row in response.get("Items", []) if (payload := _decode(row))
        ]
        return sorted(records, key=lambda record: record.sequence)

    def record_count(self, scope: str) -> int:
        """How many records the scope's chain holds, read from its head."""
        head = self._head(scope)
        return int(head["sequence"]) + 1 if head else 0

    def get_record(
        self, record_id: str, scopes: Iterable[str] | None = None
    ) -> AuditLogRecord | None:
        return next(
            (record for record in self.list_records(scopes) if record.record_id == record_id),
            None,
        )

    def verify_integrity(self, scope: str) -> ChainVerdict:
        return verify_chain(self._query_scope(scope))

    def head_hash(self, scope: str) -> str:
        head = self._head(scope)
        return str(head["entry_hash"]) if head else GENESIS_HASH
