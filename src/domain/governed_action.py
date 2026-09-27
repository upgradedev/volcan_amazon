"""Domain entity for governed action staging, approval and audit logging.

Custody model, stated exactly as implemented: an autonomous agent may *stage*
an action, and only a principal whose role is HUMAN may *release* it. An agent
cannot approve its own proposal, and no principal can approve an action it
staged itself unless the caller explicitly allows self-approval. The approval
itself is an :class:`~src.domain.approval_grant.ApprovalGrantIssuer` grant, not
a free-form string.
"""
import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class ActionState(str, Enum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    #: A governed command a human approved, handed back as a plan by the
    #: dry-run planner. Nothing ran, and the stored word says so.
    RELEASED_NOT_RUN = "RELEASED_NOT_RUN"
    #: Something left this process: a review that was really submitted to
    #: GitHub. Records sealed before RELEASED_NOT_RUN existed also carry it
    #: for a released plan, so it stays decodable.
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


class PrincipalRole(str, Enum):
    AGENT = "AGENT"
    HUMAN = "HUMAN"


@dataclass(frozen=True)
class Principal:
    """Who is acting. Role decides what the principal is allowed to do."""

    principal_id: str
    role: PrincipalRole = PrincipalRole.HUMAN

    @classmethod
    def agent(cls, principal_id: str = "volcan-agent") -> "Principal":
        return cls(principal_id=principal_id, role=PrincipalRole.AGENT)

    @classmethod
    def human(cls, principal_id: str = "developer") -> "Principal":
        return cls(principal_id=principal_id, role=PrincipalRole.HUMAN)


class CustodyRefusal(str, Enum):
    NOT_PENDING = "NOT_PENDING"
    LEASE_EXPIRED = "LEASE_EXPIRED"
    AGENT_MAY_NOT_APPROVE = "AGENT_MAY_NOT_APPROVE"
    SELF_APPROVAL = "SELF_APPROVAL"


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
    staged_by: str = "unknown"
    approved_by: str = "unapproved"
    # Durable repositories use this value to select an isolated hash chain.
    # It is deliberately part of the record seal; moving a record between
    # scopes after the fact therefore breaks verification.
    audit_scope: str = "local"
    #: Position in the tamper-evident chain, filled in when the record is sealed
    #: by src/domain/audit_chain.py. -1 means the record has not been sealed.
    sequence: int = -1
    previous_hash: str = ""
    entry_hash: str = ""


@dataclass
class GovernedAction:
    action_id: str
    action_type: str
    command_or_path: str
    payload_hash: str
    summary_spoken: str
    staged_by: Principal = field(default_factory=Principal.agent)
    state: ActionState = ActionState.PENDING_APPROVAL
    created_at_epoch: float = field(default_factory=time.time)
    lease_duration_sec: float = 300.0
    approval_token: str | None = None
    approved_by: Principal | None = None
    execution_result: str | None = None
    audit_scope: str = "local"

    @classmethod
    def create(
        cls,
        action_id: str,
        action_type: str,
        command_or_path: str,
        summary_spoken: str,
        lease_sec: float = 300.0,
        staged_by: Principal | None = None,
        audit_scope: str = "local",
    ) -> "GovernedAction":
        return cls(
            action_id=action_id,
            action_type=action_type,
            command_or_path=command_or_path,
            payload_hash=cls.compute_payload_hash(action_type, command_or_path, audit_scope),
            summary_spoken=summary_spoken,
            staged_by=staged_by or Principal.agent(),
            state=ActionState.PENDING_APPROVAL,
            created_at_epoch=time.time(),
            lease_duration_sec=lease_sec,
            audit_scope=audit_scope,
        )

    @staticmethod
    def compute_payload_hash(
        action_type: str, command_or_path: str, binding_context: str = "local"
    ) -> str:
        """The content binding an approval grant is signed over."""
        return hashlib.sha256(
            f"{action_type}:{command_or_path}:{binding_context}".encode()
        ).hexdigest()

    @property
    def expires_at_epoch(self) -> float:
        return self.created_at_epoch + self.lease_duration_sec

    def is_expired(self, current_time: float | None = None) -> bool:
        now = time.time() if current_time is None else current_time
        return (now - self.created_at_epoch) > self.lease_duration_sec

    def check_custody(
        self,
        approver: Principal,
        current_time: float | None = None,
        allow_self_approval: bool = False,
    ) -> CustodyRefusal | None:
        """Returns the refusal reason, or None when custody rules are satisfied."""
        if self.state != ActionState.PENDING_APPROVAL:
            return CustodyRefusal.NOT_PENDING
        if self.is_expired(current_time):
            self.state = ActionState.EXPIRED
            return CustodyRefusal.LEASE_EXPIRED
        if approver.role is not PrincipalRole.HUMAN:
            return CustodyRefusal.AGENT_MAY_NOT_APPROVE
        if not allow_self_approval and approver.principal_id == self.staged_by.principal_id:
            return CustodyRefusal.SELF_APPROVAL
        return None

    def mark_approved(self, grant: str, approver: Principal) -> None:
        self.state = ActionState.APPROVED
        self.approval_token = grant
        self.approved_by = approver

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
            timestamp=datetime.now(timezone.utc).isoformat(),
            staged_by=self.staged_by.principal_id,
            approved_by=self.approved_by.principal_id if self.approved_by else "unapproved",
            audit_scope=self.audit_scope,
        )
