"""Use Case: conversational turn orchestrator for the voice experience."""
from typing import Any

from src.application.digest_diff_use_case import DigestDiffUseCase
from src.application.governed_execution_use_case import GovernedExecutionUseCase
from src.application.sonify_event_use_case import SonifyEventUseCase
from src.domain.governed_action import Principal
from src.domain.sonification import EarconType, earcon_for_report
from src.domain.voice_session import VoiceSessionContext


class VoiceTurnUseCase:
    def __init__(
        self,
        digest_use_case: DigestDiffUseCase,
        governed_use_case: GovernedExecutionUseCase,
        sonify_use_case: SonifyEventUseCase,
    ):
        self._digest = digest_use_case
        self._governed = governed_use_case
        self._sonify = sonify_use_case
        self._sessions: dict[str, VoiceSessionContext] = {}

    def get_or_create_session(self, session_id: str, user_id: str, repo: str) -> VoiceSessionContext:
        if session_id not in self._sessions:
            self._sessions[session_id] = VoiceSessionContext(session_id, user_id, repo)
        return self._sessions[session_id]

    async def handle_turn(
        self, session_id: str, user_id: str, repo: str, intent: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        session = self.get_or_create_session(session_id, user_id, repo)
        session.record_turn("user", f"Intent: {intent}, Params: {params}")

        if intent == "summarize_diff":
            return await self._summarize(session, repo, params)
        if intent == "stage_action":
            return self._stage(session, params)
        if intent == "approve_action":
            return await self._approve(session, user_id, params)
        if intent == "reject_action":
            return self._reject(session, params)

        return {
            "spoken_text": (
                "Volcan is ready. You can ask to summarize the workspace diff "
                "or review staged actions."
            )
        }

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

    def _stage(self, session, params: dict[str, Any]) -> dict[str, Any]:
        action_id = params.get("action_id", "act-default")
        ticket = self._governed.stage_action(
            action_id,
            params.get("action_type", "TERMINAL_COMMAND"),
            params.get("command", ""),
            params.get("summary_spoken", ""),
            staged_by=Principal.agent(params.get("staged_by", "volcan-agent")),
        )
        session.staged_action_id = action_id
        cue, _ = self._sonify.execute(EarconType.GOVERNANCE_CHALLENGE)
        spoken = (
            f"Volcan staged action: {ticket.action.summary_spoken}. "
            "Say 'Approve action' with the authorization grant, or 'Reject' to discard it."
        )
        session.record_turn("volcan", spoken)
        return {
            "spoken_text": spoken,
            "action_id": ticket.action.action_id,
            "payload_hash": ticket.action.payload_hash,
            "approval_grant": ticket.grant,
            "expires_at_epoch": ticket.expires_at_epoch,
            "earcon_type": cue.earcon_type.value,
            "state": ticket.action.state.value,
        }

    async def _approve(self, session, user_id: str, params: dict[str, Any]) -> dict[str, Any]:
        action_id = params.get("action_id") or session.staged_action_id
        if not action_id:
            return {
                "spoken_text": "There is no pending action staged in your current session.",
                "error": True,
            }

        outcome = await self._governed.confirm_and_execute(
            action_id,
            params.get("approval_grant", ""),
            approver=Principal.human(params.get("approver_id", user_id)),
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
        session.record_turn("volcan", spoken)
        return {
            "spoken_text": spoken,
            "output": outcome.output,
            "earcon_type": cue.earcon_type.value,
            "status": "PLANNED",
        }

    def _reject(self, session, params: dict[str, Any]) -> dict[str, Any]:
        action_id = params.get("action_id") or session.staged_action_id
        if action_id:
            self._governed.reject_action(action_id)
        spoken = "The staged action was cancelled and discarded."
        session.record_turn("volcan", spoken)
        return {"spoken_text": spoken, "status": "REJECTED"}
