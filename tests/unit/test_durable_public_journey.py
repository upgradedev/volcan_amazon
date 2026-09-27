"""Durable mode keeps the anonymous judge journey working, and redacted.

With ``VOLCAN_STATE_TABLE`` set, the companion page is still opened by someone
with no reviewer credential. These tests drive the routes the page calls
(stage, confirm, audit log) plus the voice turn and the MCP tools, against the
in-memory DynamoDB fake, and check three things: the anonymous journey
answers, its audit trail lists the actions it just released, and nothing a
caller typed (or any grant) is repeated to the next visitor.
"""
import asyncio
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from src.application.durable_state import review_audit_scope
from src.application.governed_execution_use_case import GovernedExecutionUseCase
from src.application.public_audit import (
    ANONYMOUS_VOICE_OWNER,
    PUBLIC_AUDIT_LIMIT,
    PUBLIC_DEMO_AUDIT_SCOPE,
    WITHHELD,
    public_record_view,
)
from src.application.review_authorization import current_review_principal
from src.application.sonify_event_use_case import SonifyEventUseCase
from src.application.voice_turn_use_case import VoiceTurnUseCase
from src.domain.approval_grant import ApprovalGrantIssuer
from src.domain.governed_action import ActionState, AuditLogRecord, GovernedAction, Principal
from src.infrastructure.dry_run_executor import DryRunExecutor
from src.infrastructure.dynamodb_audit_repository import DynamoAuditRepository
from src.infrastructure.dynamodb_state import DynamoStateStore
from src.interfaces.mcp_protocol import PROTOCOL_VERSION
from src.interfaces.review_authorization import authenticated_reviewer
from tests.fixtures.fake_dynamodb import FakeTable

SECRET = b"durable-public-journey-secret-000001"
TABLE = "volcan-test-state"
PAGE_COMMAND = "git diff HEAD"


class Durable:
    """One fake table, and the use cases a durable composition root builds on it."""

    def __init__(self) -> None:
        self.table = FakeTable()
        self.state = DynamoStateStore(TABLE, table=self.table)
        self.audit = DynamoAuditRepository(TABLE, table=self.table, client=self.table.meta.client)
        self.governed = GovernedExecutionUseCase(
            DryRunExecutor(), self.audit,
            ApprovalGrantIssuer(SECRET, replay_store=self.state), state_store=self.state,
        )


@pytest.fixture
def durable(monkeypatch):
    from src.interfaces import composition, operations, rest_api

    world = Durable()
    voice = VoiceTurnUseCase(
        composition.digest_use_case, world.governed, SonifyEventUseCase(),
        state_store=world.state,
    )
    monkeypatch.setattr(operations, "audit_repo", world.audit)
    monkeypatch.setattr(operations, "governed_use_case", world.governed)
    monkeypatch.setattr(rest_api, "voice_turn_use_case", voice)
    monkeypatch.delenv("VOLCAN_REVIEWERS", raising=False)
    return world


def _client():
    from src.interfaces.mcp_server import app

    return TestClient(app)


def _stage_and_confirm(client, action_id, command, *, action_type="TERMINAL_COMMAND",
                       staged_by="volcan-agent", approver_id="companion-operator"):
    staged = client.post("/api/stage_governed_action", json={
        "action_id": action_id, "action_type": action_type, "command": command,
        "summary_spoken": "Inspect the working tree diff before release",
        "lease_sec": 300, "staged_by": staged_by,
    })
    assert staged.status_code == 200, staged.text
    grant = staged.json()["approval_grant"]
    confirmed = client.post("/api/confirm_action", json={
        "action_id": action_id, "approval_grant": grant, "approver_id": approver_id,
    })
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["approved"] is True, confirmed.json()
    return grant


def test_the_page_journey_works_anonymously_and_its_audit_trail_lists_it(durable):
    client = _client()
    grant = _stage_and_confirm(client, "act_12345", PAGE_COMMAND)

    audit = client.get("/api/audit_log")
    assert audit.status_code == 200, audit.text
    body = audit.json()
    assert body["view"] == "public"
    assert body["public_chain_records"] == 1
    assert "not listed here" in body["note"]
    [record] = body["records"]
    assert record["action"] == "act_12345"
    assert record["command"] == PAGE_COMMAND
    assert record["state"] == "RELEASED_NOT_RUN"
    assert record["approved_by"] == "companion-operator"
    assert record["outcome"].startswith("Dry run only, nothing was executed.")
    assert grant not in audit.text
    assert "approver_token_hash" not in audit.text


def test_caller_written_text_from_rest_and_mcp_is_withheld_from_the_public_view(durable):
    client = _client()
    _stage_and_confirm(client, "act_20001", PAGE_COMMAND)
    grants = [_stage_and_confirm(
        client, "rest-canary-7f3a", "pytest rest-canary-7f3a",
        action_type="REST-CANARY-TYPE-7f3a", staged_by="rest-canary-stager-7f3a",
        approver_id="rest-canary-approver-7f3a",
    )]

    initialized = client.post("/mcp", json={
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                   "clientInfo": {"name": "test", "version": "1"}},
    })
    headers = {"MCP-Protocol-Version": PROTOCOL_VERSION}
    if initialized.headers.get("mcp-session-id"):
        headers["Mcp-Session-Id"] = initialized.headers["mcp-session-id"]

    def call(name, arguments):
        answer = client.post("/mcp", headers=headers, json={
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }).json()
        assert "error" not in answer, answer
        return json.loads(answer["result"]["content"][-1]["text"])

    staged = call("stage_governed_action", {
        "action_id": "mcp-canary-9b2c", "action_type": "MCP-CANARY-TYPE-9b2c",
        "command": "ruff check mcp-canary-9b2c", "summary_spoken": "mcp-canary-9b2c",
        "staged_by": "mcp-canary-stager-9b2c",
    })
    grants.append(staged["approval_grant"])
    released = call("confirm_governed_action", {
        "action_id": "mcp-canary-9b2c", "approval_grant": staged["approval_grant"],
        "approver_id": "mcp-canary-approver-9b2c",
    })
    assert released["approved"] is True

    audit = client.get("/api/audit_log")
    body = audit.json()
    assert body["public_chain_records"] == 3
    for canary in ("7f3a", "9b2c", "CANARY", "canary"):
        assert canary not in audit.text, canary
    for grant in grants:
        assert grant not in audit.text
    page_row, *withheld = body["records"]
    assert page_row["command"] == PAGE_COMMAND
    for row in withheld:
        assert row["command"] == WITHHELD
        assert row["action"] == WITHHELD
        assert row["action_type"] == WITHHELD
        assert row["staged_by"] == WITHHELD
        assert row["approved_by"] == WITHHELD
        assert row["outcome"] == "Dry run only, nothing was executed. The rest is withheld."
        assert row["id"].startswith("public-")
        assert len(row["payload_hash"]) == 64


def test_the_public_read_is_one_bounded_query_of_the_newest_records(durable):
    world = durable
    total = PUBLIC_AUDIT_LIMIT + 10
    for index in range(total):
        action = GovernedAction.create(
            f"act_{index}", "TERMINAL_COMMAND", PAGE_COMMAND, "diff",
            audit_scope=PUBLIC_DEMO_AUDIT_SCOPE,
        )
        world.audit.append_audit_record(action.create_audit_record(stdout="Action rejected by operator."))
    world.table.queries = 0

    body = _client().get("/api/audit_log").json()
    assert world.table.queries == 1
    assert body["public_chain_records"] == total
    assert body["total_records"] == PUBLIC_AUDIT_LIMIT
    assert [row["sequence"] for row in body["records"]] == list(range(10, total))


def test_a_reviewer_sees_the_public_chain_and_their_own_records_in_time_order(durable, monkeypatch):
    world = durable
    client = _client()
    _stage_and_confirm(client, "act_30001", PAGE_COMMAND)
    own = GovernedAction.create(
        "review-own", "GITHUB_REQUEST_CHANGES", "REQUEST_CHANGES octo/demo#1", "review",
        audit_scope=review_audit_scope("alice", "octo/demo"),
    )
    world.audit.append_audit_record(own.create_audit_record(stdout="DRY RUN recorded, not sent"))
    _stage_and_confirm(client, "act_30002", PAGE_COMMAND)
    monkeypatch.setenv("VOLCAN_REVIEWERS", json.dumps({
        "alice": {"token": "a" * 40, "repositories": ["octo/demo"]},
    }))

    body = client.get("/api/audit_log", headers={"Authorization": f"Bearer {'a' * 40}"}).json()
    assert body["view"] == "public_and_reviewer"
    assert [row["action"] for row in body["records"]] == ["act_30001", "review-own", "act_30002"]
    assert [row["chain"] for row in body["records"]] == ["public", "reviewer", "public"]
    assert body["records"][1]["command"] == "REQUEST_CHANGES octo/demo#1"

    anonymous = client.get("/api/audit_log").json()
    assert [row["action"] for row in anonymous["records"]] == ["act_30001", "act_30002"]


def test_parallel_public_releases_all_finalize_into_one_intact_chain():
    for _round in range(3):
        world = Durable()
        world.table.read_delay_sec = 0.002
        tickets = [
            world.governed.stage_action(f"act_{index}", "TERMINAL_COMMAND", PAGE_COMMAND, "diff")
            for index in range(32)
        ]

        def release(ticket):
            return asyncio.run(world.governed.confirm_and_execute(
                ticket.action.action_id, ticket.grant, Principal.human("companion-operator"),
            ))

        with ThreadPoolExecutor(max_workers=32) as pool:
            outcomes = list(pool.map(release, tickets))
        assert all(outcome.approved for outcome in outcomes)
        assert world.audit.record_count(PUBLIC_DEMO_AUDIT_SCOPE) == 32
        assert world.audit.verify_integrity(PUBLIC_DEMO_AUDIT_SCOPE).intact
        for ticket in tickets:
            action = world.state.get_action("governed", ticket.action.action_id)
            assert action.state is ActionState.RELEASED_NOT_RUN


def test_an_anonymous_voice_turn_answers_in_durable_mode(durable):
    client = _client()
    turn = {"session_id": "voice-anon", "user_id": "judge", "repository": "octo/demo"}
    staged = client.post("/api/voice_turn", json={**turn, "intent": "stage_action", "params": {
        "action_id": "act_40001", "command": PAGE_COMMAND, "summary_spoken": "diff",
    }})
    assert staged.status_code == 200, staged.text
    approved = client.post("/api/voice_turn", json={**turn, "intent": "approve_action", "params": {
        "approval_grant": staged.json()["approval_grant"],
    }})
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "RELEASED_NOT_RUN"
    assert durable.state.load_voice("voice-anon", ANONYMOUS_VOICE_OWNER, "octo/demo") is not None
    # A voice session's record stays in its private chain.
    assert client.get("/api/audit_log").json()["records"] == []


def test_a_durable_voice_turn_with_a_reviewer_credential_is_still_bound_to_the_reviewer(
    durable, monkeypatch,
):
    monkeypatch.setenv("VOLCAN_REVIEWERS", json.dumps({
        "alice": {"token": "a" * 40, "repositories": ["octo/demo"]},
    }))
    client = _client()
    refused = client.post(
        "/api/voice_turn",
        headers={"Authorization": f"Bearer {'a' * 40}"},
        json={"session_id": "s", "user_id": "alice", "repository": "other/private",
              "intent": "summarize_diff", "params": {}},
    )
    assert refused.status_code == 403


@pytest.mark.parametrize("identity", [ANONYMOUS_VOICE_OWNER, "team:alice"])
def test_the_roster_refuses_an_identity_that_could_equal_the_anonymous_owner(monkeypatch, identity):
    monkeypatch.setenv("VOLCAN_REVIEWERS", json.dumps({
        identity: {"token": "z" * 40, "repositories": ["octo/demo"]},
    }))
    assert authenticated_reviewer(f"Bearer {'z' * 40}") is None


def test_the_public_view_keeps_product_refusal_codes_and_drops_everything_else():
    def record(command, stdout):
        return AuditLogRecord(
            record_id="AUDIT-x y", action_id="x y", action_type="TERMINAL_COMMAND",
            command=command, payload_hash="0" * 64, approver_token_hash="1" * 64,
            state=ActionState.FAILED, execution_stdout=stdout, timestamp="t",
            staged_by="volcan-agent", approved_by="unapproved",
            audit_scope=PUBLIC_DEMO_AUDIT_SCOPE, sequence=4,
        )

    assert public_record_view(record("rm -rf x", "REFUSED LEASE_EXPIRED"))["outcome"] == (
        "REFUSED LEASE_EXPIRED"
    )
    assert public_record_view(record("rm -rf x", "FAILED: rm -rf x"))["outcome"] == WITHHELD
    assert public_record_view(record("rm -rf x", "Refused, and nothing was executed. rm"))[
        "outcome"] == "Refused, and nothing was executed. The rest is withheld."
    view = public_record_view(record(PAGE_COMMAND, "Dry run only, nothing was executed. x"))
    assert view["command"] == PAGE_COMMAND
    assert view["id"] == "public-4"
    assert "1" * 64 not in json.dumps(view)


def test_process_memory_mode_is_unchanged():
    from src.interfaces import operations

    assert not getattr(operations.audit_repo, "is_durable", False)
    body = _client().get("/api/audit_log").json()
    assert body["view"] == "process_memory"
    assert "note" not in body


def test_the_principal_context_does_not_leak_between_requests(durable, monkeypatch):
    monkeypatch.setenv("VOLCAN_REVIEWERS", json.dumps({
        "alice": {"token": "a" * 40, "repositories": ["octo/demo"]},
    }))
    client = _client()
    client.get("/api/audit_log", headers={"Authorization": f"Bearer {'a' * 40}"})
    assert current_review_principal.get() is None
    assert client.get("/api/audit_log").json()["view"] == "public"
