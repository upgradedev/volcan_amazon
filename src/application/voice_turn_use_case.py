"""Use Case: conversational turn orchestrator for the voice experience."""
from typing import Any

from src.application.digest_diff_use_case import DigestDiffUseCase
from src.application.durable_state import (
    SessionOwnerMismatch,
    VoiceSessionState,
    voice_action_namespace,
)
from src.application.governed_execution_use_case import GovernedExecutionUseCase
from src.application.public_audit import ANONYMOUS_VOICE_OWNER
from src.application.review_authorization import (
    ReviewAuthorizationError,
    current_review_principal,
)
from src.application.sonify_event_use_case import SonifyEventUseCase
from src.domain.governed_action import ActionState, Principal
from src.domain.sonification import EarconType, earcon_for_report
from src.domain.voice_session import VoiceSessionContext


class VoiceTurnUseCase:
    def __init__(
        self,
        digest_use_case: DigestDiffUseCase,
        governed_use_case: GovernedExecutionUseCase,
        sonify_use_case: SonifyEventUseCase,
        state_store: Any | None = None,
    ):
        self._digest = digest_use_case
        self._governed = governed_use_case
        self._sonify = sonify_use_case
        self._state_store = state_store
        self._sessions: dict[str, VoiceSessionContext] = {}

    def get_or_create_session(self, session_id: str, user_id: str, repo: str) -> VoiceSessionContext:
        if session_id not in self._sessions:
            self._sessions[session_id] = VoiceSessionContext(session_id, user_id, repo)
        return self._sessions[session_id]

    async def handle_turn(
        self, session_id: str, user_id: str, repo: str, intent: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        revision = 0
        approver_id = params.get("approver_id", user_id)
        if self._state_store is not None:
            principal = current_review_principal.get()
            if principal is None:
                # No roster credential: the same simulated flow a local run
                # offers, planned and never run, owned by one fixed anonymous
                # owner that no roster identity can equal (the roster refuses
                # ":"). Sessions and action namespaces are keyed by owner, so
                # an anonymous caller can never reach a reviewer's session.
                user_id = ANONYMOUS_VOICE_OWNER
            else:
                repository = repo.strip().lower()
                if repository not in principal.repositories:
                    raise ReviewAuthorizationError(
                        "REPOSITORY_NOT_ALLOWED",
                        403,
                        "This reviewer may not access that repository.",
                    )
                # A JSON user_id is display input, never durable ownership. The
                # request-scoped Bearer principal owns the session and its actions.
                user_id = principal.identity
                approver_id = principal.identity
        if self._state_store is None:
            session = self.get_or_create_session(session_id, user_id, repo)
        else:
            stored = self._state_store.load_voice(session_id, user_id, repo)
            if stored is None:
                session = VoiceSessionContext(session_id, user_id, repo)
            else:
                revision = stored.revision
                saved = stored.value
                if saved.owner != user_id or saved.repository != repo:
                    raise SessionOwnerMismatch(
                        "This voice session belongs to a different user or repository."
                    )
                session = saved.session
        session.record_turn("user", f"Intent: {intent}, Params: {params}")
        new_action = None
        action_namespace = voice_action_namespace(user_id, repo, session_id)

        if intent == "summarize_diff":
            result = await self._summarize(session, repo, params)
        elif intent == "stage_action":
            result, new_action = self._stage(session, repo, action_namespace, params)
        elif intent == "approve_action":
            result = await self._approve(session, approver_id, action_namespace, params)
        elif intent == "reject_action":
            result = self._reject(session, action_namespace, params)
        else:
            result = {
                "spoken_text": (
                    "Volcan is ready. You can ask to summarize the workspace diff "
                    "or review staged actions."
                )
            }

        if self._state_store is not None:
            saved = VoiceSessionState(session=session, owner=user_id, repository=repo)
            if new_action is not None:
                self._state_store.save_voice_with_action(
                    saved,
                    revision,
                    action_namespace,
                    new_action,
                )
            else:
                self._state_store.save_voice(saved, expected_revision=revision)
        return result

    async def _summarize(self, session, repo: str, params: dict[str, Any]) -> dict[str, Any]:
        report = await self._digest.execute(params.get("raw_diff", ""))
        level = params.get("level", 0)
        voice_text = report.to_voice_summary(level=level)
        # Same selection as the REST and MCP digests. The voice surface is the
        # one where the cue matters most, because it arrives before the words.
        cue, wav_bytes = self._sonify.execute(earcon_for_report(report))
        session.record_turn("volcan", voice_text)
        return {
            "spoken_text": voice_text,
            "synthesis_mode": report.synthesis_mode,
            "earcon_type": cue.earcon_type.value,
            "earcon_wav_bytes": len(wav_bytes),
            "total_files": report.total_files_changed,
            "critical_findings": report.critical_findings,
            "apl_card": {
                "title": f"Volcan Semantic Diff: {repo}",
                "primary_text": voice_text,
                "metrics": (
                    f"+{report.total_insertions} / -{report.total_deletions} lines "
                    f"across {report.total_files_changed} files"
                ),
            },
        }

    def _stage(
        self,
        session: VoiceSessionContext,
        repo: str,
        action_namespace: str,
        params: dict[str, Any],
    ) -> tuple[dict[str, Any], Any | None]:
        action_id = params.get("action_id", "act-default")
        action_type = params.get("action_type", "TERMINAL_COMMAND")
        command = params.get("command", "")
        existing = (
            self._governed.get_action(session.staged_action_id, action_namespace)
            if session.staged_action_id else None
        )
        if existing is not None and existing.state.value != "PENDING_APPROVAL":
            # The action may have been finalized before the session checkpoint
            # response was saved. The durable action is authoritative.
            session.staged_action_id = None
            session.staged_action_grant = None
            existing = None
        if existing is not None:
            same = (
                existing.action_id == action_id
                and existing.action_type == action_type
                and existing.command_or_path == command
                and existing.state.value == "PENDING_APPROVAL"
                and session.staged_action_grant
            )
            if same:
                return self._stage_result(session, existing, session.staged_action_grant), None
            spoken = "A different action is already staged. Reject it before staging another."
            session.record_turn("volcan", spoken)
            return {"spoken_text": spoken, "error": True, "state": existing.state.value}, None
        ticket = self._governed.stage_action(
            action_id,
            action_type,
            command,
            params.get("summary_spoken", ""),
            staged_by=Principal.agent(params.get("staged_by", "volcan-agent")),
            persist=False,
            audit_scope=f"voice-session:{action_namespace}",
            action_namespace=action_namespace,
        )
        session.staged_action_id = action_id
        session.staged_action_grant = ticket.grant
        return self._stage_result(session, ticket.action, ticket.grant), ticket.action

    def _stage_result(
        self, session: VoiceSessionContext, action: Any, grant: str
    ) -> dict[str, Any]:
        cue, _ = self._sonify.execute(EarconType.GOVERNANCE_CHALLENGE)
        spoken = (
            f"Volcan staged action: {action.summary_spoken}. "
            "Say 'Approve action' with the authorization grant, or 'Reject' to discard it."
        )
        session.record_turn("volcan", spoken)
        return {
            "spoken_text": spoken,
            "action_id": action.action_id,
            "payload_hash": action.payload_hash,
            "approval_grant": grant,
            "expires_at_epoch": action.expires_at_epoch,
            "earcon_type": cue.earcon_type.value,
            "state": action.state.value,
        }

    async def _approve(
        self,
        session: VoiceSessionContext,
        approver_id: str,
        action_namespace: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        requested = params.get("action_id")
        if requested and requested != session.staged_action_id:
            return {
                "spoken_text": "That action does not belong to this voice session.",
                "error": True,
                "refusal_code": "SESSION_ACTION_MISMATCH",
                "status": "REFUSED",
            }
        action_id = session.staged_action_id
        if not action_id:
            return {
                "spoken_text": "There is no pending action staged in your current session.",
                "error": True,
            }

        outcome = await self._governed.confirm_and_execute(
            action_id,
            params.get("approval_grant", ""),
            approver=Principal.human(approver_id),
            action_namespace=action_namespace,
        )
        if outcome.refused:
            cue, _ = self._sonify.execute(EarconType.TEST_FAILED)
            session.record_turn("volcan", outcome.spoken_reason)
            return {
                "spoken_text": f"Authorization refused. {outcome.spoken_reason}",
                "error": True,
                "refusal_code": outcome.refusal_code,
                "refusal_detail": outcome.refusal_detail,
                "earcon_type": cue.earcon_type.value,
                "status": "REFUSED",
            }

        cue, _ = self._sonify.execute(EarconType.ACTION_COMMITTED)
        spoken = f"Grant accepted. {outcome.output}"
        session.staged_action_id = None
        session.staged_action_grant = None
        session.record_turn("volcan", spoken)
        return {
            "spoken_text": spoken,
            "output": outcome.output,
            "earcon_type": cue.earcon_type.value,
            "status": ActionState.RELEASED_NOT_RUN.value,
        }

    def _reject(
        self,
        session: VoiceSessionContext,
        action_namespace: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        requested = params.get("action_id")
        if requested and requested != session.staged_action_id:
            spoken = "That action does not belong to this voice session."
            session.record_turn("volcan", spoken)
            return {
                "spoken_text": spoken,
                "error": True,
                "refusal_code": "SESSION_ACTION_MISMATCH",
                "status": "REFUSED",
            }
        action_id = session.staged_action_id
        if action_id:
            rejected = self._governed.reject_action(action_id, action_namespace)
            if rejected:
                session.staged_action_id = None
                session.staged_action_grant = None
        spoken = "The staged action was cancelled and discarded."
        session.record_turn("volcan", spoken)
        return {"spoken_text": spoken, "status": "REJECTED"}
