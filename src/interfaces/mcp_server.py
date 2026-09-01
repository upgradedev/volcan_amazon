"""Interfaces Layer: FastMCP / Streamable HTTP Server for Amazon Alexa+ and MCP Clients."""
import base64
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from src.application.digest_diff_use_case import DigestDiffUseCase
from src.application.governed_execution_use_case import GovernedExecutionUseCase
from src.application.sonify_event_use_case import SonifyEventUseCase
from src.application.voice_turn_use_case import VoiceTurnUseCase
from src.domain.sonification import EarconType
from src.infrastructure.audit_repository import InMemoryAuditRepository
from src.infrastructure.bedrock_adapter import BedrockSynthesisAdapter
from src.infrastructure.git_adapter import LocalGitAdapter
from src.interfaces.web_companion import COMPANION_HTML


app = FastAPI(
    title="Volcan Accessible AI Agent Forge",
    description="Streamable HTTP FastMCP Server for Amazon Alexa+ & Accessible AI Coding (Spec 2025-11-25+)",
    version="0.1.0",
)

# Composition Root
audit_repo = InMemoryAuditRepository()
bedrock_adapter = BedrockSynthesisAdapter()
git_adapter = LocalGitAdapter()

digest_use_case = DigestDiffUseCase(bedrock_adapter)
sonify_use_case = SonifyEventUseCase()


class ShellExecutor:
    async def run_command(self, command: str) -> str:
        # Sandboxed mock execution for demo safety
        return f"Executed command safely: '{command}'"


governed_use_case = GovernedExecutionUseCase(ShellExecutor(), audit_repo)
voice_turn_use_case = VoiceTurnUseCase(digest_use_case, governed_use_case, sonify_use_case)


# --- DTOs ---

class DigestRequest(BaseModel):
    raw_diff: str = Field(..., description="Unified git patch content")
    level: int = Field(0, description="Digest detail level (0: Executive, 1: File-by-file, 2: Deep drill-down)")


class DrillDownRequest(BaseModel):
    raw_diff: str
    section_index: int = Field(0, description="0-indexed section to inspect")


class StageActionRequest(BaseModel):
    action_id: str
    action_type: str = "TERMINAL_COMMAND"
    command: str
    summary_spoken: str
    lease_sec: float = 300.0


class ConfirmActionRequest(BaseModel):
    action_id: str
    voice_token: str


class VoiceTurnRequest(BaseModel):
    session_id: str
    user_id: str
    repository: str
    intent: str
    params: Dict[str, Any] = Field(default_factory=dict)


class PlayEarconRequest(BaseModel):
    earcon_type: str


# --- Endpoints ---

@app.get("/", response_class=HTMLResponse)
@app.get("/demo", response_class=HTMLResponse)
async def demo_ui() -> str:
    """Zero-setup interactive web companion for judges and developers."""
    return COMPANION_HTML


@app.get("/health")
async def health_check() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": "volcan-accessible-forge",
        "mcp_spec": "2025-11-25",
        "transport": "Streamable HTTP",
        "supported_earcons": [e.value for e in EarconType],
    }


@app.get("/mcp/resources/audit_log")
async def get_audit_log_resource() -> Dict[str, Any]:
    """MCP Resource: Immutable audit trail of voice-governed actions."""
    records = audit_repo.list_records()
    return {
        "uri": "volcan://governance/audit_log",
        "mimeType": "application/json",
        "total_records": len(records),
        "records": [
            {
                "id": r.record_id,
                "action": r.action_id,
                "command": r.command,
                "payload_hash": r.payload_hash,
                "state": r.state.value,
                "timestamp": r.timestamp,
            }
            for r in records
        ],
    }


@app.post("/mcp/tools/digest_semantic_diff")
async def digest_semantic_diff(req: DigestRequest) -> Dict[str, Any]:
    """MCP Tool: Convert raw git diff into multi-level spoken semantic summaries."""
    report = await digest_use_case.execute(req.raw_diff)
    cue, wav_bytes = sonify_use_case.execute(EarconType.DIFF_READY)
    return {
        "voice_summary": report.to_voice_summary(level=req.level),
        "total_files": report.total_files_changed,
        "insertions": report.total_insertions,
        "deletions": report.total_deletions,
        "category_breakdown": report.category_breakdown,
        "critical_findings": report.critical_findings,
        "earcon": {
            "type": cue.earcon_type.value,
            "spoken_fallback": cue.spoken_fallback,
            "wav_base64": base64.b64encode(wav_bytes).decode("ascii"),
        },
    }


@app.post("/mcp/tools/drill_down_section")
async def drill_down_section(req: DrillDownRequest) -> Dict[str, Any]:
    """MCP Tool: Deep drill-down into a specific file section of the patch."""
    report = await digest_use_case.execute(req.raw_diff)
    if req.section_index < 0 or req.section_index >= len(report.sections):
        raise HTTPException(status_code=404, detail="Section index out of bounds.")
    
    sec = report.sections[req.section_index]
    cue, wav_bytes = sonify_use_case.execute(EarconType.DRILL_DOWN_OPENED)
    spoken = (
        f"Inspecting {sec.file_path}. Category: {sec.category.value}. "
        f"Significance is {sec.significance.value}. {sec.summary_spoken} "
        f"(Added {sec.added_count} lines, removed {sec.removed_count} lines)."
    )
    if sec.security_flags:
        spoken += f" Security alert: Flagged for {', '.join(sec.security_flags)}."

    return {
        "spoken_text": spoken,
        "file_path": sec.file_path,
        "category": sec.category.value,
        "significance": sec.significance.value,
        "security_flags": sec.security_flags,
        "earcon": {
            "type": cue.earcon_type.value,
            "wav_base64": base64.b64encode(wav_bytes).decode("ascii"),
        },
    }


@app.post("/mcp/tools/stage_governed_action")
async def stage_governed_action(req: StageActionRequest) -> Dict[str, Any]:
    """MCP Tool: Stage a voice-governed action requiring dual-custody confirmation."""
    action = governed_use_case.stage_action(
        req.action_id, req.action_type, req.command, req.summary_spoken, req.lease_sec
    )
    cue, wav_bytes = sonify_use_case.execute(EarconType.GOVERNANCE_CHALLENGE)
    return {
        "action_id": action.action_id,
        "state": action.state.value,
        "payload_hash": action.payload_hash,
        "spoken_prompt": (
            f"Volcan staged action: {action.summary_spoken}. "
            f"Say 'Confirm action' with your voice authorization token."
        ),
        "earcon": {
            "type": cue.earcon_type.value,
            "wav_base64": base64.b64encode(wav_bytes).decode("ascii"),
        },
    }


@app.post("/mcp/tools/confirm_action")
async def confirm_action(req: ConfirmActionRequest) -> Dict[str, Any]:
    """MCP Tool: Confirm and execute a staged action with cryptographic token."""
    result = await governed_use_case.confirm_and_execute(req.action_id, req.voice_token)
    if result is None:
        raise HTTPException(status_code=400, detail="Action not found, expired, or already finalized.")
    cue, wav_bytes = sonify_use_case.execute(EarconType.ACTION_COMMITTED)
    return {
        "status": "EXECUTED",
        "output": result,
        "earcon": {
            "type": cue.earcon_type.value,
            "wav_base64": base64.b64encode(wav_bytes).decode("ascii"),
        },
    }


@app.post("/mcp/tools/play_earcon")
async def play_earcon(req: PlayEarconRequest):
    """MCP Tool: Return binary audio/wav stream for a given EarconType."""
    try:
        etype = EarconType(req.earcon_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown earcon type: {req.earcon_type}")
    
    cue, wav_bytes = sonify_use_case.execute(etype)
    return Response(content=wav_bytes, media_type="audio/wav")


@app.post("/mcp/tools/voice_turn")
async def handle_voice_turn(req: VoiceTurnRequest) -> Dict[str, Any]:
    """MCP Tool: Process full conversational turn for Alexa+ multi-modal skill."""
    return await voice_turn_use_case.handle_turn(
        session_id=req.session_id,
        user_id=req.user_id,
        repo=req.repository,
        intent=req.intent,
        params=req.params,
    )


@app.post("/mcp/tools/run_accessible_tests")
async def run_accessible_tests() -> Dict[str, Any]:
    """MCP Tool: Run local test suite and convert terminal output to spoken digest."""
    passed, output = git_adapter.run_tests()
    cue_type = EarconType.TEST_PASSED if passed else EarconType.TEST_FAILED
    cue, wav_bytes = sonify_use_case.execute(cue_type)
    
    status_phrase = "All tests passed successfully." if passed else "Test suite failed with errors."
    spoken = f"{status_phrase} Processed workspace test execution."
    return {
        "passed": passed,
        "spoken_text": spoken,
        "output_snippet": output[:300],
        "earcon": {
            "type": cue.earcon_type.value,
            "wav_base64": base64.b64encode(wav_bytes).decode("ascii"),
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
