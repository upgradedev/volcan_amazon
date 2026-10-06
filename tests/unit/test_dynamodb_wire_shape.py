"""What the durable stores put on the wire, through real boto3, offline.

The stores are built the way ``src/interfaces/composition.py`` builds them on
Lambda: a boto3 DynamoDB resource ``Table``, and the audit repository handed
that same table with no client of its own. A ``before-send`` hook records each
request body and answers ``{}``, so nothing leaves the process and no
credential is used.

The resource's client serializes Python values itself. An item that was
already turned into AttributeValues is serialized a second time, and the key
``pk`` reaches DynamoDB as a map, ``{"M": {"S": {"S": ...}}}``. DynamoDB
refuses that with a ValidationException, the store reports durable state as
unavailable, and the page's Request changes answers HTTP 503. That is what the
live build did on 2026-10-06. Every transaction the stores send is checked
here: stage, the confirm claim that burns the grant nonce, the audit append and
the audit finalization.
"""
from __future__ import annotations

import json
import time

import boto3
import pytest
from botocore.awsrequest import AWSResponse

from src.application.durable_state import ReviewSessionState, review_action_namespace
from src.domain.governed_action import ActionState, GovernedAction, Principal
from src.domain.review_dialogue import ReviewDialogue
from src.infrastructure.dynamodb_audit_repository import DynamoAuditRepository
from src.infrastructure.dynamodb_state import DynamoStateStore

TABLE = "volcan-wire-test"
SCALAR_TYPES = {"S", "N"}


class _Raw:
    def stream(self, **_kwargs):
        yield b"{}"


@pytest.fixture
def wire(monkeypatch):
    for name in ("AWS_PROFILE", "AWS_SESSION_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    session = boto3.session.Session(
        aws_access_key_id="testing", aws_secret_access_key="testing",
        region_name="eu-west-1",
    )
    table = session.resource("dynamodb").Table(TABLE)
    sent: list[tuple[str, dict]] = []

    def answer(request, **_kwargs):
        target = request.headers.get("X-Amz-Target", b"")
        target = target.decode() if isinstance(target, bytes) else target
        body = request.body.decode() if isinstance(request.body, bytes) else request.body
        sent.append((target.rsplit(".", 1)[-1], json.loads(body or "{}")))
        return AWSResponse(request.url, 200, {}, _Raw())

    table.meta.client.meta.events.register("before-send.dynamodb", answer)
    state = DynamoStateStore(TABLE, table=table)
    audit = DynamoAuditRepository(TABLE, table=state.table)
    return state, audit, sent


def _transactions(sent):
    return [body for operation, body in sent if operation == "TransactWriteItems"]


def _assert_single_level(values: dict, where: str) -> None:
    for name, value in values.items():
        assert isinstance(value, dict) and len(value) == 1, (where, name, value)
        (kind, inner), = value.items()
        assert kind in SCALAR_TYPES and isinstance(inner, str), (
            f"{where}: attribute {name!r} reached DynamoDB as {value!r}, "
            "not as one string or number"
        )


def _assert_wire_shape(body: dict) -> None:
    for item in body["TransactItems"]:
        put = item["Put"]
        _assert_single_level(put["Item"], "Item")
        _assert_single_level(put.get("ExpressionAttributeValues") or {}, "ExpressionAttributeValues")
        assert put["Item"]["pk"] == {"S": put["Item"]["pk"]["S"]}
        assert put["Item"]["sk"] == {"S": put["Item"]["sk"]["S"]}


def _action(audit_scope: str = "local") -> GovernedAction:
    return GovernedAction.create(
        action_id="review-web-rcfix-1",
        action_type="GITHUB_REQUEST_CHANGES",
        command_or_path="REQUEST_CHANGES upgradedev/volcan-demo-service#1 commit 74dd0b1",
        summary_spoken="Request changes",
        staged_by=Principal.agent("volcan-review-dialogue"),
        audit_scope=audit_scope,
    )


def test_staging_a_review_sends_each_attribute_once_serialized(wire):
    state, _audit, sent = wire
    namespace = review_action_namespace("companion-developer", "upgradedev/volcan-demo-service", "web-x")
    saved = ReviewSessionState(
        ReviewDialogue("web-x"), "companion-developer",
        pending_action_id="review-web-rcfix-1", pending_grant="v1.grant", staged_count=1,
    )

    state.save_review_with_action(saved, 2, namespace, _action())

    (body,) = _transactions(sent)
    _assert_wire_shape(body)
    session_put = body["TransactItems"][0]["Put"]
    assert session_put["Item"]["revision"] == {"N": "3"}
    assert session_put["ExpressionAttributeValues"][":expected"] == {"N": "2"}


def test_confirming_claims_the_action_and_burns_the_nonce_once_serialized(wire):
    state, _audit, sent = wire
    action = _action()
    action.mark_approved("v1.grant", Principal.human("companion-developer"))

    state.claim_action_with_nonce(
        "review-ns", action, ActionState.PENDING_APPROVAL, "nonce-1", time.time() + 300,
    )

    (body,) = _transactions(sent)
    _assert_wire_shape(body)
    nonce_item = body["TransactItems"][1]["Put"]["Item"]
    assert nonce_item["sk"] == {"S": "spent"}


def test_audit_append_and_finalize_send_each_attribute_once_serialized(wire):
    _state, audit, sent = wire
    action = _action()
    audit.append_audit_record(action.create_audit_record(stdout="REFUSED TEST"))
    action.mark_approved("v1.grant", Principal.human("companion-developer"))
    action.state = ActionState.APPROVED
    audit.finalize_action(
        "review-ns", action, ActionState.APPROVED,
        action.create_audit_record(stdout="DRY RUN recorded, not sent"),
    )

    transactions = _transactions(sent)
    assert len(transactions) == 2
    for body in transactions:
        _assert_wire_shape(body)
    assert len(transactions[1]["TransactItems"]) == 4
