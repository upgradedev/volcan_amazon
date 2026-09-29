"""Unit tests for the tamper-evident audit chain.

The claim is narrow and the tests hold it to exactly that width: an edit to a
stored record is *detected*, and the verdict names which entry broke. Nothing
here claims the chain is tamper-proof, because it is not.
"""
from dataclasses import replace

from src.domain.audit_chain import GENESIS_HASH, verify_chain
from src.domain.governed_action import ActionState, AuditLogRecord
from src.infrastructure.audit_repository import InMemoryAuditRepository


def make_record(index: int) -> AuditLogRecord:
    return AuditLogRecord(
        record_id=f"AUDIT-{index}",
        action_id=f"act-{index}",
        action_type="RUN_TESTS",
        command="pytest tests/unit",
        payload_hash="a" * 64,
        approver_token_hash="b" * 64,
        state=ActionState.EXECUTED,
        execution_stdout="PLANNED: pytest tests/unit",
        timestamp=f"2026-09-05T00:00:0{index}+00:00",
        staged_by="volcan-agent",
        approved_by="reviewer",
    )


def filled_repository(count: int = 4) -> InMemoryAuditRepository:
    repo = InMemoryAuditRepository()
    for index in range(count):
        repo.append_audit_record(make_record(index))
    return repo


def test_an_empty_chain_is_intact_and_starts_at_genesis():
    repo = InMemoryAuditRepository()
    verdict = repo.verify_integrity()
    assert verdict.intact is True
    assert verdict.verified_entries == 0
    assert repo.head_hash == GENESIS_HASH


def test_each_record_links_to_the_one_before_it():
    repo = filled_repository()
    records = repo.list_records()
    assert records[0].previous_hash == GENESIS_HASH
    for earlier, later in zip(records, records[1:]):
        assert later.previous_hash == earlier.entry_hash
        assert later.sequence == earlier.sequence + 1
    assert repo.verify_integrity().intact is True
    assert repo.head_hash == records[-1].entry_hash


def test_two_identical_records_receive_different_seals():
    """Position is part of the seal, so a duplicated entry cannot be swapped in."""
    repo = InMemoryAuditRepository()
    first = repo.append_audit_record(make_record(0))
    second = repo.append_audit_record(make_record(0))
    assert first.entry_hash != second.entry_hash


def test_editing_a_stored_field_is_detected_and_the_entry_is_named():
    repo = filled_repository()
    records = repo.list_records()
    tampered = list(records)
    tampered[1] = replace(records[1], command="rm -rf /")

    verdict = verify_chain(tampered)
    assert verdict.intact is False
    assert verdict.broken_at_sequence == 1
    assert "altered after it was written" in verdict.detail


def test_deleting_an_entry_breaks_the_chain():
    records = filled_repository().list_records()
    verdict = verify_chain([records[0], records[2], records[3]])
    assert verdict.intact is False
    assert verdict.broken_at_sequence == 1


def test_reordering_entries_breaks_the_chain():
    records = filled_repository().list_records()
    verdict = verify_chain([records[1], records[0], records[2], records[3]])
    assert verdict.intact is False
    assert verdict.broken_at_sequence == 0


def test_appending_an_unsealed_record_breaks_the_chain():
    records = filled_repository().list_records()
    verdict = verify_chain([*records, make_record(9)])
    assert verdict.intact is False
    assert verdict.broken_at_sequence == len(records)


def test_a_repository_used_through_governance_stays_verifiable():
    import asyncio

    from src.application.governed_execution_use_case import GovernedExecutionUseCase
    from src.domain.approval_grant import ApprovalGrantIssuer
    from src.domain.governed_action import Principal
    from src.infrastructure.dry_run_executor import DryRunExecutor

    async def _run():
        repo = InMemoryAuditRepository()
        use_case = GovernedExecutionUseCase(
            DryRunExecutor(), repo, ApprovalGrantIssuer(b"chain-test-signing-secret-000001"),
        )
        for index in range(3):
            ticket = use_case.stage_action(
                f"act-chain-{index}", "RUN_TESTS", "pytest tests/unit", "Run the unit suite",
            )
            outcome = await use_case.confirm_and_execute(
                f"act-chain-{index}", ticket.grant, Principal.human("reviewer"),
            )
            assert outcome.approved is True

        verdict = repo.verify_integrity()
        assert verdict.intact is True
        assert verdict.verified_entries == 3

    asyncio.run(_run())
