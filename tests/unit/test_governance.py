"""Unit tests for staged actions, approval grants, custody rules and auditing.

Most of these are negative tests. A control that has never been observed to
refuse is not a control, so every refusal path has a test that reaches it.
"""
import asyncio
import time

import pytest

from src.application.governed_execution_use_case import GovernedExecutionUseCase
from src.domain.approval_grant import ApprovalGrantIssuer, GrantRefusal
from src.domain.governed_action import ActionState, GovernedAction, Principal
from src.infrastructure.audit_repository import InMemoryAuditRepository

SECRET = b"volcan-test-signing-secret-0001-x"


class RecordingExecutor:
    """Stands in for the dry-run planner and records what it was asked to plan."""

    def __init__(self):
        self.calls: list[str] = []

    async def run_command(self, command: str) -> str:
        self.calls.append(command)
        return f"PLANNED: {command}"


def make_use_case(**kwargs) -> tuple[GovernedExecutionUseCase, RecordingExecutor, InMemoryAuditRepository]:
    executor = RecordingExecutor()
    repo = InMemoryAuditRepository()
    use_case = GovernedExecutionUseCase(executor, repo, ApprovalGrantIssuer(SECRET), **kwargs)
    return use_case, executor, repo


# --- happy path -------------------------------------------------------------

def test_staged_action_is_released_by_a_valid_grant_and_audited():
    async def _run():
        use_case, executor, repo = make_use_case()
        ticket = use_case.stage_action(
            "act-001", "RUN_PYTEST", "pytest tests/unit", "Run the unit suite", lease_sec=30.0,
        )
        assert ticket.action.state == ActionState.PENDING_APPROVAL
        assert ticket.grant.startswith("v1.")

        outcome = await use_case.confirm_and_execute(
            "act-001", ticket.grant, approver=Principal.human("reviewer-1"),
        )
        assert outcome.approved is True
        assert outcome.output == "PLANNED: pytest tests/unit"
        assert executor.calls == ["pytest tests/unit"]
        assert ticket.action.state == ActionState.EXECUTED

        records = repo.list_records()
        assert len(records) == 1
        assert records[0].action_id == "act-001"
        assert records[0].staged_by == "volcan-agent"
        assert records[0].approved_by == "reviewer-1"
        assert len(records[0].approver_token_hash) == 64

    asyncio.run(_run())


# --- grant refusals ---------------------------------------------------------

def test_forged_grant_is_refused():
    async def _run():
        use_case, executor, _ = make_use_case()
        ticket = use_case.stage_action("act-forge", "RUN_PYTEST", "pytest tests/unit", "Run tests")
        version, body, signature = ticket.grant.split(".")
        forged = f"{version}.{body}.{'A' if signature[0] != 'A' else 'B'}{signature[1:]}"

        outcome = await use_case.confirm_and_execute("act-forge", forged, Principal.human("attacker"))
        assert outcome.refused
        assert outcome.refusal_code == GrantRefusal.BAD_SIGNATURE.value
        assert executor.calls == [], "a refused grant must never reach the executor"

    asyncio.run(_run())


def test_grant_minted_with_a_different_secret_is_refused():
    async def _run():
        use_case, executor, _ = make_use_case()
        ticket = use_case.stage_action("act-other-key", "RUN_PYTEST", "pytest tests/unit", "Run tests")
        rogue = ApprovalGrantIssuer(b"an-entirely-different-secret-xxxx").issue(
            "act-other-key", ticket.action.payload_hash, time.time() + 300,
        )
        outcome = await use_case.confirm_and_execute("act-other-key", rogue, Principal.human("attacker"))
        assert outcome.refusal_code == GrantRefusal.BAD_SIGNATURE.value
        assert executor.calls == []

    asyncio.run(_run())


def test_replayed_grant_is_refused_on_second_use():
    async def _run():
        use_case, executor, _ = make_use_case()
        ticket = use_case.stage_action("act-replay", "RUN_PYTEST", "pytest tests/unit", "Run tests")
        first = await use_case.confirm_and_execute("act-replay", ticket.grant, Principal.human("r1"))
        assert first.approved is True

        # Stage a second action with an identical payload, then replay the burned grant.
        second_ticket = use_case.stage_action(
            "act-replay", "RUN_PYTEST", "pytest tests/unit", "Run tests",
        )
        assert second_ticket.grant != ticket.grant
        replayed = await use_case.confirm_and_execute("act-replay", ticket.grant, Principal.human("r1"))
        assert replayed.refused
        assert replayed.refusal_code == GrantRefusal.REPLAYED.value
        assert executor.calls == ["pytest tests/unit"], "the replay must not plan a second time"

    asyncio.run(_run())


def test_grant_for_a_different_action_is_refused():
    async def _run():
        use_case, executor, _ = make_use_case()
        ticket_a = use_case.stage_action("act-a", "RUN_PYTEST", "pytest tests/unit", "A")
        use_case.stage_action("act-b", "RUN_PYTEST", "pytest tests/unit", "B")

        outcome = await use_case.confirm_and_execute("act-b", ticket_a.grant, Principal.human("r1"))
        assert outcome.refusal_code == GrantRefusal.WRONG_ACTION.value
        assert executor.calls == []

    asyncio.run(_run())


def test_grant_is_bound_to_the_command_and_refused_after_the_command_changes():
    issuer = ApprovalGrantIssuer(SECRET)
    original_hash = GovernedAction.compute_payload_hash("DEPLOY", "pytest tests/unit")
    grant = issuer.issue("act-bind", original_hash, time.time() + 300)

    tampered_hash = GovernedAction.compute_payload_hash("DEPLOY", "pytest tests/unit --exitfirst")
    verdict = issuer.verify(grant, "act-bind", tampered_hash)
    assert verdict.accepted is False
    assert verdict.refusal is GrantRefusal.CONTENT_MISMATCH


def test_expired_grant_is_refused():
    issuer = ApprovalGrantIssuer(SECRET)
    payload_hash = GovernedAction.compute_payload_hash("RUN", "pytest")
    grant = issuer.issue("act-exp", payload_hash, time.time() - 1.0)
    verdict = issuer.verify(grant, "act-exp", payload_hash)
    assert verdict.refusal is GrantRefusal.EXPIRED


@pytest.mark.parametrize("bad_grant", ["", "not-a-grant", "v1.only-two", "v2.abc.def", "v1..", "v1.!!!.zzz"])
def test_malformed_grants_are_refused_without_raising(bad_grant):
    issuer = ApprovalGrantIssuer(SECRET)
    verdict = issuer.verify(bad_grant, "act", "hash")
    assert verdict.accepted is False
    assert verdict.refusal in {GrantRefusal.MALFORMED, GrantRefusal.BAD_SIGNATURE}


def test_issuer_rejects_a_weak_signing_secret():
    with pytest.raises(ValueError):
        ApprovalGrantIssuer(b"short")


# --- custody rules ----------------------------------------------------------

def test_an_agent_may_not_approve_its_own_proposal():
    async def _run():
        use_case, executor, _ = make_use_case()
        ticket = use_case.stage_action("act-agent", "DEPLOY", "pytest tests/unit", "Deploy")
        outcome = await use_case.confirm_and_execute(
            "act-agent", ticket.grant, approver=Principal.agent("volcan-agent"),
        )
        assert outcome.refused
        assert outcome.refusal_code == "AGENT_MAY_NOT_APPROVE"
        assert executor.calls == []

    asyncio.run(_run())


def test_the_principal_that_staged_an_action_may_not_also_approve_it():
    async def _run():
        use_case, executor, _ = make_use_case()
        ticket = use_case.stage_action(
            "act-self", "DEPLOY", "pytest tests/unit", "Deploy",
            staged_by=Principal.human("same-person"),
        )
        outcome = await use_case.confirm_and_execute(
            "act-self", ticket.grant, approver=Principal.human("same-person"),
        )
        assert outcome.refusal_code == "SELF_APPROVAL"
        assert executor.calls == []

    asyncio.run(_run())


def test_self_approval_is_possible_only_when_explicitly_enabled():
    async def _run():
        use_case, executor, _ = make_use_case(allow_self_approval=True)
        ticket = use_case.stage_action(
            "act-self-ok", "RUN", "pytest tests/unit", "Run",
            staged_by=Principal.human("solo-dev"),
        )
        outcome = await use_case.confirm_and_execute(
            "act-self-ok", ticket.grant, approver=Principal.human("solo-dev"),
        )
        assert outcome.approved is True
        assert executor.calls == ["pytest tests/unit"]

    asyncio.run(_run())


def test_expired_lease_cannot_be_approved():
    async def _run():
        use_case, executor, _ = make_use_case()
        ticket = use_case.stage_action(
            "act-expired", "DEPLOY", "pytest tests/unit", "Deploy", lease_sec=0.01,
        )
        ticket.action.created_at_epoch = time.time() - 10.0
        outcome = await use_case.confirm_and_execute("act-expired", ticket.grant, Principal.human("r"))
        assert outcome.refusal_code == "LEASE_EXPIRED"
        assert ticket.action.state == ActionState.EXPIRED
        assert executor.calls == []

    asyncio.run(_run())


def test_an_action_cannot_be_released_twice():
    async def _run():
        use_case, executor, _ = make_use_case()
        ticket = use_case.stage_action("act-once", "RUN", "pytest tests/unit", "Run")
        assert (await use_case.confirm_and_execute("act-once", ticket.grant, Principal.human("r"))).approved
        second = await use_case.confirm_and_execute("act-once", ticket.grant, Principal.human("r"))
        assert second.refusal_code == "NOT_PENDING"
        assert executor.calls == ["pytest tests/unit"]

    asyncio.run(_run())


def test_rejection_lifecycle():
    use_case, _executor, repo = make_use_case()
    ticket = use_case.stage_action("act-reject", "DELETE_FILE", "rm temp.py", "Delete temp file")
    assert use_case.reject_action("act-reject") is True
    assert ticket.action.state == ActionState.REJECTED
    assert use_case.reject_action("act-reject") is False
    assert repo.list_records()[0].approved_by == "unapproved"
