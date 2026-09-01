"""Domain entity for Voice-Governed Action Execution and Audit Logging."""
import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class ActionState(str, Enum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True)
class AuditLogRecord:
    record_id: str
    action_id: str
    action_type: str
    command: str
    payload_hash: str
    approver_token_hash: str
    state: ActionState
    execution_stdout: str
    timestamp: str


@dataclass
class GovernedAction:
    action_id: str
    action_type: str
    command_or_path: str
    payload_hash: str
    summary_spoken: str
    state: ActionState = ActionState.PENDING_APPROVAL
    created_at_epoch: float = field(default_factory=time.time)
    lease_duration_sec: float = 300.0
    approval_token: Optional[str] = None
    execution_result: Optional[str] = None

    @classmethod
    def create(
        cls, action_id: str, action_type: str, command_or_path: str, summary_spoken: str, lease_sec: float = 300.0
    ) -> "GovernedAction":
        content = f"{action_type}:{command_or_path}".encode("utf-8")
        payload_hash = hashlib.sha256(content).hexdigest()
        return cls(
            action_id=action_id,
            action_type=action_type,
            command_or_path=command_or_path,
            payload_hash=payload_hash,
            summary_spoken=summary_spoken,
            state=ActionState.PENDING_APPROVAL,
            created_at_epoch=time.time(),
            lease_duration_sec=lease_sec,
        )

    def is_expired(self, current_time: Optional[float] = None) -> bool:
        now = current_time or time.time()
        return (now - self.created_at_epoch) > self.lease_duration_sec

    def approve(self, token: str, current_time: Optional[float] = None) -> bool:
        if self.is_expired(current_time):
            self.state = ActionState.EXPIRED
            return False
        if self.state != ActionState.PENDING_APPROVAL:
            return False
        if not token or not token.strip():
            return False

        self.state = ActionState.APPROVED
        self.approval_token = token
        return True

    def reject(self) -> None:
        self.state = ActionState.REJECTED

    def create_audit_record(self, stdout: str) -> AuditLogRecord:
        token_hash = (
            hashlib.sha256(self.approval_token.encode("utf-8")).hexdigest()
            if self.approval_token
            else "unauthorized"
        )
        return AuditLogRecord(
            record_id=f"AUDIT-{self.action_id}",
            action_id=self.action_id,
            action_type=self.action_type,
            command=self.command_or_path,
            payload_hash=self.payload_hash,
            approver_token_hash=token_hash,
            state=self.state,
            execution_stdout=stdout,
            timestamp=datetime.utcnow().isoformat(),
        )
