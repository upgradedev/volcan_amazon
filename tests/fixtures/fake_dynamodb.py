"""In-memory stand-ins for the DynamoDB table and the Secrets Manager client.

No test in this repository calls AWS. ``FakeTable`` implements the subset of the
boto3 Table and client API that ``src/infrastructure/dynamodb_state.py`` and
``src/infrastructure/dynamodb_audit_repository.py`` use, including conditional
puts, all-or-nothing transactions, and queries that honour sort direction,
``Limit`` and paging. The transaction client stands in for ``Table.meta.client``,
the client of a boto3 *resource*: like the real one it takes plain Python values
and serializes them itself, so an item that arrives already serialized is
serialized twice, its key becomes a map, and DynamoDB's ValidationException is
raised, exactly as the live table answers. ``install_fake_aws`` swaps boto3's constructors for these
fakes and refuses any other AWS service, so a code path the fakes do not cover
fails loudly instead of reaching a real account.
"""
from __future__ import annotations

import threading
import time
from types import SimpleNamespace

from boto3.dynamodb.types import TypeDeserializer, TypeSerializer


class ConditionalFailure(Exception):
    response = {"Error": {"Code": "ConditionalCheckFailedException"}}


class TransactionFailure(Exception):
    response = {
        "Error": {"Code": "TransactionCanceledException"},
        "CancellationReasons": [{"Code": "ConditionalCheckFailed"}],
    }


class ValidationFailure(Exception):
    """What DynamoDB answers for a key attribute of the wrong type."""

    response = {"Error": {"Code": "ValidationException"}}


class FakeTransactionClient:
    """The resource-level client: plain values in, serialized once, as boto3 does."""

    def __init__(self, table: "FakeTable") -> None:
        self.table = table
        self.serializer = TypeSerializer()
        self.deserializer = TypeDeserializer()

    def _plain(self, values, *, keyed: bool = False):
        # boto3's resource client runs TypeSerializer on every value (a float
        # raises here as it does there). DynamoDB then checks the key schema:
        # pk and sk are strings, and a map in their place is refused.
        wire = {key: self.serializer.serialize(value) for key, value in values.items()}
        if keyed:
            for key in ("pk", "sk"):
                if set(wire.get(key, {})) != {"S"}:
                    raise ValidationFailure(
                        "One or more parameter values were invalid: "
                        f"Type mismatch for key {key} expected: S actual: {next(iter(wire.get(key) or {'NULL': 0}))}"
                    )
        return {key: self.deserializer.deserialize(value) for key, value in wire.items()}

    def transact_write_items(self, TransactItems):
        puts = [item["Put"] for item in TransactItems]
        decoded = [self._plain(item["Item"], keyed=True) for item in puts]
        with self.table.lock:
            kinds = {str(item.get("kind", "")) for item in decoded}
            is_stage = bool(
                {"review_session", "voice_session"} & kinds
                and "governed_action" in kinds
            )
            is_finalize = "audit_finalization" in kinds
            if is_stage and self.table.fail_stage_once:
                self.table.fail_stage_once = False
                raise RuntimeError("stage transaction unavailable")
            if is_finalize and self.table.fail_finalize_once:
                self.table.fail_finalize_once = False
                raise RuntimeError("finalize transaction unavailable")
            for operation, item in zip(puts, decoded, strict=True):
                current = self.table.items.get((item["pk"], item["sk"]))
                condition = operation.get("ConditionExpression")
                if condition == "attribute_not_exists(pk)" and current is not None:
                    raise TransactionFailure()
                if condition == "#revision = :expected AND #owner = :owner":
                    values = self._plain(operation["ExpressionAttributeValues"])
                    if (
                        current is None
                        or current.get("revision") != values[":expected"]
                        or current.get("owner") != values[":owner"]
                    ):
                        raise TransactionFailure()
                if condition == "#state = :expected AND payload_hash = :payload_hash":
                    values = self._plain(operation["ExpressionAttributeValues"])
                    if (
                        current is None
                        or current.get("state") != values[":expected"]
                        or current.get("payload_hash") != values[":payload_hash"]
                    ):
                        raise TransactionFailure()
                if condition and condition.startswith("#head ="):
                    values = self._plain(operation["ExpressionAttributeValues"])
                    if (
                        current is None
                        or current.get("entry_hash") != values[":expected"]
                        or current.get("sequence") != values[":previous"]
                    ):
                        raise TransactionFailure()
            for item in decoded:
                self.table.items[(item["pk"], item["sk"])] = dict(item)
            if is_stage and self.table.commit_then_fail_stage_once:
                self.table.commit_then_fail_stage_once = False
                raise RuntimeError("stage response lost")
            if is_finalize and self.table.commit_then_fail_finalize_once:
                self.table.commit_then_fail_finalize_once = False
                raise RuntimeError("finalize response lost")


class FakeTable:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str], dict] = {}
        self.lock = threading.RLock()
        self.fail_stage_once = False
        self.commit_then_fail_stage_once = False
        self.fail_finalize_once = False
        self.commit_then_fail_finalize_once = False
        self.queries = 0
        self.read_delay_sec = 0.0
        self.meta = SimpleNamespace(client=FakeTransactionClient(self))

    @staticmethod
    def _key(value):
        return value["pk"], value["sk"]

    def put_item(
        self,
        Item,
        ConditionExpression=None,
        ExpressionAttributeNames=None,
        ExpressionAttributeValues=None,
    ):
        with self.lock:
            current = self.items.get(self._key(Item))
            if ConditionExpression == "attribute_not_exists(pk)" and current is not None:
                raise ConditionalFailure()
            if ConditionExpression == "#revision = :expected AND #owner = :owner":
                values = ExpressionAttributeValues
                if (
                    current is None
                    or current.get("revision") != values[":expected"]
                    or current.get("owner") != values[":owner"]
                ):
                    raise ConditionalFailure()
            if ConditionExpression == "#state = :expected AND payload_hash = :payload_hash":
                values = ExpressionAttributeValues
                if (
                    current is None
                    or current.get("state") != values[":expected"]
                    or current.get("payload_hash") != values[":payload_hash"]
                ):
                    raise ConditionalFailure()
            self.items[self._key(Item)] = dict(Item)
        return {}

    def get_item(self, Key, **_kwargs):
        with self.lock:
            item = self.items.get(self._key(Key))
            snapshot = {"Item": dict(item)} if item else {}
        if self.read_delay_sec:
            # The snapshot is returned late, which widens the gap between
            # reading a chain head and writing past it, so parallel writers
            # really do collide the way Lambda workers can.
            time.sleep(self.read_delay_sec)
        return snapshot

    def query(
        self,
        ExpressionAttributeValues,
        ScanIndexForward=True,
        Limit=None,
        ExclusiveStartKey=None,
        **_kwargs,
    ):
        """Honours sort direction, Limit and paging the way DynamoDB does."""
        self.queries += 1
        pk = ExpressionAttributeValues[":pk"]
        prefix = ExpressionAttributeValues[":prefix"]
        with self.lock:
            rows = sorted(
                (
                    dict(item) for (item_pk, sk), item in self.items.items()
                    if item_pk == pk and sk.startswith(prefix)
                ),
                key=lambda item: item["sk"],
                reverse=not ScanIndexForward,
            )
        if ExclusiveStartKey is not None:
            last = ExclusiveStartKey["sk"]
            rows = [
                row for row in rows
                if (row["sk"] > last if ScanIndexForward else row["sk"] < last)
            ]
        if Limit is not None and len(rows) > Limit:
            page = rows[:Limit]
            return {
                "Items": page,
                "LastEvaluatedKey": {"pk": pk, "sk": page[-1]["sk"]},
            }
        return {"Items": rows}


class FakeSecretsManager:
    """Answers one secret id with one SecretString, and records every request."""

    def __init__(self, secret_id: str, secret_string: str) -> None:
        self._secret_id = secret_id
        self._secret_string = secret_string
        self.requested: list[str] = []

    def get_secret_value(self, SecretId):
        self.requested.append(SecretId)
        if SecretId != self._secret_id:
            raise RuntimeError("ResourceNotFoundException")
        return {"SecretString": self._secret_string}


class UnexpectedAwsCall(RuntimeError):
    """A code path asked boto3 for something these fakes do not provide."""


def install_fake_aws(table: FakeTable, secrets: FakeSecretsManager, table_name: str) -> None:
    """Point boto3.resource/boto3.client at the fakes, for one process.

    Only the DynamoDB resource for ``table_name`` and the Secrets Manager client
    exist. Anything else raises, so an unpatched call can never fall through to
    the credential chain of the machine running the tests.
    """
    import boto3

    class _Resource:
        def Table(self, name):  # noqa: N802 - boto3's own spelling
            if name != table_name:
                raise UnexpectedAwsCall(f"unexpected DynamoDB table {name!r}")
            return table

    def fake_resource(service_name, *args, **kwargs):
        if service_name != "dynamodb":
            raise UnexpectedAwsCall(f"unexpected boto3.resource({service_name!r})")
        return _Resource()

    def fake_client(service_name, *args, **kwargs):
        if service_name != "secretsmanager":
            raise UnexpectedAwsCall(f"unexpected boto3.client({service_name!r})")
        return secrets

    boto3.resource = fake_resource
    boto3.client = fake_client
