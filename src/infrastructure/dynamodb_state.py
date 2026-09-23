"""Shared DynamoDB state for Volcan's multi-turn Lambda flows.

One PAY_PER_REQUEST table stores versioned review and voice sessions, governed
actions, globally spent grant nonces and the audit chain.  Every state change
uses a DynamoDB condition. A concurrent worker therefore wins once; the loser
gets a conflict and never falls back to process memory.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any

from src.application.durable_state import (
    DuplicateState,
    DurableStateError,
    ReviewSessionState,
    StateConflict,
    StateTooLarge,
    VersionedState,
    VoiceSessionState,
)
from src.domain.governed_action import ActionState, GovernedAction
from src.infrastructure.state_codec import (
    action_from_dict,
    action_to_dict,
    review_dialogue_from_dict,
    review_dialogue_to_dict,
    voice_session_from_dict,
    voice_session_to_dict,
)

MAX_PAYLOAD_BYTES = 320_000
SESSION_TTL_SEC = 2 * 60 * 60
ACTION_RETENTION_SEC = 24 * 60 * 60


def _conditional_failure(exc: Exception) -> bool:
    response = getattr(exc, "response", {})
    return response.get("Error", {}).get("Code") == "ConditionalCheckFailedException"


def _transaction_conflict(exc: Exception) -> bool:
    response = getattr(exc, "response", {})
    code = response.get("Error", {}).get("Code")
    if code != "TransactionCanceledException":
        return False
    reasons = response.get("CancellationReasons") or []
    return not reasons or any(reason.get("Code") == "ConditionalCheckFailed" for reason in reasons)


def _json(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    size = len(encoded.encode("utf-8"))
    if size > MAX_PAYLOAD_BYTES:
        raise StateTooLarge(
            f"durable state is {size} bytes; the bounded maximum is {MAX_PAYLOAD_BYTES} bytes"
        )
    return encoded


def _decode(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    try:
        value = json.loads(str(item["payload_json"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise DurableStateError("durable state item is missing valid payload_json") from exc
    if not isinstance(value, dict):
        raise DurableStateError("durable state payload must be a JSON object")
    return value


def _serialize(value: Any) -> dict[str, Any]:
    from boto3.dynamodb.types import TypeSerializer

    return TypeSerializer().serialize(value)


def _serialize_item(value: dict[str, Any]) -> dict[str, Any]:
    return {key: _serialize(raw) for key, raw in value.items()}


def _session_put(
    *, table_name: str, item: dict[str, Any], expected_revision: int, owner: str
) -> dict[str, Any]:
    operation: dict[str, Any] = {
        "TableName": table_name,
        "Item": _serialize_item(item),
    }
    if expected_revision == 0:
        operation["ConditionExpression"] = "attribute_not_exists(pk)"
    else:
        operation.update(
            ConditionExpression="#revision = :expected AND #owner = :owner",
            ExpressionAttributeNames={"#revision": "revision", "#owner": "owner"},
            ExpressionAttributeValues={
                ":expected": _serialize(expected_revision),
                ":owner": _serialize(owner),
            },
        )
    return operation


class DynamoStateStore:
    """Conditional session, action and nonce state in one DynamoDB table."""

    is_durable = True

    def __init__(
        self, table_name: str, table: Any | None = None, client: Any | None = None
    ) -> None:
        if not table_name.strip():
            raise ValueError("table_name must not be empty")
        self.table_name = table_name.strip()
        if table is None:
            import boto3

            table = boto3.resource(
                "dynamodb", region_name=os.getenv("AWS_REGION", "eu-west-1")
            ).Table(self.table_name)
        self._table = table
        self._client = client or table.meta.client
        self._burned_this_process = 0

    @classmethod
    def from_environment(cls) -> "DynamoStateStore | None":
        table_name = os.getenv("VOLCAN_STATE_TABLE", "").strip()
        return cls(table_name) if table_name else None

    @property
    def table(self) -> Any:
        return self._table

    def describe(self) -> dict[str, Any]:
        return {
            "backend": "dynamodb",
            "durable_across_restart": True,
            "shared_across_workers": True,
            "writes": "conditional",
        }

    def capability(self) -> dict[str, Any]:
        """Resolve configuration separately from current table reachability."""
        result = {**self.describe(), "configured": True}
        try:
            self._table.get_item(
                Key={"pk": "health#probe", "sk": "read"}, ConsistentRead=True
            )
        except Exception:  # Provider details can contain account/request identifiers.
            return {
                **result,
                "reachable": False,
                "resolved_capability": "configured_unreachable",
            }
        return {
            **result,
            "reachable": True,
            "resolved_capability": "configured_reachable",
        }

    # -- review dialogue -------------------------------------------------

    @staticmethod
    def _session_partition(
        kind: str,
        owner: str,
        session_id: str,
        repository: str = "",
    ) -> str:
        material = "\x00".join(
            (kind, owner.strip().lower(), repository.strip().lower(), session_id.strip())
        )
        digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
        return f"session#{kind}#{digest}"

    def load_review(
        self, session_id: str, owner: str
    ) -> VersionedState[ReviewSessionState] | None:
        item = self._get(self._session_partition("review", owner, session_id), "state")
        payload = _decode(item)
        if payload is None:
            return None
        value = ReviewSessionState(
            dialogue=review_dialogue_from_dict(payload["dialogue"]),
            owner=str(payload["owner"]),
            pending_action_id=payload.get("pending_action_id"),
            pending_grant=payload.get("pending_grant"),
            staged_count=int(payload.get("staged_count", 0)),
        )
        return VersionedState(value=value, revision=int(item["revision"]))

    def save_review(self, state: ReviewSessionState, expected_revision: int) -> int:
        payload = {
            "owner": state.owner,
            "pending_action_id": state.pending_action_id,
            "pending_grant": state.pending_grant,
            "staged_count": state.staged_count,
            "dialogue": review_dialogue_to_dict(state.dialogue),
        }
        return self._put_versioned(
            pk=self._session_partition("review", state.owner, state.dialogue.session_id),
            kind="review_session",
            owner=state.owner,
            payload=payload,
            expected_revision=expected_revision,
        )

    def save_review_with_action(
        self,
        state: ReviewSessionState,
        expected_revision: int,
        namespace: str,
        action: GovernedAction,
    ) -> int:
        payload = {
            "owner": state.owner,
            "pending_action_id": state.pending_action_id,
            "pending_grant": state.pending_grant,
            "staged_count": state.staged_count,
            "dialogue": review_dialogue_to_dict(state.dialogue),
        }
        return self._save_session_with_action(
            pk=self._session_partition("review", state.owner, state.dialogue.session_id),
            kind="review_session",
            owner=state.owner,
            payload=payload,
            expected_revision=expected_revision,
            namespace=namespace,
            action=action,
        )

    # -- voice session ---------------------------------------------------

    def load_voice(
        self, session_id: str, owner: str, repository: str
    ) -> VersionedState[VoiceSessionState] | None:
        item = self._get(
            self._session_partition("voice", owner, session_id, repository), "state"
        )
        payload = _decode(item)
        if payload is None:
            return None
        value = VoiceSessionState(
            session=voice_session_from_dict(payload["session"]),
            owner=str(payload["owner"]),
            repository=str(payload["repository"]),
        )
        return VersionedState(value=value, revision=int(item["revision"]))

    def save_voice(self, state: VoiceSessionState, expected_revision: int) -> int:
        payload = {
            "owner": state.owner,
            "repository": state.repository,
            "session": voice_session_to_dict(state.session),
        }
        return self._put_versioned(
            pk=self._session_partition(
                "voice", state.owner, state.session.session_id, state.repository
            ),
            kind="voice_session",
            owner=state.owner,
            payload=payload,
            expected_revision=expected_revision,
        )

    def save_voice_with_action(
        self,
        state: VoiceSessionState,
        expected_revision: int,
        namespace: str,
        action: GovernedAction,
    ) -> int:
        payload = {
            "owner": state.owner,
            "repository": state.repository,
            "session": voice_session_to_dict(state.session),
        }
        return self._save_session_with_action(
            pk=self._session_partition(
                "voice", state.owner, state.session.session_id, state.repository
            ),
            kind="voice_session",
            owner=state.owner,
            payload=payload,
            expected_revision=expected_revision,
            namespace=namespace,
            action=action,
        )

    def _put_versioned(
        self, *, pk: str, kind: str, owner: str, payload: dict[str, Any], expected_revision: int
    ) -> int:
        revision = expected_revision + 1
        item = {
            "pk": pk,
            "sk": "state",
            "kind": kind,
            "owner": owner,
            "revision": revision,
            "payload_json": _json(payload),
            "expires_at": int(time.time()) + SESSION_TTL_SEC,
        }
        kwargs: dict[str, Any] = {"Item": item}
        if expected_revision == 0:
            kwargs["ConditionExpression"] = "attribute_not_exists(pk)"
        else:
            kwargs.update(
                ConditionExpression="#revision = :expected AND #owner = :owner",
                ExpressionAttributeNames={"#revision": "revision", "#owner": "owner"},
                ExpressionAttributeValues={":expected": expected_revision, ":owner": owner},
            )
        try:
            self._table.put_item(**kwargs)
        except Exception as exc:
            if _conditional_failure(exc):
                raise StateConflict(f"{kind} revision or owner changed before commit") from exc
            raise DurableStateError(f"{kind} could not be committed to DynamoDB") from exc
        return revision

    def _save_session_with_action(
        self,
        *,
        pk: str,
        kind: str,
        owner: str,
        payload: dict[str, Any],
        expected_revision: int,
        namespace: str,
        action: GovernedAction,
    ) -> int:
        """Create a staged action and bind it to its session all-or-nothing."""
        revision = expected_revision + 1
        session_item = {
            "pk": pk,
            "sk": "state",
            "kind": kind,
            "owner": owner,
            "revision": revision,
            "payload_json": _json(payload),
            "expires_at": int(time.time()) + SESSION_TTL_SEC,
        }
        action_item = self._action_item(namespace, action)
        try:
            self._client.transact_write_items(
                TransactItems=[
                    {
                        "Put": _session_put(
                            table_name=self.table_name,
                            item=session_item,
                            expected_revision=expected_revision,
                            owner=owner,
                        )
                    },
                    {
                        "Put": {
                            "TableName": self.table_name,
                            "Item": _serialize_item(action_item),
                            "ConditionExpression": "attribute_not_exists(pk)",
                        }
                    },
                ]
            )
        except Exception as exc:
            if _transaction_conflict(exc):
                raise StateConflict(
                    f"{kind} revision/action changed before atomic stage commit"
                ) from exc
            raise DurableStateError(
                f"{kind} and staged action could not be committed atomically"
            ) from exc
        return revision

    # -- governed actions ------------------------------------------------

    @staticmethod
    def _action_key(namespace: str, action_id: str) -> dict[str, str]:
        material = f"{namespace}\x00{action_id}".encode("utf-8")
        return {"pk": f"action#{hashlib.sha256(material).hexdigest()}", "sk": "state"}

    def put_action(self, namespace: str, action: GovernedAction) -> None:
        item = self._action_item(namespace, action)
        try:
            self._table.put_item(Item=item, ConditionExpression="attribute_not_exists(pk)")
        except Exception as exc:
            if _conditional_failure(exc):
                raise DuplicateState(
                    f"action '{action.action_id}' already exists in namespace '{namespace}'"
                ) from exc
            raise DurableStateError("staged action could not be persisted") from exc

    def get_action(self, namespace: str, action_id: str) -> GovernedAction | None:
        item = self._get(**self._action_key(namespace, action_id))
        payload = _decode(item)
        return action_from_dict(payload) if payload else None

    def transition_action(
        self, namespace: str, action: GovernedAction, expected_state: ActionState
    ) -> None:
        item = self._action_item(namespace, action)
        try:
            self._table.put_item(
                Item=item,
                ConditionExpression="#state = :expected AND payload_hash = :payload_hash",
                ExpressionAttributeNames={"#state": "state"},
                ExpressionAttributeValues={
                    ":expected": expected_state.value,
                    ":payload_hash": action.payload_hash,
                },
            )
        except Exception as exc:
            if _conditional_failure(exc):
                raise StateConflict(
                    f"action '{action.action_id}' is no longer {expected_state.value}"
                ) from exc
            raise DurableStateError("governed action transition could not be persisted") from exc

    def claim_action_with_nonce(
        self,
        namespace: str,
        action: GovernedAction,
        expected_state: ActionState,
        nonce: str,
        nonce_expires_at: float,
    ) -> None:
        """Atomically claim an action and consume the grant nonce exactly once."""
        digest = hashlib.sha256(nonce.encode("utf-8")).hexdigest()
        nonce_item = {
            "pk": f"nonce#{digest}",
            "sk": "spent",
            "kind": "spent_nonce",
            "expires_at": int(nonce_expires_at) + ACTION_RETENTION_SEC,
        }
        try:
            self._client.transact_write_items(
                TransactItems=[
                    {
                        "Put": {
                            "TableName": self.table_name,
                            "Item": _serialize_item(self._action_item(namespace, action)),
                            "ConditionExpression": (
                                "#state = :expected AND payload_hash = :payload_hash"
                            ),
                            "ExpressionAttributeNames": {"#state": "state"},
                            "ExpressionAttributeValues": {
                                ":expected": _serialize(expected_state.value),
                                ":payload_hash": _serialize(action.payload_hash),
                            },
                        }
                    },
                    {
                        "Put": {
                            "TableName": self.table_name,
                            "Item": _serialize_item(nonce_item),
                            "ConditionExpression": "attribute_not_exists(pk)",
                        }
                    },
                ]
            )
        except Exception as exc:
            if _transaction_conflict(exc):
                raise StateConflict(
                    f"action '{action.action_id}' was already claimed or grant replayed"
                ) from exc
            raise DurableStateError("action claim and nonce burn could not be committed") from exc
        self._burned_this_process += 1

    def _action_item(self, namespace: str, action: GovernedAction) -> dict[str, Any]:
        return {
            **self._action_key(namespace, action.action_id),
            "kind": "governed_action",
            "namespace": namespace,
            "state": action.state.value,
            "payload_hash": action.payload_hash,
            "payload_json": _json(action_to_dict(action)),
            "expires_at": int(action.expires_at_epoch) + ACTION_RETENTION_SEC,
        }

    # -- single-use grant nonce -----------------------------------------

    def consume(self, nonce: str, expires_at_epoch: float) -> bool:
        digest = hashlib.sha256(nonce.encode("utf-8")).hexdigest()
        try:
            self._table.put_item(
                Item={
                    "pk": f"nonce#{digest}",
                    "sk": "spent",
                    "kind": "spent_nonce",
                    "expires_at": int(expires_at_epoch) + ACTION_RETENTION_SEC,
                },
                ConditionExpression="attribute_not_exists(pk)",
            )
        except Exception as exc:
            if _conditional_failure(exc):
                return False
            raise DurableStateError("grant nonce could not be consumed durably") from exc
        self._burned_this_process += 1
        return True

    @property
    def count(self) -> int:
        """Nonces consumed by this adapter instance; table-wide counting is intentionally avoided."""
        return self._burned_this_process

    def _get(self, pk: str, sk: str) -> dict[str, Any] | None:
        try:
            return self._table.get_item(
                Key={"pk": pk, "sk": sk}, ConsistentRead=True
            ).get("Item")
        except Exception as exc:
            raise DurableStateError("durable state could not be read from DynamoDB") from exc
