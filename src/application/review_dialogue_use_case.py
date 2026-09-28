"""Use Case: one turn of the spoken review dialogue, side effects included.

The state machine in ``src/domain/review_dialogue.py`` decides what a
transcript means and where the conversation goes. This use case owns the three
things the domain refuses to do itself:

1. **Opening** a pull request, which is a live GitHub read through the port.
2. **Staging** a review, which mints a single-use approval grant bound to the
   pull request, its head commit and the comment body, the same HMAC grant the
   rest of the product uses for a governed action.
3. **Confirming** a review, which verifies custody and the grant, then hands the
   submission to the GitHub port. That port is dry-run by default and says so
   in its outcome; this use case relays the outcome and seals an audit record
   either way.

A human said "confirm" in the same session that staged the review, presenting
the grant that staging returned, inside the lease. That is the approval. The
authenticated reviewer comes from the HTTP credential roster, not user_id.
The GitHub token is separate service authority. The principal and commit
are bound in the grant's payload hash, with the head re-read by the port
before anything is sent.
"""
import asyncio
import base64
import hashlib
import logging
import time
from dataclasses import dataclass
from typing import Any, Protocol

from src.application.digest_diff_use_case import DigestDiffUseCase
from src.application.durable_state import (
    DurableStateError,
    ReviewSessionState,
    StateConflict,
    private_review_audit_scope,
    review_action_namespace,
    review_audit_scope,
)
from src.application.review_authorization import (
    ReviewAuthorizationError,
    current_review_principal,
    require_review_principal,
)
from src.application.sonify_event_use_case import SonifyEventUseCase
from src.domain.approval_grant import ApprovalGrantIssuer
from src.domain.governed_action import ActionState, GovernedAction, Principal
from src.domain.pull_request_read import read_failure_words
from src.domain.review_dialogue import (
    Command,
    DialogueState,
    DialogueTurn,
    PullRequestSnapshot,
    ReviewDialogue,
    parse_command,
)
from src.domain.sonification import EarconType
from src.domain.spoken_form import speakable

_log = logging.getLogger(__name__)

ACTION_TYPE = "GITHUB_REQUEST_CHANGES"
STAGING_PRINCIPAL = "volcan-review-dialogue"
class PullRequestReviewPort(Protocol):
    def parse_pull_request_url(self, url: str) -> tuple[str, str, int]: ...

    def fetch_pull_request(self, url: str) -> PullRequestSnapshot: ...

    def submit_request_changes(self, snapshot: PullRequestSnapshot, body: str, expected_head_sha: str): ...

    def capability(self) -> dict[str, Any]: ...


@dataclass
class _ReviewRuntime:
    dialogue: ReviewDialogue
    owner: str
    pending: GovernedAction | None
    pending_grant: str | None
    staged_count: int
    revision: int = 0
    new_action: GovernedAction | None = None


class ReviewDialogueUseCase:
    def __init__(
        self,
        digest_use_case: DigestDiffUseCase,
        github: PullRequestReviewPort,
        grant_issuer: ApprovalGrantIssuer,
        audit_repo,
        sonify_use_case: SonifyEventUseCase,
        lease_sec: float = 300.0,
        state_store: Any | None = None,
    ):
        self._digest = digest_use_case
        self._github = github
        self._issuer = grant_issuer
        self._audit = audit_repo
        self._sonify = sonify_use_case
        self._lease_sec = lease_sec
        self._state_store = state_store
        self._sessions: dict[str, ReviewDialogue] = {}
        self._pending: dict[str, GovernedAction] = {}
        self._pending_grants: dict[str, str] = {}
        self._staged_count = 0
        self._session_owners: dict[str, str | None] = {}

    def session(self, session_id: str) -> ReviewDialogue:
        if session_id not in self._sessions:
            self._sessions[session_id] = ReviewDialogue(session_id=session_id)
        return self._sessions[session_id]

    async def handle_turn(
        self,
        session_id: str,
        user_id: str,
        transcript: str,
        pr_url: str | None = None,
        raw_diff: str | None = None,
        approval_grant: str | None = None,
    ) -> dict[str, Any]:
        live = bool(self._github.capability()["write_enabled"])
        principal = require_review_principal() if live else None
        owner = principal.identity if principal else user_id.strip()
        if principal:
            user_id = principal.identity
        runtime = self._load_runtime(session_id, owner)
        dialogue = runtime.dialogue
        if principal and dialogue.pull_request is not None:
            principal.require_repository(dialogue.pull_request.owner, dialogue.pull_request.repo)
        command = parse_command(transcript)
        turn = dialogue.apply(command)
        extra: dict[str, Any] = {}

        if turn.needs == "open":
            turn = await self._open(runtime, command, pr_url, raw_diff)
        elif turn.needs == "resume":
            turn = await self._resume(runtime, command)
        elif turn.needs == "request_changes":
            turn, extra = self._stage(runtime, command)
        elif turn.needs == "confirm":
            turn, extra = await self._confirm(runtime, command, user_id, approval_grant)
        elif turn.needs == "cancel":
            self._drop_pending(runtime)
            turn = dialogue.cancel_review(command)

        payload = self._serialise(dialogue, turn, extra)
        self._commit_runtime(runtime)
        return payload

    def _load_runtime(self, session_id: str, owner: str) -> _ReviewRuntime:
        if self._state_store is None:
            if session_id in self._session_owners and self._session_owners[session_id] != owner:
                raise ReviewAuthorizationError(
                    "SESSION_OWNER_MISMATCH", 403,
                    "This review session belongs to a different identity or mode; start a new session.",
                )
            self._session_owners[session_id] = owner
            return _ReviewRuntime(
                dialogue=self.session(session_id), owner=owner,
                pending=self._pending.get(session_id),
                pending_grant=self._pending_grants.get(session_id),
                staged_count=self._staged_count,
            )

        stored = self._state_store.load_review(session_id, owner)
        if stored is None:
            return _ReviewRuntime(
                ReviewDialogue(session_id=session_id), owner, None, None, 0, 0
            )
        saved = stored.value
        if saved.owner != owner:
            raise ReviewAuthorizationError(
                "SESSION_OWNER_MISMATCH", 403,
                "This review session belongs to a different identity or mode; start a new session.",
            )
        pending = (
            self._state_store.get_action(
                self._action_namespace(saved.dialogue, saved.owner),
                saved.pending_action_id,
            )
            if saved.pending_action_id else None
        )
        return _ReviewRuntime(
            dialogue=saved.dialogue, owner=saved.owner, pending=pending,
            pending_grant=saved.pending_grant,
            staged_count=saved.staged_count, revision=stored.revision,
        )

    def _commit_runtime(self, runtime: _ReviewRuntime) -> None:
        session_id = runtime.dialogue.session_id
        if self._state_store is None:
            self._sessions[session_id] = runtime.dialogue
            self._session_owners[session_id] = runtime.owner
            self._staged_count = runtime.staged_count
            if runtime.pending is None:
                self._pending.pop(session_id, None)
                self._pending_grants.pop(session_id, None)
            else:
                self._pending[session_id] = runtime.pending
                if runtime.pending_grant:
                    self._pending_grants[session_id] = runtime.pending_grant
            return
        saved = ReviewSessionState(
            dialogue=runtime.dialogue,
            owner=runtime.owner,
            pending_action_id=runtime.pending.action_id if runtime.pending else None,
            pending_grant=runtime.pending_grant,
            staged_count=runtime.staged_count,
        )
        if runtime.new_action is not None:
            self._state_store.save_review_with_action(
                saved,
                runtime.revision,
                self._action_namespace(runtime.dialogue, runtime.owner),
                runtime.new_action,
            )
        else:
            self._state_store.save_review(saved, expected_revision=runtime.revision)

    def _drop_pending(self, runtime: _ReviewRuntime) -> None:
        action = runtime.pending
        if self._state_store is not None and action and action.state is ActionState.PENDING_APPROVAL:
            action.reject()
            action.execution_result = "REJECTED session cancelled or source changed"
            self._finalize_action(
                self._action_namespace(runtime.dialogue, runtime.owner),
                action,
                ActionState.PENDING_APPROVAL,
                "REJECTED session cancelled or source changed",
            )
        runtime.pending = None
        runtime.pending_grant = None
        runtime.new_action = None

    async def _resume(self, runtime: _ReviewRuntime, command: Command) -> DialogueTurn:
        dialogue = runtime.dialogue
        pr = dialogue.pull_request
        if pr is None:
            return dialogue.resume(command)
        try:
            live = await asyncio.to_thread(self._github.fetch_pull_request, pr.url)
        except Exception as exc:  # noqa: BLE001 - the reason is the answer
            _log.warning("refreshing %s failed: %r", pr.url, exc)
            return dialogue._turn(
                command, "resume",
                "The pull request could not be refreshed. "
                + read_failure_words(exc, pr.url, retry="say resume again"),
                error=True, earcon=EarconType.TEST_FAILED, remember=False,
            )
        if live.head_sha == pr.head_sha:
            return dialogue.resume(command)
        report = await self._digest.execute(live.diff)
        self._drop_pending(runtime)
        return dialogue.refresh(report, live, command, previous_head=pr.head_sha)

    # -- open ------------------------------------------------------------------

    async def _open(self, runtime: _ReviewRuntime, command: Command,
                    pr_url: str | None, raw_diff: str | None) -> DialogueTurn:
        dialogue = runtime.dialogue
        url = command.slots.get("url") or (pr_url or "").strip() or None
        if url:
            try:
                if current_review_principal.get() is not None:
                    owner, repo, _number = self._github.parse_pull_request_url(url)
                    current_review_principal.get().require_repository(owner, repo)
                snapshot = await asyncio.to_thread(self._github.fetch_pull_request, url)
            except ReviewAuthorizationError:
                raise
            except Exception as exc:  # noqa: BLE001 - the reason is the answer
                # The listener hears what failed and what to do, and the
                # readback names the pull request, since a link was given. The
                # exception, class name included, goes to the server log only.
                _log.warning("opening %s failed: %r", url, exc)
                return dialogue._turn(
                    command, "open the pull request",
                    "The pull request could not be opened. " + read_failure_words(exc, url),
                    error=True, earcon=EarconType.TEST_FAILED,
                )
            report = await self._digest.execute(snapshot.diff)
            self._drop_pending(runtime)
            return dialogue.load(report, snapshot, command)
        if raw_diff and raw_diff.strip():
            report = await self._digest.execute(raw_diff)
            self._drop_pending(runtime)
            return dialogue.load(report, None, command)
        return dialogue._turn(
            command, command.words,
            "Give me a pull request URL, or paste a patch, then say open.", error=True,
        )

    # -- stage -----------------------------------------------------------------

    def _stage(self, runtime: _ReviewRuntime, command: Command) -> tuple[DialogueTurn, dict[str, Any]]:
        dialogue = runtime.dialogue
        body = command.slots.get("body", "")
        normalized_body = body.strip()
        if runtime.pending is not None and runtime.pending.state is not ActionState.PENDING_APPROVAL:
            # Finalization may have committed before the session checkpoint.
            # The durable action is authoritative, so a later stage may replace
            # the stale session reference without reviving the old action.
            runtime.pending = None
            runtime.pending_grant = None
        if runtime.pending is not None:
            if (
                runtime.pending.state is ActionState.PENDING_APPROVAL
                and runtime.pending_grant
                and dialogue.pending_body == normalized_body
            ):
                turn = dialogue.stage_review(command, body)
                return turn, self._stage_payload(
                    dialogue, runtime.pending, runtime.pending_grant
                )
            return dialogue._turn(
                command,
                command.words,
                "A different review is already waiting. Say cancel before staging another.",
                error=True,
            ), {}
        turn = dialogue.stage_review(command, body)
        if turn.error:
            return turn, {}
        pr = dialogue.pull_request
        if current_review_principal.get() is not None:
            current_review_principal.get().require_repository(pr.owner, pr.repo)
        runtime.staged_count += 1
        body_hash = hashlib.sha256(dialogue.pending_body.encode("utf-8")).hexdigest()
        authenticated = current_review_principal.get()
        if authenticated is not None and authenticated.identity != runtime.owner:
            authenticated = None
        scope = (
            review_audit_scope(authenticated.identity, f"{pr.owner}/{pr.repo}")
            if authenticated is not None
            else private_review_audit_scope(
                runtime.owner,
                f"{pr.owner}/{pr.repo}",
                dialogue.session_id,
            )
        )
        action = GovernedAction.create(
            action_id=f"review-{dialogue.session_id}-{runtime.staged_count}",
            action_type=ACTION_TYPE,
            command_or_path=(
                f"REQUEST_CHANGES {pr.owner}/{pr.repo}#{pr.number} commit {pr.head_sha} "
                f"body_sha256 {body_hash} reviewer {runtime.owner}"
            ),
            summary_spoken=f"Request changes on {pr.label} at {pr.head_sha[:7]}",
            lease_sec=self._lease_sec,
            staged_by=Principal.agent(STAGING_PRINCIPAL),
            audit_scope=scope,
        )
        runtime.pending = action
        grant = self._issuer.issue(action.action_id, action.payload_hash, action.expires_at_epoch)
        runtime.pending_grant = grant
        runtime.new_action = action if self._state_store is not None else None
        return turn, self._stage_payload(dialogue, action, grant)

    def _stage_payload(
        self, dialogue: ReviewDialogue, action: GovernedAction, grant: str
    ) -> dict[str, Any]:
        pr = dialogue.pull_request
        return {
            "approval_grant": grant,
            "pending_review": {
                "action_id": action.action_id,
                "payload_hash": action.payload_hash,
                "expires_at_epoch": action.expires_at_epoch,
                "lease_sec": self._lease_sec,
                "body": dialogue.pending_body,
                "head_sha": pr.head_sha,
                "pull_request": pr.label,
            },
        }

    # -- confirm ---------------------------------------------------------------

    async def _confirm(self, runtime: _ReviewRuntime, command: Command, user_id: str,
                       grant: str | None) -> tuple[DialogueTurn, dict[str, Any]]:
        dialogue = runtime.dialogue
        action = runtime.pending
        pr = dialogue.pull_request
        if action is None or pr is None:
            turn = dialogue.record_outcome(
                command, "No review is staged in this session, so there is nothing to confirm.",
                submitted=False, dry_run=False, refused=True, earcon=EarconType.TEST_FAILED,
            )
            return turn, {"review_outcome": {"refusal_code": "UNKNOWN_ACTION", "submitted": False, "dry_run": False}}

        approver = Principal.human(user_id)
        principal = current_review_principal.get() if self._github.capability()["write_enabled"] else None
        if principal is not None:
            principal.require_repository(pr.owner, pr.repo)
            if runtime.owner != principal.identity:
                raise ReviewAuthorizationError(
                    "SESSION_OWNER_MISMATCH", 403, "This reviewer does not own the staged review."
                )
            approver = Principal.human(principal.identity)
        if self._state_store is not None and action.state is not ActionState.PENDING_APPROVAL:
            runtime.pending = None
            runtime.pending_grant = None
            spoken = "That review is no longer awaiting approval. Nothing was sent."
            turn = dialogue.record_outcome(
                command, spoken, submitted=False, dry_run=False, refused=True,
                earcon=EarconType.TEST_FAILED,
            )
            return turn, {"review_outcome": {
                "refusal_code": "NOT_PENDING", "submitted": False,
                "dry_run": False, "spoken": spoken,
            }}
        now = time.time()
        custody = action.check_custody(approver, now)
        if custody is not None:
            return self._refuse(runtime, command, action, custody.value,
                                f"Custody refused the confirmation: {custody.value}. Nothing was sent.")

        verdict = self._issuer.verify(
            grant or "",
            action.action_id,
            action.payload_hash,
            now_epoch=now,
            burn_on_success=self._state_store is None,
        )
        if not verdict.accepted:
            return self._refuse(runtime, command, action, verdict.refusal.value,
                                f"{verdict.spoken_reason} Nothing was sent.")

        action.mark_approved(grant, approver)
        if self._state_store is not None:
            try:
                self._state_store.claim_action_with_nonce(
                    self._action_namespace(dialogue, runtime.owner),
                    action,
                    ActionState.PENDING_APPROVAL,
                    verdict.nonce,
                    verdict.expires_at_epoch,
                )
            except StateConflict:
                runtime.pending = None
                runtime.pending_grant = None
                spoken = "That review is no longer awaiting approval. Nothing was sent."
                turn = dialogue.record_outcome(
                    command, spoken, submitted=False, dry_run=False, refused=True,
                    earcon=EarconType.TEST_FAILED,
                )
                return turn, {"review_outcome": {
                    "refusal_code": "NOT_PENDING", "submitted": False,
                    "dry_run": False, "spoken": spoken,
                }}
        submission = await asyncio.to_thread(
            self._github.submit_request_changes, pr, dialogue.pending_body, pr.head_sha,
        )
        outcome = submission.to_dict()
        outcome["spoken"] = submission.spoken

        if submission.submitted:
            action.state = ActionState.EXECUTED
            stdout = f"SUBMITTED review {submission.response.get('id')} at {pr.head_sha}"
            earcon = EarconType.ACTION_COMMITTED
        elif submission.dry_run:
            action.state = ActionState.APPROVED
            stdout = f"DRY RUN recorded, not sent: POST {submission.request['url']} commit_id {pr.head_sha}"
            earcon = EarconType.DRY_RUN_RECORDED
        else:
            action.state = ActionState.FAILED
            stdout = f"REFUSED {submission.refusal_code}: {submission.detail}"
            earcon = EarconType.TEST_FAILED
        action.execution_result = stdout
        self._finalize_action(
            self._action_namespace(dialogue, runtime.owner),
            action,
            ActionState.APPROVED,
            stdout,
        )
        runtime.pending = None
        runtime.pending_grant = None

        turn = dialogue.record_outcome(
            command, submission.spoken,
            submitted=submission.submitted, dry_run=submission.dry_run,
            refused=not (submission.submitted or submission.dry_run), earcon=earcon,
        )
        return turn, {"review_outcome": outcome}

    def _refuse(self, runtime: _ReviewRuntime, command: Command, action: GovernedAction,
                code: str, spoken: str) -> tuple[DialogueTurn, dict[str, Any]]:
        dialogue = runtime.dialogue
        previous_state = action.state
        action.state = ActionState.FAILED if action.state is ActionState.PENDING_APPROVAL else action.state
        action.execution_result = f"REFUSED {code}"
        if self._state_store is not None:
            expected = (
                ActionState.PENDING_APPROVAL
                if previous_state in {ActionState.PENDING_APPROVAL, ActionState.EXPIRED}
                else previous_state
            )
            self._finalize_action(
                self._action_namespace(dialogue, runtime.owner),
                action,
                expected,
                f"REFUSED {code}",
            )
        else:
            self._audit.append_audit_record(
                action.create_audit_record(stdout=f"REFUSED {code}")
            )
        runtime.pending = None
        runtime.pending_grant = None
        turn = dialogue.record_outcome(
            command, spoken, submitted=False, dry_run=False, refused=True, earcon=EarconType.TEST_FAILED,
        )
        return turn, {"review_outcome": {"refusal_code": code, "submitted": False, "dry_run": False, "spoken": spoken}}

    def _finalize_action(
        self,
        namespace: str,
        action: GovernedAction,
        expected: ActionState,
        stdout: str,
    ) -> None:
        record = action.create_audit_record(stdout=stdout)
        if self._state_store is None:
            self._audit.append_audit_record(record)
            return
        finalize = getattr(self._audit, "finalize_action", None)
        if finalize is None:
            raise DurableStateError(
                "durable actions require an audit repository with atomic finalization"
            )
        finalize(namespace, action, expected, record)

    @staticmethod
    def _action_namespace(dialogue: ReviewDialogue, owner: str) -> str:
        pr = dialogue.pull_request
        repository = f"{pr.owner}/{pr.repo}" if pr is not None else "unbound"
        return review_action_namespace(owner, repository, dialogue.session_id)

    # -- serialisation ---------------------------------------------------------

    def _serialise(self, dialogue: ReviewDialogue, turn: DialogueTurn, extra: dict[str, Any]) -> dict[str, Any]:
        earcon: dict[str, Any] | None = None
        wav: bytes | None = None
        if turn.earcon_type is not None:
            cue, wav = self._sonify.execute(turn.earcon_type)
            earcon = {
                "type": cue.earcon_type.value,
                "spoken_fallback": cue.spoken_fallback,
                "wav_base64": base64.b64encode(wav).decode("ascii"),
            }
        payload: dict[str, Any] = {
            "state": turn.state.value,
            "understood": turn.understood,
            "readback": turn.readback,
            "spoken": turn.spoken,
            # What a speech engine is handed: the same words with each code
            # operator named, so != is never heard as == or as nothing.
            "readback_for_speech": speakable(turn.readback),
            "spoken_for_speech": speakable(turn.spoken),
            "speech_rate": turn.speech_rate,
            "silent": turn.silent,
            "error": turn.error,
            "focus": turn.focus,
            "line": turn.line,
            "earcon": earcon,
            "pull_request": dialogue.pull_request.to_dict() if dialogue.pull_request else None,
            "pending_review": extra.get("pending_review"),
            "approval_grant": extra.get("approval_grant"),
            "review_outcome": extra.get("review_outcome"),
            "review_path": self._github.capability(),
            "awaiting_confirmation": dialogue.state is DialogueState.CONFIRM_REVIEW,
            "_wav": wav,
        }
        return payload
