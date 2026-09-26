"""Cold-start, concurrency and fail-closed proof for Volcan durable state."""
from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi.testclient import TestClient

from src.application.digest_diff_use_case import DigestDiffUseCase
from src.application.durable_state import (
    DurableStateError,
    ReviewSessionState,
    StateConflict,
    private_review_audit_scope,
    review_action_namespace,
    review_audit_scope,
    voice_action_namespace,
)
from src.application.governed_execution_use_case import GovernedExecutionUseCase
from src.application.public_audit import ANONYMOUS_VOICE_OWNER, PUBLIC_DEMO_AUDIT_SCOPE
from src.application.review_authorization import (
    ReviewAuthorizationError,
    ReviewPrincipal,
    current_review_principal,
)
from src.application.review_dialogue_use_case import ReviewDialogueUseCase
from src.application.sonify_event_use_case import SonifyEventUseCase
from src.application.voice_turn_use_case import VoiceTurnUseCase
from src.domain.approval_grant import ApprovalGrantIssuer
from src.domain.governed_action import ActionState, AuditLogRecord, Principal
from src.domain.review_dialogue import ReviewDialogue
from src.infrastructure.bedrock_adapter import BedrockSynthesisAdapter
from src.infrastructure.dynamodb_audit_repository import DynamoAuditRepository
from src.infrastructure.dynamodb_state import DynamoStateStore
from src.infrastructure.github_review_adapter import GitHubReviewAdapter
from src.infrastructure.secret_provider import SecretConfigurationError, load_approval_secret
from tests.fixtures.fake_dynamodb import FakeTable
from tests.fixtures.fake_github import PR_URL, FakeGitHub

SECRET = b"durable-volcan-test-secret-00000001"


class RecordingExecutor:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def run_command(self, command: str) -> str:
        self.calls.append(command)
        return f"PLANNED: {command}"


def state(table: FakeTable) -> DynamoStateStore:
    return DynamoStateStore("volcan-test-state", table=table)


def audit(table: FakeTable) -> DynamoAuditRepository:
    return DynamoAuditRepository(
        "volcan-test-state", table=table, client=table.meta.client,
    )


def review_use_case(table: FakeTable, fake: FakeGitHub) -> ReviewDialogueUseCase:
    durable = state(table)
    bedrock = BedrockSynthesisAdapter(client_factory=lambda _region: None)
    bedrock.credentials_present = lambda: False  # type: ignore[method-assign]
    return ReviewDialogueUseCase(
        DigestDiffUseCase(bedrock),
        GitHubReviewAdapter(write_enabled=False, transport=httpx.MockTransport(fake)),
        ApprovalGrantIssuer(SECRET, replay_store=durable),
        audit(table),
        SonifyEventUseCase(),
        state_store=durable,
    )


def voice_use_case(table: FakeTable, executor: RecordingExecutor) -> VoiceTurnUseCase:
    durable = state(table)
    bedrock = BedrockSynthesisAdapter(client_factory=lambda _region: None)
    bedrock.credentials_present = lambda: False  # type: ignore[method-assign]
    governed = GovernedExecutionUseCase(
        executor,
        audit(table),
        ApprovalGrantIssuer(SECRET, replay_store=durable),
        state_store=durable,
    )
    return VoiceTurnUseCase(
        DigestDiffUseCase(bedrock), governed, SonifyEventUseCase(), state_store=durable,
    )


def voice_say(
    use_case: VoiceTurnUseCase,
    session_id: str,
    identity: str,
    repo: str,
    intent: str,
    params: dict,
    *,
    claimed_user_id: str | None = None,
    repositories: frozenset[str] | None = None,
):
    principal = ReviewPrincipal(
        identity,
        repositories or frozenset({repo.lower()}),
    )
    token = current_review_principal.set(principal)
    try:
        return asyncio.run(use_case.handle_turn(
            session_id,
            claimed_user_id or identity,
            repo,
            intent,
            params,
        ))
    finally:
        current_review_principal.reset(token)


def say(use_case: ReviewDialogueUseCase, transcript: str, **kwargs):
    return asyncio.run(use_case.handle_turn(
        session_id="durable-review", user_id="blind-developer",
        transcript=transcript, **kwargs,
    ))


def test_review_dialogue_pending_action_nonce_and_audit_survive_cold_starts():
    table = FakeTable()
    fake = FakeGitHub()
    first_worker = review_use_case(table, fake)
    say(first_worker, "open the pull request", pr_url=PR_URL)
    staged = say(first_worker, "request changes: restore the equality check")

    second_worker = review_use_case(table, fake)
    confirmed = say(second_worker, "confirm", approval_grant=staged["approval_grant"])
    assert confirmed["state"] == "RECORDED"
    assert confirmed["review_outcome"]["dry_run"] is True

    third_worker = review_use_case(table, fake)
    repeated = say(third_worker, "confirm", approval_grant=staged["approval_grant"])
    assert repeated["error"] is True
    assert repeated["review_outcome"] is None

    durable_audit = audit(table)
    scope = private_review_audit_scope(
        "blind-developer", "octo/demo", "durable-review"
    )
    records = durable_audit.list_records([scope])
    assert len(records) == 1
    assert records[0].action_id == staged["pending_review"]["action_id"]
    assert durable_audit.verify_integrity(scope).intact is True


def test_grant_nonce_has_exactly_one_winner_across_workers():
    table = FakeTable()
    first = state(table)
    issuer = ApprovalGrantIssuer(SECRET, replay_store=first)
    grant = issuer.issue("act", "payload", 4_000_000_000)

    def verify(_index):
        worker = ApprovalGrantIssuer(SECRET, replay_store=state(table))
        return worker.verify(grant, "act", "payload", now_epoch=1_000_000_000)

    with ThreadPoolExecutor(max_workers=12) as pool:
        verdicts = list(pool.map(verify, range(24)))
    assert sum(verdict.accepted for verdict in verdicts) == 1
    assert sum(
        bool(verdict.refusal and verdict.refusal.value == "REPLAYED") for verdict in verdicts
    ) == 23


def test_governed_action_can_be_confirmed_after_cold_start_but_never_twice():
    table = FakeTable()
    staging_executor = RecordingExecutor()
    first_store = state(table)
    first = GovernedExecutionUseCase(
        staging_executor,
        audit(table),
        ApprovalGrantIssuer(SECRET, replay_store=first_store),
        state_store=first_store,
    )
    ticket = first.stage_action("cold-action", "RUN", "pytest tests/unit", "Run tests")

    execution = RecordingExecutor()
    second_store = state(table)
    second = GovernedExecutionUseCase(
        execution,
        audit(table),
        ApprovalGrantIssuer(SECRET, replay_store=second_store),
        state_store=second_store,
    )
    outcome = asyncio.run(second.confirm_and_execute(
        "cold-action", ticket.grant, Principal.human("reviewer"),
    ))
    assert outcome.approved is True
    assert execution.calls == ["pytest tests/unit"]

    replay_executor = RecordingExecutor()
    third_store = state(table)
    third = GovernedExecutionUseCase(
        replay_executor,
        audit(table),
        ApprovalGrantIssuer(SECRET, replay_store=third_store),
        state_store=third_store,
    )
    replay = asyncio.run(third.confirm_and_execute(
        "cold-action", ticket.grant, Principal.human("reviewer"),
    ))
    assert replay.refusal_code == "NOT_PENDING"
    assert replay_executor.calls == []
    assert third.get_action("cold-action").state is ActionState.EXECUTED


def test_voice_session_action_and_owner_binding_survive_cold_start():
    table = FakeTable()
    first = voice_use_case(table, RecordingExecutor())
    staged = voice_say(
        first,
        "voice-session", "developer", "octo/demo", "stage_action",
        {
            "action_id": "voice-action", "action_type": "RUN",
            "command": "pytest tests/unit", "summary_spoken": "Run tests",
        },
    )

    execution = RecordingExecutor()
    fresh = voice_use_case(table, execution)
    result = voice_say(
        fresh,
        "voice-session", "developer", "octo/demo", "approve_action",
        {"approval_grant": staged["approval_grant"], "approver_id": "reviewer"},
    )
    assert result["status"] == "PLANNED"
    assert execution.calls == ["pytest tests/unit"]

    wrong_owner = voice_use_case(table, RecordingExecutor())
    isolated = voice_say(
        wrong_owner,
        "voice-session", "intruder", "octo/demo", "summarize_diff", {"raw_diff": ""},
    )
    assert isolated["total_files"] == 0
    original = state(table).load_voice(
        "voice-session", "developer", "octo/demo"
    ).value.session
    assert original.user_id == "developer"
    assert original.staged_action_id is None


def test_durable_voice_uses_server_principal_not_caller_user_id():
    table = FakeTable()
    use_case = voice_use_case(table, RecordingExecutor())
    params = {
        "action_id": "principal-bound",
        "action_type": "RUN",
        "command": "pytest",
        "summary_spoken": "Run tests",
    }

    # Without a credential the turn runs, but as the fixed anonymous owner:
    # the JSON user_id owns nothing, and the session it opens is not alice's.
    anonymous = asyncio.run(use_case.handle_turn(
        "principal-session",
        "alice",
        "octo/demo",
        "stage_action",
        params,
    ))
    assert anonymous["approval_grant"].startswith("v1.")
    assert state(table).load_voice(
        "principal-session", ANONYMOUS_VOICE_OWNER, "octo/demo"
    ) is not None
    assert state(table).load_voice("principal-session", "alice", "octo/demo") is None

    staged = voice_say(
        use_case,
        "principal-session",
        "alice",
        "octo/demo",
        "stage_action",
        params,
        claimed_user_id="mallory",
    )
    assert staged["approval_grant"].startswith("v1.")
    assert state(table).load_voice(
        "principal-session", "alice", "octo/demo"
    ) is not None
    assert state(table).load_voice(
        "principal-session", "mallory", "octo/demo"
    ) is None

    with pytest.raises(ReviewAuthorizationError, match="may not access"):
        voice_say(
            use_case,
            "principal-session",
            "bob",
            "octo/demo",
            "reject_action",
            {"action_id": "principal-bound"},
            repositories=frozenset({"other/private"}),
        )

    # The anonymous caller rejects "principal-bound" in the same session id and
    # reaches only its own staged action, never alice's.
    rejected = asyncio.run(use_case.handle_turn(
        "principal-session", "alice", "octo/demo", "reject_action",
        {"action_id": "principal-bound"},
    ))
    assert rejected["status"] == "REJECTED"
    assert state(table).get_action(
        voice_action_namespace(ANONYMOUS_VOICE_OWNER, "octo/demo", "principal-session"),
        "principal-bound",
    ).state is ActionState.REJECTED

    victim = state(table).get_action(
        voice_action_namespace("alice", "octo/demo", "principal-session"),
        "principal-bound",
    )
    assert victim.state is ActionState.PENDING_APPROVAL


def test_stale_session_revision_is_refused_instead_of_overwriting_newer_state():
    table = FakeTable()
    durable = state(table)
    original = ReviewSessionState(ReviewDialogue("session"), "owner")
    assert durable.save_review(original, expected_revision=0) == 1
    left = durable.load_review("session", "owner")
    right = durable.load_review("session", "owner")
    left.value.dialogue.history.append({"role": "developer", "text": "left"})
    right.value.dialogue.history.append({"role": "developer", "text": "right"})
    durable.save_review(left.value, expected_revision=left.revision)
    with pytest.raises(StateConflict):
        durable.save_review(right.value, expected_revision=right.revision)
    restored = durable.load_review("session", "owner").value.dialogue
    assert restored.history[-1]["text"] == "left"


def test_same_session_id_is_isolated_by_owner_and_repository_without_raw_keys():
    table = FakeTable()
    durable = state(table)
    assert durable.save_review(
        ReviewSessionState(ReviewDialogue("shared"), "alice"), 0
    ) == 1
    assert durable.save_review(
        ReviewSessionState(ReviewDialogue("shared"), "bob"), 0
    ) == 1
    assert durable.load_review("shared", "alice").value.owner == "alice"
    assert durable.load_review("shared", "bob").value.owner == "bob"
    assert durable.load_review("shared", "mallory") is None
    for pk, _sk in table.items:
        assert "shared" not in pk
        assert "alice" not in pk
        assert "bob" not in pk


def test_review_action_ids_are_isolated_by_owner_repository_and_session():
    table = FakeTable()
    fake = FakeGitHub()
    use_case = review_use_case(table, fake)

    def review_turn(owner: str, transcript: str, **kwargs):
        return asyncio.run(use_case.handle_turn(
            session_id="shared-review",
            user_id=owner,
            transcript=transcript,
            **kwargs,
        ))

    review_turn("alice", "open the pull request", pr_url=PR_URL)
    alice = review_turn("alice", "request changes: restore the equality check")
    review_turn("bob", "open the pull request", pr_url=PR_URL)
    bob = review_turn("bob", "request changes: restore the equality check")

    assert alice["pending_review"]["action_id"] == bob["pending_review"]["action_id"]
    durable = state(table)
    for owner in ("alice", "bob"):
        namespace = review_action_namespace(owner, "octo/demo", "shared-review")
        assert durable.get_action(
            namespace, alice["pending_review"]["action_id"]
        ) is not None


def _record(index: int) -> AuditLogRecord:
    return AuditLogRecord(
        record_id=f"AUDIT-{index}", action_id=f"act-{index}", action_type="RUN",
        command="pytest", payload_hash=f"hash-{index}", approver_token_hash="token",
        state=ActionState.EXECUTED, execution_stdout="PLANNED", timestamp=str(index),
    )


def test_parallel_audit_appends_form_one_intact_chain():
    table = FakeTable()

    def append(index):
        return audit(table).append_audit_record(_record(index))

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(append, range(32)))
    repository = audit(table)
    records = repository.list_records(["local"])
    assert [record.sequence for record in records] == list(range(32))
    assert repository.verify_integrity("local").intact is True
    assert repository.head_hash("local") == records[-1].entry_hash


def test_storage_outage_raises_and_never_falls_back_to_memory():
    class BrokenTable(FakeTable):
        def put_item(self, *args, **kwargs):
            raise RuntimeError("network unavailable")

    durable = state(BrokenTable())
    with pytest.raises(DurableStateError, match="could not be committed"):
        durable.save_review(
            ReviewSessionState(ReviewDialogue("session"), "owner"), expected_revision=0,
        )


def test_review_stage_transaction_failure_leaves_no_orphan_and_retry_succeeds():
    table = FakeTable()
    fake = FakeGitHub()
    first = review_use_case(table, fake)
    say(first, "open the pull request", pr_url=PR_URL)
    table.fail_stage_once = True

    with pytest.raises(DurableStateError, match="committed atomically"):
        say(first, "request changes: restore the equality check")

    durable = state(table)
    namespace = review_action_namespace(
        "blind-developer", "octo/demo", "durable-review"
    )
    assert durable.get_action(namespace, "review-durable-review-1") is None
    stored = durable.load_review("durable-review", "blind-developer")
    assert stored.value.pending_action_id is None
    assert stored.value.dialogue.pending_body is None

    retried = say(
        review_use_case(table, fake),
        "request changes: restore the equality check",
    )
    assert retried["approval_grant"].startswith("v1.")
    assert durable.get_action(namespace, "review-durable-review-1") is not None


def test_lost_review_stage_response_replays_exact_persisted_grant_after_cold_start():
    table = FakeTable()
    fake = FakeGitHub()
    first = review_use_case(table, fake)
    say(first, "open the pull request", pr_url=PR_URL)
    table.commit_then_fail_stage_once = True

    with pytest.raises(DurableStateError, match="committed atomically"):
        say(first, "request changes: restore the equality check")

    stored = state(table).load_review("durable-review", "blind-developer").value
    persisted_grant = stored.pending_grant
    retried = say(
        review_use_case(table, fake),
        "request changes: restore the equality check",
    )
    assert retried["approval_grant"] == persisted_grant
    actions = [item for item in table.items.values() if item.get("kind") == "governed_action"]
    assert len(actions) == 1


def test_lost_voice_stage_response_replays_exact_grant_without_duplicate_action():
    table = FakeTable()
    params = {
        "action_id": "voice-retry",
        "action_type": "RUN",
        "command": "pytest tests/unit",
        "summary_spoken": "Run tests",
    }
    table.commit_then_fail_stage_once = True
    with pytest.raises(DurableStateError, match="committed atomically"):
        voice_say(
            voice_use_case(table, RecordingExecutor()),
            "voice-retry-session", "developer", "octo/demo", "stage_action", params,
        )

    stored = state(table).load_voice(
        "voice-retry-session", "developer", "octo/demo"
    ).value.session
    retried = voice_say(
        voice_use_case(table, RecordingExecutor()),
        "voice-retry-session", "developer", "octo/demo", "stage_action", params,
    )
    assert retried["approval_grant"] == stored.staged_action_grant
    actions = [item for item in table.items.values() if item.get("kind") == "governed_action"]
    assert len(actions) == 1


def test_voice_namespaces_prevent_default_id_collision_between_sessions():
    table = FakeTable()
    params = {
        "action_id": "act-default",
        "action_type": "RUN",
        "command": "pytest tests/unit",
        "summary_spoken": "Run tests",
    }
    first = voice_say(
        voice_use_case(table, RecordingExecutor()),
        "voice-a", "developer", "octo/demo", "stage_action", params,
    )
    second = voice_say(
        voice_use_case(table, RecordingExecutor()),
        "voice-b", "developer", "octo/demo", "stage_action", params,
    )
    assert first["payload_hash"] != second["payload_hash"]
    durable = state(table)
    assert durable.get_action(
        voice_action_namespace("developer", "octo/demo", "voice-a"), "act-default"
    ) is not None
    assert durable.get_action(
        voice_action_namespace("developer", "octo/demo", "voice-b"), "act-default"
    ) is not None


def test_voice_session_cannot_approve_or_reject_another_sessions_action():
    table = FakeTable()
    victim = voice_say(
        voice_use_case(table, RecordingExecutor()),
        "victim", "developer", "octo/demo", "stage_action",
        {"action_id": "victim-action", "action_type": "RUN", "command": "pytest",
         "summary_spoken": "Run victim tests"},
    )
    attacker_executor = RecordingExecutor()
    attacker = voice_use_case(table, attacker_executor)
    voice_say(
        attacker,
        "attacker", "developer", "octo/demo", "stage_action",
        {"action_id": "attacker-action", "action_type": "RUN", "command": "whoami",
         "summary_spoken": "Run attacker command"},
    )

    refused = voice_say(
        attacker,
        "attacker", "developer", "octo/demo", "approve_action",
        {"action_id": "victim-action", "approval_grant": victim["approval_grant"]},
    )
    rejected = voice_say(
        attacker,
        "attacker", "developer", "octo/demo", "reject_action",
        {"action_id": "victim-action"},
    )
    assert refused["refusal_code"] == "SESSION_ACTION_MISMATCH"
    assert rejected["refusal_code"] == "SESSION_ACTION_MISMATCH"
    assert attacker_executor.calls == []
    victim_action = state(table).get_action(
        voice_action_namespace("developer", "octo/demo", "victim"), "victim-action"
    )
    assert victim_action.state is ActionState.PENDING_APPROVAL


def test_finalize_failure_never_persists_terminal_action_without_audit():
    table = FakeTable()
    executor = RecordingExecutor()
    durable = state(table)
    use_case = GovernedExecutionUseCase(
        executor,
        audit(table),
        ApprovalGrantIssuer(SECRET, replay_store=durable),
        state_store=durable,
    )
    ticket = use_case.stage_action("finalize-gap", "RUN", "pytest", "Run tests")
    table.fail_finalize_once = True

    with pytest.raises(DurableStateError, match="finalized atomically"):
        asyncio.run(use_case.confirm_and_execute(
            ticket.action.action_id, ticket.grant, Principal.human("reviewer"),
        ))

    persisted = state(table).get_action("governed", "finalize-gap")
    assert persisted.state is ActionState.APPROVED
    assert audit(table).list_records([PUBLIC_DEMO_AUDIT_SCOPE]) == []
    replay = asyncio.run(use_case.confirm_and_execute(
        ticket.action.action_id, ticket.grant, Principal.human("reviewer"),
    ))
    assert replay.refusal_code == "NOT_PENDING"
    assert executor.calls == ["pytest"]


def test_lost_finalize_response_is_recognized_idempotently():
    table = FakeTable()
    executor = RecordingExecutor()
    durable = state(table)
    use_case = GovernedExecutionUseCase(
        executor,
        audit(table),
        ApprovalGrantIssuer(SECRET, replay_store=durable),
        state_store=durable,
    )
    ticket = use_case.stage_action("finalize-response", "RUN", "pytest", "Run tests")
    table.commit_then_fail_finalize_once = True
    result = asyncio.run(use_case.confirm_and_execute(
        ticket.action.action_id, ticket.grant, Principal.human("reviewer"),
    ))
    assert result.approved is True
    assert executor.calls == ["pytest"]
    assert state(table).get_action("governed", "finalize-response").state is ActionState.EXECUTED
    records = audit(table).list_records([PUBLIC_DEMO_AUDIT_SCOPE])
    assert len(records) == 1


def test_health_distinguishes_configured_reachable_from_unreachable():
    reachable = state(FakeTable()).capability()
    assert reachable["configured"] is True
    assert reachable["reachable"] is True
    assert reachable["resolved_capability"] == "configured_reachable"
    assert "table" not in reachable
    assert "volcan-test-state" not in str(reachable)
    assert "arn:aws" not in str(reachable)

    class BrokenReadTable(FakeTable):
        def get_item(self, *args, **kwargs):
            raise RuntimeError("account and request id must not leak")

    unreachable = state(BrokenReadTable()).capability()
    assert unreachable["configured"] is True
    assert unreachable["reachable"] is False
    assert unreachable["resolved_capability"] == "configured_unreachable"
    assert "account" not in str(unreachable)


def test_durable_secret_comes_from_arn_and_never_uses_direct_environment(monkeypatch):
    class Secrets:
        def __init__(self):
            self.requested = None

        def get_secret_value(self, SecretId):
            self.requested = SecretId
            return {"SecretString": "s" * 32}

    client = Secrets()
    arn = "arn:aws:secretsmanager:eu-west-1:123456789012:secret:volcan"
    monkeypatch.setenv("VOLCAN_APPROVAL_SECRET_ARN", arn)
    monkeypatch.delenv("VOLCAN_APPROVAL_SECRET", raising=False)
    secret = load_approval_secret(durable=True, client=client)
    assert client.requested == arn
    assert secret.source == "secrets_manager"
    assert secret.value == b"s" * 32

    monkeypatch.setenv("VOLCAN_APPROVAL_SECRET", "x" * 64)
    with pytest.raises(SecretConfigurationError, match="forbidden"):
        load_approval_secret(durable=True, client=client)


def test_secret_failures_are_bounded_and_never_echo_secret(monkeypatch):
    leaked = "do-not-echo-this-secret-value-123456789"

    class BrokenSecrets:
        def get_secret_value(self, SecretId):
            raise RuntimeError(f"provider leaked {leaked} for {SecretId}")

    monkeypatch.setenv(
        "VOLCAN_APPROVAL_SECRET_ARN",
        "arn:aws:secretsmanager:eu-west-1:123456789012:secret:volcan",
    )
    monkeypatch.delenv("VOLCAN_APPROVAL_SECRET", raising=False)
    with pytest.raises(SecretConfigurationError) as caught:
        load_approval_secret(durable=True, client=BrokenSecrets())
    assert leaked not in str(caught.value)


def test_durable_audit_route_is_public_for_anyone_and_repository_scoped_for_reviewers(monkeypatch):
    from src.interfaces import operations
    from src.interfaces.mcp_server import app

    table = FakeTable()
    repository = audit(table)
    alice = _record(101)
    alice = AuditLogRecord(**{
        **alice.__dict__,
        "audit_scope": review_audit_scope("alice", "octo/demo"),
    })
    bob = _record(102)
    bob = AuditLogRecord(**{
        **bob.__dict__,
        "audit_scope": review_audit_scope("bob", "other/private"),
    })
    repository.append_audit_record(alice)
    repository.append_audit_record(bob)
    monkeypatch.setattr(operations, "audit_repo", repository)
    monkeypatch.setenv("VOLCAN_REVIEWERS", json.dumps({
        "alice": {"token": "a" * 40, "repositories": ["octo/demo"]},
        "bob": {"token": "b" * 40, "repositories": ["other/private"]},
    }))
    client = TestClient(app)

    # Anonymous callers get the public demo chain, never a reviewer's records.
    anonymous = client.get("/api/audit_log")
    assert anonymous.status_code == 200
    assert anonymous.json()["view"] == "public"
    assert anonymous.json()["records"] == []
    forged = client.get("/api/audit_log", headers={"Authorization": f"Bearer {'c' * 40}"})
    assert forged.json()["view"] == "public"
    assert forged.json()["records"] == []
    alice_view = client.get(
        "/api/audit_log", headers={"Authorization": f"Bearer {'a' * 40}"},
    ).json()
    bob_view = client.get(
        "/api/audit_log", headers={"Authorization": f"Bearer {'b' * 40}"},
    ).json()
    assert alice_view["view"] == "public_and_reviewer"
    assert [record["action"] for record in alice_view["records"]] == ["act-101"]
    assert [record["action"] for record in bob_view["records"]] == ["act-102"]
    assert all("alice" not in pk and "octo" not in pk for pk, _sk in table.items)
