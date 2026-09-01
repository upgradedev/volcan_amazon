"""Use Case: Voice-Governed Action Execution and Audit Persistence."""
import time
from typing import Dict, List, Optional, Protocol
from src.domain.governed_action import ActionState, AuditLogRecord, GovernedAction


class CommandExecutionPort(Protocol):
    async def run_command(self, command: str) -> str:
        ...


class AuditRepositoryPort(Protocol):
    def append_audit_record(self, record: AuditLogRecord) -> None:
        ...

    def list_records(self) -> List[AuditLogRecord]:
        ...


class GovernedExecutionUseCase:
    def __init__(self, executor: CommandExecutionPort, audit_repo: Optional[AuditRepositoryPort] = None):
        self._executor = executor
        self._audit_repo = audit_repo
        self._actions: Dict[str, GovernedAction] = {}

    def stage_action(
        self, action_id: str, action_type: str, command: str, summary_spoken: str, lease_sec: float = 300.0
    ) -> GovernedAction:
        action = GovernedAction.create(action_id, action_type, command, summary_spoken, lease_sec)
        self._actions[action_id] = action
        return action

    def get_action(self, action_id: str) -> Optional[GovernedAction]:
        return self._actions.get(action_id)

    async def confirm_and_execute(self, action_id: str, voice_token: str) -> Optional[str]:
        action = self._actions.get(action_id)
        if not action or action.state != ActionState.PENDING_APPROVAL:
            return None

        approved = action.approve(voice_token, current_time=time.time())
        if not approved:
            return None

        try:
            result = await self._executor.run_command(action.command_or_path)
            action.state = ActionState.EXECUTED
            action.execution_result = result
            if self._audit_repo:
                self._audit_repo.append_audit_record(action.create_audit_record(stdout=result))
            return result
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
            self._audit_repo.append_audit_record(action.create_audit_record(stdout="Action rejected by user."))
        return True
