"""Use Case: governed action staging, grant-verified release and audit persistence."""
import secrets
import time
from dataclasses import dataclass
from typing import Protocol

from src.domain.approval_grant import ApprovalGrantIssuer, GrantRefusal
from src.domain.governed_action import (
    ActionState,
    AuditLogRecord,
    CustodyRefusal,
    GovernedAction,
    Principal,
)


class CommandExecutionPort(Protocol):
    async def run_command(self, command: str) -> str:
        ...


class AuditRepositoryPort(Protocol):
    def append_audit_record(self, record: AuditLogRecord) -> None:
        ...

    def list_records(self) -> list[AuditLogRecord]:
        ...


@dataclass(frozen=True)
class StagedActionTicket:
    """What staging hands back: the action plus the grant that can release it."""

    action: GovernedAction
    grant: str
    expires_at_epoch: float


@dataclass(frozen=True)
class ReleaseOutcome:
    """The result of presenting a grant. A refusal is a first-class outcome."""

    approved: bool
    output: str | None = None
    refusal_code: str | None = None
    refusal_detail: str = ""
    spoken_reason: str = ""

    @property
    def refused(self) -> bool:
        return not self.approved


class GovernedExecutionUseCase:
    def __init__(
        self,
        executor: CommandExecutionPort,
        audit_repo: AuditRepositoryPort | None = None,
        grant_issuer: ApprovalGrantIssuer | None = None,
        allow_self_approval: bool = False,
    ):
        self._executor = executor
        self._audit_repo = audit_repo
        self._issuer = grant_issuer or ApprovalGrantIssuer(secrets.token_bytes(32))
        self._allow_self_approval = allow_self_approval
        self._actions: dict[str, GovernedAction] = {}

    @property
    def grant_issuer(self) -> ApprovalGrantIssuer:
        return self._issuer

    def stage_action(
        self,
        action_id: str,
        action_type: str,
        command: str,
        summary_spoken: str,
        lease_sec: float = 300.0,
        staged_by: Principal | None = None,
    ) -> StagedActionTicket:
        action = GovernedAction.create(
            action_id, action_type, command, summary_spoken, lease_sec,
            staged_by=staged_by or Principal.agent(),
        )
        self._actions[action_id] = action
        grant = self._issuer.issue(action.action_id, action.payload_hash, action.expires_at_epoch)
        return StagedActionTicket(action=action, grant=grant, expires_at_epoch=action.expires_at_epoch)

    def get_action(self, action_id: str) -> GovernedAction | None:
        return self._actions.get(action_id)

    async def confirm_and_execute(
        self,
        action_id: str,
        grant: str,
        approver: Principal | None = None,
    ) -> ReleaseOutcome:
        approver = approver or Principal.human()
        action = self._actions.get(action_id)
        if action is None:
            return ReleaseOutcome(
                approved=False,
                refusal_code="UNKNOWN_ACTION",
                refusal_detail=f"No staged action with id '{action_id}'.",
                spoken_reason="There is no staged action with that identifier.",
            )

        now = time.time()
        custody = action.check_custody(approver, now, allow_self_approval=self._allow_self_approval)
        if custody is not None:
            return ReleaseOutcome(
                approved=False,
                refusal_code=custody.value,
                refusal_detail=_custody_detail(custody, action, approver),
                spoken_reason=_custody_spoken(custody),
            )

        verdict = self._issuer.verify(grant, action.action_id, action.payload_hash, now_epoch=now)
        if not verdict.accepted:
            refusal: GrantRefusal = verdict.refusal
            return ReleaseOutcome(
                approved=False,
                refusal_code=refusal.value,
                refusal_detail=verdict.detail,
                spoken_reason=verdict.spoken_reason,
            )

        action.mark_approved(grant, approver)

        try:
            result = await self._executor.run_command(action.command_or_path)
            action.state = ActionState.EXECUTED
            action.execution_result = result
            if self._audit_repo:
                self._audit_repo.append_audit_record(action.create_audit_record(stdout=result))
            return ReleaseOutcome(approved=True, output=result, spoken_reason="Authorization grant accepted.")
        except Exception as ex:
            action.state = ActionState.FAILED
            action.execution_result = str(ex)
            if self._audit_repo:
                self._audit_repo.append_audit_record(action.create_audit_record(stdout=f"FAILED: {ex}"))
            raise

    def reject_action(self, action_id: str) -> bool:
        action = self._actions.get(action_id)
        if not action or action.state != ActionState.PENDING_APPROVAL:
            return False
        action.reject()
        if self._audit_repo:
            self._audit_repo.append_audit_record(action.create_audit_record(stdout="Action rejected by operator."))
        return True


def _custody_detail(refusal: CustodyRefusal, action: GovernedAction, approver: Principal) -> str:
    if refusal is CustodyRefusal.NOT_PENDING:
        return f"Action is in state {action.state.value}, not PENDING_APPROVAL."
    if refusal is CustodyRefusal.LEASE_EXPIRED:
        return f"Lease of {action.lease_duration_sec} seconds elapsed before approval."
    if refusal is CustodyRefusal.AGENT_MAY_NOT_APPROVE:
        return f"Principal '{approver.principal_id}' has role {approver.role.value}; only HUMAN may release an action."
    return f"Principal '{approver.principal_id}' staged this action and may not also approve it."


def _custody_spoken(refusal: CustodyRefusal) -> str:
    return {
        CustodyRefusal.NOT_PENDING: "That action is no longer awaiting approval.",
        CustodyRefusal.LEASE_EXPIRED: "The execution lease expired before you confirmed.",
        CustodyRefusal.AGENT_MAY_NOT_APPROVE: "An agent cannot approve its own proposal. A human must confirm.",
        CustodyRefusal.SELF_APPROVAL: "The principal that staged this action cannot also approve it.",
    }[refusal]
