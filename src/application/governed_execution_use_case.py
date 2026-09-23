"""Use Case: governed action staging, grant-verified release and audit persistence."""
import secrets
import time
from dataclasses import dataclass
from typing import Any, Protocol

from src.application.durable_state import DurableStateError, StateConflict, governed_audit_scope
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
        state_store: Any | None = None,
        action_namespace: str = "governed",
    ):
        self._executor = executor
        self._audit_repo = audit_repo
        self._issuer = grant_issuer or ApprovalGrantIssuer(secrets.token_bytes(32))
        self._allow_self_approval = allow_self_approval
        self._state_store = state_store
        self._action_namespace = action_namespace
        self._actions: dict[str, GovernedAction] = {}

    @property
    def grant_issuer(self) -> ApprovalGrantIssuer:
        return self._issuer

    @property
    def action_namespace(self) -> str:
        return self._action_namespace

    def stage_action(
        self,
        action_id: str,
        action_type: str,
        command: str,
        summary_spoken: str,
        lease_sec: float = 300.0,
        staged_by: Principal | None = None,
        persist: bool = True,
        audit_scope: str | None = None,
        action_namespace: str | None = None,
    ) -> StagedActionTicket:
        namespace = action_namespace or self._action_namespace
        action = GovernedAction.create(
            action_id, action_type, command, summary_spoken, lease_sec,
            staged_by=staged_by or Principal.agent(),
            audit_scope=audit_scope or governed_audit_scope(action_id),
        )
        if self._state_store is None:
            self._actions[f"{namespace}:{action_id}"] = action
        elif persist:
            self._state_store.put_action(namespace, action)
        grant = self._issuer.issue(action.action_id, action.payload_hash, action.expires_at_epoch)
        return StagedActionTicket(action=action, grant=grant, expires_at_epoch=action.expires_at_epoch)

    def get_action(
        self, action_id: str, action_namespace: str | None = None
    ) -> GovernedAction | None:
        namespace = action_namespace or self._action_namespace
        if self._state_store is None:
            return self._actions.get(f"{namespace}:{action_id}")
        return self._state_store.get_action(namespace, action_id)

    async def confirm_and_execute(
        self,
        action_id: str,
        grant: str,
        approver: Principal | None = None,
        action_namespace: str | None = None,
    ) -> ReleaseOutcome:
        namespace = action_namespace or self._action_namespace
        approver = approver or Principal.human()
        action = self.get_action(action_id, namespace)
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
            if self._state_store is not None and action.state is ActionState.EXPIRED:
                action.execution_result = f"REFUSED {custody.value}"
                self._finalize_action(
                    namespace,
                    action,
                    ActionState.PENDING_APPROVAL,
                    f"REFUSED {custody.value}",
                )
            return ReleaseOutcome(
                approved=False,
                refusal_code=custody.value,
                refusal_detail=_custody_detail(custody, action, approver),
                spoken_reason=_custody_spoken(custody),
            )

        verdict = self._issuer.verify(
            grant,
            action.action_id,
            action.payload_hash,
            now_epoch=now,
            burn_on_success=self._state_store is None,
        )
        if not verdict.accepted:
            refusal: GrantRefusal = verdict.refusal
            return ReleaseOutcome(
                approved=False,
                refusal_code=refusal.value,
                refusal_detail=verdict.detail,
                spoken_reason=verdict.spoken_reason,
            )

        action.mark_approved(grant, approver)
        if self._state_store is not None:
            try:
                self._state_store.claim_action_with_nonce(
                    namespace,
                    action,
                    ActionState.PENDING_APPROVAL,
                    verdict.nonce,
                    verdict.expires_at_epoch,
                )
            except StateConflict:
                current = self.get_action(action_id, namespace)
                detail = (
                    f"Action is in state {current.state.value}, not PENDING_APPROVAL."
                    if current else "The staged action no longer exists."
                )
                return ReleaseOutcome(
                    approved=False,
                    refusal_code=CustodyRefusal.NOT_PENDING.value,
                    refusal_detail=detail,
                    spoken_reason=_custody_spoken(CustodyRefusal.NOT_PENDING),
                )

        try:
            result = await self._executor.run_command(action.command_or_path)
        except Exception as ex:
            action.state = ActionState.FAILED
            action.execution_result = str(ex)
            self._finalize_action(
                namespace, action, ActionState.APPROVED, f"FAILED: {ex}"
            )
            raise
        action.state = ActionState.EXECUTED
        action.execution_result = result
        self._finalize_action(namespace, action, ActionState.APPROVED, result)
        return ReleaseOutcome(
            approved=True, output=result, spoken_reason="Authorization grant accepted."
        )

    def reject_action(
        self, action_id: str, action_namespace: str | None = None
    ) -> bool:
        namespace = action_namespace or self._action_namespace
        action = self.get_action(action_id, namespace)
        if not action or action.state != ActionState.PENDING_APPROVAL:
            return False
        action.reject()
        if self._state_store is not None:
            try:
                self._finalize_action(
                    namespace,
                    action,
                    ActionState.PENDING_APPROVAL,
                    "Action rejected by operator.",
                )
            except StateConflict:
                return False
        elif self._audit_repo:
            self._audit_repo.append_audit_record(action.create_audit_record(stdout="Action rejected by operator."))
        return True

    def _finalize_action(
        self,
        namespace: str,
        action: GovernedAction,
        expected: ActionState,
        stdout: str,
    ) -> None:
        if self._audit_repo is None:
            if self._state_store is not None:
                raise DurableStateError(
                    "durable actions require an audit repository for finalization"
                )
            return
        record = action.create_audit_record(stdout=stdout)
        if self._state_store is None:
            self._audit_repo.append_audit_record(record)
            return
        finalize = getattr(self._audit_repo, "finalize_action", None)
        if finalize is None:
            raise DurableStateError(
                "durable actions require an audit repository with atomic finalization"
            )
        finalize(namespace, action, expected, record)


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
