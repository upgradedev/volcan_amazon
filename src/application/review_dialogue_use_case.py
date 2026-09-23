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
import time
from typing import Any, Protocol

from src.application.digest_diff_use_case import DigestDiffUseCase
from src.application.review_authorization import (
    ReviewAuthorizationError,
    require_review_principal,
)
from src.application.sonify_event_use_case import SonifyEventUseCase
from src.domain.approval_grant import ApprovalGrantIssuer
from src.domain.governed_action import ActionState, GovernedAction, Principal
from src.domain.review_dialogue import (
    Command,
    DialogueState,
    DialogueTurn,
    PullRequestSnapshot,
    ReviewDialogue,
    parse_command,
)
from src.domain.sonification import EarconType

ACTION_TYPE = "GITHUB_REQUEST_CHANGES"
STAGING_PRINCIPAL = "volcan-review-dialogue"


class PullRequestReviewPort(Protocol):
    def parse_pull_request_url(self, url: str) -> tuple[str, str, int]: ...

    def fetch_pull_request(self, url: str) -> PullRequestSnapshot: ...

    def submit_request_changes(self, snapshot: PullRequestSnapshot, body: str, expected_head_sha: str): ...

    def capability(self) -> dict[str, Any]: ...


class ReviewDialogueUseCase:
    def __init__(
        self,
        digest_use_case: DigestDiffUseCase,
        github: PullRequestReviewPort,
        grant_issuer: ApprovalGrantIssuer,
        audit_repo,
        sonify_use_case: SonifyEventUseCase,
        lease_sec: float = 300.0,
    ):
        self._digest = digest_use_case
        self._github = github
        self._issuer = grant_issuer
        self._audit = audit_repo
        self._sonify = sonify_use_case
        self._lease_sec = lease_sec
        self._sessions: dict[str, ReviewDialogue] = {}
        self._pending: dict[str, GovernedAction] = {}
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
        if session_id in self._session_owners and self._session_owners[session_id] != owner:
            raise ReviewAuthorizationError(
                "SESSION_OWNER_MISMATCH", 403,
                "This review session belongs to a different identity or mode; start a new session.",
            )
        self._session_owners[session_id] = owner
        if principal:
            user_id = principal.identity
        dialogue = self.session(session_id)
        if principal and dialogue.pull_request is not None:
            principal.require_repository(dialogue.pull_request.owner, dialogue.pull_request.repo)
        command = parse_command(transcript)
        turn = dialogue.apply(command)
        extra: dict[str, Any] = {}

        if turn.needs == "open":
            turn = await self._open(dialogue, command, pr_url, raw_diff)
        elif turn.needs == "resume":
            turn = await self._resume(dialogue, command)
        elif turn.needs == "request_changes":
            turn, extra = self._stage(dialogue, command)
        elif turn.needs == "confirm":
            turn, extra = await self._confirm(dialogue, command, user_id, approval_grant)
        elif turn.needs == "cancel":
            self._pending.pop(session_id, None)
            turn = dialogue.cancel_review(command)

        return self._serialise(dialogue, turn, extra)

    async def _resume(self, dialogue: ReviewDialogue, command: Command) -> DialogueTurn:
        pr = dialogue.pull_request
        if pr is None:
            return dialogue.resume(command)
        try:
            live = await asyncio.to_thread(self._github.fetch_pull_request, pr.url)
        except Exception as exc:  # noqa: BLE001 - the reason is the answer
            return dialogue._turn(
                command, "resume",
                f"The pull request could not be refreshed. {type(exc).__name__}: {exc}",
                error=True, earcon=EarconType.TEST_FAILED, remember=False,
            )
        if live.head_sha == pr.head_sha:
            return dialogue.resume(command)
        report = await self._digest.execute(live.diff)
        self._pending.pop(dialogue.session_id, None)
        return dialogue.refresh(report, live, command, previous_head=pr.head_sha)

    # -- open ------------------------------------------------------------------

    async def _open(self, dialogue: ReviewDialogue, command: Command,
                    pr_url: str | None, raw_diff: str | None) -> DialogueTurn:
        url = command.slots.get("url") or (pr_url or "").strip() or None
        if url:
            try:
                if self._github.capability()["write_enabled"]:
                    owner, repo, _number = self._github.parse_pull_request_url(url)
                    require_review_principal().require_repository(owner, repo)
                snapshot = await asyncio.to_thread(self._github.fetch_pull_request, url)
            except ReviewAuthorizationError:
                raise
            except Exception as exc:  # noqa: BLE001 - the reason is the answer
                return dialogue._turn(
                    command, command.words,
                    f"The pull request could not be opened. {type(exc).__name__}: {exc}",
                    error=True, earcon=EarconType.TEST_FAILED,
                )
            report = await self._digest.execute(snapshot.diff)
            self._pending.pop(dialogue.session_id, None)
            return dialogue.load(report, snapshot, command)
        if raw_diff and raw_diff.strip():
            report = await self._digest.execute(raw_diff)
            self._pending.pop(dialogue.session_id, None)
            return dialogue.load(report, None, command)
        return dialogue._turn(
            command, command.words,
            "Give me a pull request URL, or paste a patch, then say open.", error=True,
        )

    # -- stage -----------------------------------------------------------------

    def _stage(self, dialogue: ReviewDialogue, command: Command) -> tuple[DialogueTurn, dict[str, Any]]:
        body = command.slots.get("body", "")
        turn = dialogue.stage_review(command, body)
        if turn.error:
            return turn, {}
        pr = dialogue.pull_request
        if self._github.capability()["write_enabled"]:
            require_review_principal().require_repository(pr.owner, pr.repo)
        self._staged_count += 1
        body_hash = hashlib.sha256(dialogue.pending_body.encode("utf-8")).hexdigest()
        action = GovernedAction.create(
            action_id=f"review-{dialogue.session_id}-{self._staged_count}",
            action_type=ACTION_TYPE,
            command_or_path=(
                f"REQUEST_CHANGES {pr.owner}/{pr.repo}#{pr.number} commit {pr.head_sha} "
                f"body_sha256 {body_hash} reviewer {self._session_owners.get(dialogue.session_id)}"
            ),
            summary_spoken=f"Request changes on {pr.label} at {pr.head_sha[:7]}",
            lease_sec=self._lease_sec,
            staged_by=Principal.agent(STAGING_PRINCIPAL),
        )
        self._pending[dialogue.session_id] = action
        grant = self._issuer.issue(action.action_id, action.payload_hash, action.expires_at_epoch)
        return turn, {
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

    async def _confirm(self, dialogue: ReviewDialogue, command: Command, user_id: str,
                       grant: str | None) -> tuple[DialogueTurn, dict[str, Any]]:
        action = self._pending.get(dialogue.session_id)
        pr = dialogue.pull_request
        if action is None or pr is None:
            turn = dialogue.record_outcome(
                command, "No review is staged in this session, so there is nothing to confirm.",
                submitted=False, dry_run=False, refused=True, earcon=EarconType.TEST_FAILED,
            )
            return turn, {"review_outcome": {"refusal_code": "UNKNOWN_ACTION", "submitted": False, "dry_run": False}}

        approver = Principal.human(user_id)
        if self._github.capability()["write_enabled"]:
            principal = require_review_principal()
            principal.require_repository(pr.owner, pr.repo)
            if self._session_owners.get(dialogue.session_id) != principal.identity:
                raise ReviewAuthorizationError(
                    "SESSION_OWNER_MISMATCH", 403, "This reviewer does not own the staged review."
                )
            approver = Principal.human(principal.identity)
        now = time.time()
        custody = action.check_custody(approver, now)
        if custody is not None:
            return self._refuse(dialogue, command, action, custody.value,
                                f"Custody refused the confirmation: {custody.value}. Nothing was sent.")

        verdict = self._issuer.verify(grant or "", action.action_id, action.payload_hash, now_epoch=now)
        if not verdict.accepted:
            return self._refuse(dialogue, command, action, verdict.refusal.value,
                                f"{verdict.spoken_reason} Nothing was sent.")

        action.mark_approved(grant, approver)
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
        self._audit.append_audit_record(action.create_audit_record(stdout=stdout))
        self._pending.pop(dialogue.session_id, None)

        turn = dialogue.record_outcome(
            command, submission.spoken,
            submitted=submission.submitted, dry_run=submission.dry_run,
            refused=not (submission.submitted or submission.dry_run), earcon=earcon,
        )
        return turn, {"review_outcome": outcome}

    def _refuse(self, dialogue: ReviewDialogue, command: Command, action: GovernedAction,
                code: str, spoken: str) -> tuple[DialogueTurn, dict[str, Any]]:
        action.state = ActionState.FAILED if action.state is ActionState.PENDING_APPROVAL else action.state
        self._audit.append_audit_record(action.create_audit_record(stdout=f"REFUSED {code}"))
        self._pending.pop(dialogue.session_id, None)
        turn = dialogue.record_outcome(
            command, spoken, submitted=False, dry_run=False, refused=True, earcon=EarconType.TEST_FAILED,
        )
        return turn, {"review_outcome": {"refusal_code": code, "submitted": False, "dry_run": False, "spoken": spoken}}

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
