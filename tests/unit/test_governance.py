"""Unit tests for Voice Governance, Leases, and Audit Logging."""
import asyncio
import time

from src.application.governed_execution_use_case import GovernedExecutionUseCase
from src.domain.governed_action import ActionState
from src.infrastructure.audit_repository import InMemoryAuditRepository


class MockExecutor:
    async def run_command(self, command: str) -> str:
        return f"SUCCESS: {command}"


def test_governed_action_lifecycle_and_audit():
    async def _test():
        audit_repo = InMemoryAuditRepository()
        use_case = GovernedExecutionUseCase(MockExecutor(), audit_repo)
        
        # 1. Stage
        action = use_case.stage_action(
            action_id="act-001",
            action_type="RUN_PYTEST",
            command="pytest tests/unit",
            summary_spoken="Run full test suite",
            lease_sec=10.0
        )
        assert action.state == ActionState.PENDING_APPROVAL

        # 2. Confirm
        output = await use_case.confirm_and_execute("act-001", "VOICE_TOKEN_123")
        assert output == "SUCCESS: pytest tests/unit"
        assert action.state == ActionState.EXECUTED

        # 3. Check Audit Log
        records = audit_repo.list_records()
        assert len(records) == 1
        rec = records[0]
        assert rec.action_id == "act-001"
        assert rec.state == ActionState.EXECUTED
        assert len(rec.approver_token_hash) == 64
    asyncio.run(_test())


def test_expired_action_cannot_be_approved():
    async def _test():
        use_case = GovernedExecutionUseCase(MockExecutor())
        action = use_case.stage_action(
            action_id="act-expired",
            action_type="DEPLOY",
            command="deploy prod",
            summary_spoken="Deploy to production",
            lease_sec=0.01
        )
        
        # Manually expire
        action.created_at_epoch = time.time() - 10.0
        res = await use_case.confirm_and_execute("act-expired", "TOKEN")
        assert res is None
        assert action.state == ActionState.EXPIRED
    asyncio.run(_test())


def test_rejection_lifecycle():
    use_case = GovernedExecutionUseCase(MockExecutor())
    action = use_case.stage_action("act-reject", "DELETE_FILE", "rm temp.py", "Delete temp file")
    rejected = use_case.reject_action("act-reject")
    assert rejected is True
    assert action.state == ActionState.REJECTED
