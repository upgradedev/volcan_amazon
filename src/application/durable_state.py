"""Application-level errors and snapshots for durable Lambda state.

The application layer deliberately knows nothing about DynamoDB.  It only
needs to distinguish a stale concurrent write from a storage outage and to
carry the revision that a repository must compare on the next write.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Generic, TypeVar

from src.domain.review_dialogue import ReviewDialogue
from src.domain.voice_session import VoiceSessionContext


class DurableStateError(RuntimeError):
    """Durable state could not be read or written safely."""


class StateConflict(DurableStateError):
    """Another worker changed the same state before this request committed."""


class DuplicateState(StateConflict):
    """A supposedly new durable identifier already exists."""


class StateTooLarge(DurableStateError):
    """A state document would exceed the deliberately bounded item size."""


class SessionOwnerMismatch(DurableStateError):
    """A session identifier was presented by a different user or repository."""


T = TypeVar("T")


@dataclass(frozen=True)
class VersionedState(Generic[T]):
    value: T
    revision: int


@dataclass
class ReviewSessionState:
    dialogue: ReviewDialogue
    owner: str
    pending_action_id: str | None = None
    pending_grant: str | None = None
    staged_count: int = 0


@dataclass
class VoiceSessionState:
    session: VoiceSessionContext
    owner: str
    repository: str


def review_audit_scope(identity: str, repository: str) -> str:
    """Stable authorization scope for one reviewer and one repository."""
    return f"review:{identity.strip().lower()}:{repository.strip().lower()}"


def review_action_namespace(owner: str, repository: str, session_id: str) -> str:
    """Opaque per-owner/repository/session namespace for review action ids."""
    material = "\x00".join(
        (owner.strip().lower(), repository.strip().lower(), session_id.strip())
    )
    return f"review-{hashlib.sha256(material.encode('utf-8')).hexdigest()}"


def private_review_audit_scope(owner: str, repository: str, session_id: str) -> str:
    """Unreadable-at-rest scope for a dry-run session without server identity."""
    material = "\x00".join(
        (owner.strip().lower(), repository.strip().lower(), session_id.strip())
    )
    return f"review-session:{hashlib.sha256(material.encode('utf-8')).hexdigest()}"


def voice_action_namespace(owner: str, repository: str, session_id: str) -> str:
    """Opaque per-session namespace for caller-selected voice action ids."""
    material = "\x00".join(
        (owner.strip().lower(), repository.strip().lower(), session_id.strip())
    )
    return f"voice-{hashlib.sha256(material.encode('utf-8')).hexdigest()}"
