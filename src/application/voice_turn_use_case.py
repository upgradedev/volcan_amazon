"""Use Case: Conversational Turn Orchestrator for Alexa+."""
from typing import Any, Dict, Optional
from src.application.digest_diff_use_case import DigestDiffUseCase
from src.application.governed_execution_use_case import GovernedExecutionUseCase
from src.application.sonify_event_use_case import SonifyEventUseCase
from src.domain.sonification import EarconType
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
        self._sessions: Dict[str, VoiceSessionContext] = {}

    def get_or_create_session(self, session_id: str, user_id: str, repo: str) -> VoiceSessionContext:
        if session_id not in self._sessions:
            self._sessions[session_id] = VoiceSessionContext(session_id, user_id, repo)
        return self._sessions[session_id]

    async def handle_turn(
        self, session_id: str, user_id: str, repo: str, intent: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        session = self.get_or_create_session(session_id, user_id, repo)
        session.record_turn("user", f"Intent: {intent}, Params: {params}")

        if intent == "summarize_diff":
            raw_diff = params.get("raw_diff", "")
            report = await self._digest.execute(raw_diff)
            level = params.get("level", 0)
            voice_text = report.to_voice_summary(level=level)
            cue, wav_bytes = self._sonify.execute(EarconType.DIFF_READY)
            session.record_turn("volcan", voice_text)
            return {
                "spoken_text": voice_text,
                "earcon_type": cue.earcon_type.value,
                "earcon_wav_base64_len": len(wav_bytes),
                "total_files": report.total_files_changed,
                "critical_findings": report.critical_findings,
                "apl_card": {
                    "title": f"Volcan Semantic Diff — {repo}",
                    "primary_text": voice_text,
                    "metrics": f"+{report.total_insertions} / -{report.total_deletions} lines across {report.total_files_changed} files",
                },
            }

        elif intent == "stage_action":
            action_id = params.get("action_id", "act-default")
            action_type = params.get("action_type", "TERMINAL_COMMAND")
            command = params.get("command", "")
            summary = params.get("summary_spoken", "")
            action = self._governed.stage_action(action_id, action_type, command, summary)
            session.staged_action_id = action_id
            cue, _ = self._sonify.execute(EarconType.GOVERNANCE_CHALLENGE)
            spoken = f"Volcan staged action: {summary}. Say 'Approve action' or 'Reject' to proceed."
            session.record_turn("volcan", spoken)
            return {
                "spoken_text": spoken,
                "action_id": action.action_id,
                "payload_hash": action.payload_hash,
                "earcon_type": cue.earcon_type.value,
                "state": action.state.value,
            }

        elif intent == "approve_action":
            action_id = params.get("action_id") or session.staged_action_id
            voice_token = params.get("voice_token", "VOICE_AUTHENTICATED")
            if not action_id:
                spoken = "There is no pending action staged in your current session."
                return {"spoken_text": spoken, "error": True}
            result = await self._governed.confirm_and_execute(action_id, voice_token)
            if result is None:
                spoken = "Authorization failed. The action was already processed or has expired."
                cue, _ = self._sonify.execute(EarconType.TEST_FAILED)
                return {"spoken_text": spoken, "error": True, "earcon_type": cue.earcon_type.value}
            cue, _ = self._sonify.execute(EarconType.ACTION_COMMITTED)
            spoken = f"Action confirmed and executed successfully. Output summary: {result[:100]}"
            session.record_turn("volcan", spoken)
            return {
                "spoken_text": spoken,
                "output": result,
                "earcon_type": cue.earcon_type.value,
                "status": "EXECUTED",
            }

        elif intent == "reject_action":
            action_id = params.get("action_id") or session.staged_action_id
            if action_id:
                self._governed.reject_action(action_id)
            spoken = "The staged action was cancelled and discarded."
            session.record_turn("volcan", spoken)
            return {"spoken_text": spoken, "status": "REJECTED"}

        else:
            spoken = "Volcan is ready. You can ask to summarize the workspace diff or review staged actions."
            return {"spoken_text": spoken}
