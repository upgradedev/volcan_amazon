"""Interfaces Layer: two HTTP surfaces over one application core.

1. **MCP surface** at ``POST /mcp`` and ``GET /mcp``: a hand-written Model
   Context Protocol server, revision 2025-11-25, Streamable HTTP transport,
   JSON-RPC 2.0 messages. Implemented in ``src/interfaces/mcp_protocol.py``;
   this module supplies the transport, the session and Origin checks, and the
   tool catalog. ``tools/list`` derives every ``inputSchema`` from the same
   pydantic models the REST surface validates against.

2. **REST surface** under ``/api/*``: ordinary JSON over HTTP for the web
   companion and for curl. It is not MCP and is not described as MCP.

Run locally, bound to loopback:

    python -m src.interfaces.mcp_server
    # then: python scripts/mcp_conformance.py http://127.0.0.1:8000/mcp
"""
import base64
import json
import os
import secrets
import time
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from src.application.accessibility_use_case import AccessibilityOrchestratorUseCase
from src.application.braille_diff_use_case import BrailleDiffUseCase
from src.application.digest_diff_use_case import DigestDiffUseCase
from src.application.ecosystem_companion_use_case import OrchestrateEcosystemCompanionUseCase
from src.application.governed_execution_use_case import GovernedExecutionUseCase
from src.application.sonify_event_use_case import SonifyEventUseCase
from src.application.voice_turn_use_case import VoiceTurnUseCase
from src.domain.approval_grant import ApprovalGrantIssuer
from src.domain.ast_completeness_checker import ASTGraphCompletenessChecker
from src.domain.governed_action import Principal
from src.domain.sonification import EarconType
from src.infrastructure.audit_repository import InMemoryAuditRepository
from src.infrastructure.bedrock_adapter import BedrockSynthesisAdapter
from src.infrastructure.dry_run_executor import DryRunExecutor
from src.infrastructure.git_adapter import LocalGitAdapter
from src.infrastructure.observability_harness import PrivateObservabilityHarness
from src.interfaces.mcp_protocol import (
    INVALID_REQUEST,
    PARSE_ERROR,
    PROTOCOL_VERSION,
    SERVER_NAME,
    SERVER_VERSION,
    SUPPORTED_PROTOCOL_VERSIONS,
    JsonRpcError,
    McpDispatcher,
    SessionRegistry,
    ToolDefinition,
    ToolRegistry,
    audio_block,
    json_block,
    text_block,
)
from src.interfaces.web_companion import load_companion_html

app = FastAPI(
    title="Volcan Accessible AI Agent Forge",
    description=(
        "MCP server (revision 2025-11-25, Streamable HTTP) at /mcp, plus a REST "
        "surface at /api for the web companion."
    ),
    version=SERVER_VERSION,
)

# --- Composition root -------------------------------------------------------

audit_repo = InMemoryAuditRepository()
bedrock_adapter = BedrockSynthesisAdapter()
git_adapter = LocalGitAdapter()
dry_run_executor = DryRunExecutor()
ast_checker = ASTGraphCompletenessChecker()

#: Signing secret for approval grants. Set VOLCAN_APPROVAL_SECRET to keep grants
#: valid across restarts; otherwise a fresh per-process secret is generated,
#: which invalidates outstanding grants on restart rather than accepting them.
_secret_env = os.getenv("VOLCAN_APPROVAL_SECRET")
grant_issuer = ApprovalGrantIssuer(
    _secret_env.encode("utf-8") if _secret_env and len(_secret_env) >= 16 else secrets.token_bytes(32)
)

digest_use_case = DigestDiffUseCase(bedrock_adapter)
sonify_use_case = SonifyEventUseCase()
ecosystem_use_case = OrchestrateEcosystemCompanionUseCase()
braille_use_case = BrailleDiffUseCase()
accessibility_use_case = AccessibilityOrchestratorUseCase()
governed_use_case = GovernedExecutionUseCase(dry_run_executor, audit_repo, grant_issuer)
voice_turn_use_case = VoiceTurnUseCase(digest_use_case, governed_use_case, sonify_use_case)

DEFAULT_ALLOWED_ORIGINS = ("http://127.0.0.1:8000", "http://localhost:8000")


def allowed_origins() -> set[str]:
    configured = os.getenv("VOLCAN_ALLOWED_ORIGINS")
    if configured:
        return {origin.strip() for origin in configured.split(",") if origin.strip()}
    return set(DEFAULT_ALLOWED_ORIGINS)


# --- DTOs -------------------------------------------------------------------

class DigestRequest(BaseModel):
    raw_diff: str = Field(..., description="Unified git patch content")
    level: int = Field(0, description="Digest detail level (0 executive, 1 file-by-file, 2 drill-down)")


class DrillDownRequest(BaseModel):
    raw_diff: str = Field(..., description="Unified git patch content")
    section_index: int = Field(0, description="0-indexed section of the patch to inspect")


class StageActionRequest(BaseModel):
    action_id: str = Field(..., description="Caller-chosen identifier for this staged action")
    action_type: str = Field("TERMINAL_COMMAND", description="Action class, used in the payload hash")
    command: str = Field(..., description="Command Volcan should plan; it is never executed")
    summary_spoken: str = Field(..., description="One sentence a voice assistant can read aloud")
    lease_sec: float = Field(300.0, description="Seconds before the approval grant expires")
    staged_by: str = Field("volcan-agent", description="Identifier of the agent staging the action")


class ConfirmActionRequest(BaseModel):
    action_id: str = Field(..., description="Identifier of the staged action to release")
    approval_grant: str = Field(..., description="The v1 HMAC grant returned when the action was staged")
    approver_id: str = Field("developer", description="Identifier of the human releasing the action")


class VoiceTurnRequest(BaseModel):
    session_id: str = Field(..., description="Conversation session identifier")
    user_id: str = Field(..., description="Speaking user identifier")
    repository: str = Field(..., description="Repository the turn is about")
    intent: str = Field(..., description="summarize_diff, stage_action, approve_action or reject_action")
    params: dict[str, Any] = Field(default_factory=dict, description="Intent-specific slots")


class PlayEarconRequest(BaseModel):
    earcon_type: str = Field(..., description=f"One of: {', '.join(e.value for e in EarconType)}")


class BrailleTranslateRequest(BaseModel):
    text: str = Field(..., description="ASCII text or code to translate into Unicode Braille")


class BrailleDiffRequest(BaseModel):
    raw_diff: str = Field(..., description="Unified git patch to format for a Braille display")


class SwitchPulseRequest(BaseModel):
    input_type: str = Field("SIP_AND_PUFF", description="SIP_AND_PUFF, SINGLE_BUTTON or FOOT_PEDAL")
    signal_strength: float = Field(1.0, description="Pressure or analog value between 0.0 and 1.0")
    duration_ms: int = Field(150, description="Pulse duration in milliseconds")
    is_long_press: bool = Field(False, description="Whether the pulse was held for dwell selection")


class HapticRequest(BaseModel):
    event_type: str = Field("TASK_COMPLETED", description="TASK_COMPLETED, SECURITY_FLAG or LEASE_TICK")


class AstCheckRequest(BaseModel):
    source_code: str = Field(..., description="Python source to parse and validate")


class BeeAnnotationRequest(BaseModel):
    speaker_id: str = Field("developer_voice_1", description="Speaker identifier")
    transcript: str = Field(..., description="Spoken transcript to attach to a review")
    pr_id: str = Field("PR-104", description="Target PR or commit identifier")


class FireTvSyncRequest(BaseModel):
    lease_id: str | None = Field(None, description="Active lease identifier")
    ttl_sec: int = Field(300, description="Seconds of lease remaining")
    security_flag: bool = Field(False, description="Whether the diff raised a security flag")
    dora_rating: str = Field("ELITE", description="DORA velocity tier label")


class RingPresenceRequest(BaseModel):
    sensor_zone: str = Field("Front Door", description="Presence sensor zone label")
    active_lease_id: str | None = Field(None, description="Active release lease identifier")


# --- Application operations shared by both surfaces -------------------------

async def op_digest(req: DigestRequest) -> dict[str, Any]:
    report = await digest_use_case.execute(req.raw_diff)
    cue, wav_bytes = sonify_use_case.execute(EarconType.DIFF_READY)
    return {
        "voice_summary": report.to_voice_summary(level=req.level),
        "synthesis_mode": report.synthesis_mode,
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
        "_wav": wav_bytes,
    }


async def op_drill_down(req: DrillDownRequest) -> dict[str, Any]:
    report = await digest_use_case.execute(req.raw_diff)
    if req.section_index < 0 or req.section_index >= len(report.sections):
        raise IndexError(
            f"Section index {req.section_index} is out of bounds; the patch has "
            f"{len(report.sections)} sections."
        )
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
        "_wav": wav_bytes,
    }


def op_stage_action(req: StageActionRequest) -> dict[str, Any]:
    ticket = governed_use_case.stage_action(
        req.action_id, req.action_type, req.command, req.summary_spoken, req.lease_sec,
        staged_by=Principal.agent(req.staged_by),
    )
    plan = dry_run_executor.plan(req.command)
    cue, wav_bytes = sonify_use_case.execute(EarconType.GOVERNANCE_CHALLENGE)
    return {
        "action_id": ticket.action.action_id,
        "state": ticket.action.state.value,
        "payload_hash": ticket.action.payload_hash,
        "approval_grant": ticket.grant,
        "expires_at_epoch": ticket.expires_at_epoch,
        "lease_sec": req.lease_sec,
        "plan": plan.to_dict(),
        "spoken_prompt": (
            f"Volcan staged action: {ticket.action.summary_spoken}. "
            "A human must approve it with the authorization grant before the lease expires."
        ),
        "earcon": {
            "type": cue.earcon_type.value,
            "wav_base64": base64.b64encode(wav_bytes).decode("ascii"),
        },
        "_wav": wav_bytes,
    }


async def op_confirm_action(req: ConfirmActionRequest) -> dict[str, Any]:
    outcome = await governed_use_case.confirm_and_execute(
        req.action_id, req.approval_grant, approver=Principal.human(req.approver_id),
    )
    earcon = EarconType.ACTION_COMMITTED if outcome.approved else EarconType.TEST_FAILED
    cue, wav_bytes = sonify_use_case.execute(earcon)
    return {
        "approved": outcome.approved,
        "status": "PLANNED" if outcome.approved else "REFUSED",
        "output": outcome.output,
        "refusal_code": outcome.refusal_code,
        "refusal_detail": outcome.refusal_detail,
        "spoken_text": outcome.spoken_reason if outcome.refused else outcome.output,
        "earcon": {
            "type": cue.earcon_type.value,
            "wav_base64": base64.b64encode(wav_bytes).decode("ascii"),
        },
        "_wav": wav_bytes,
    }


def op_audit_log() -> dict[str, Any]:
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
                "staged_by": r.staged_by,
                "approved_by": r.approved_by,
                "timestamp": r.timestamp,
            }
            for r in records
        ],
    }


# --- REST surface (not MCP) -------------------------------------------------

@app.get("/health")
async def health_check() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": SERVER_NAME,
        "version": SERVER_VERSION,
        "mcp": {
            "endpoint": "/mcp",
            "protocol_version": PROTOCOL_VERSION,
            "transport": "Streamable HTTP",
            "capabilities": ["tools"],
            "active_sessions": sessions.count,
        },
        "rest_prefix": "/api",
        "bedrock_credentials_present": bedrock_adapter.credentials_present(),
        "supported_earcons": [e.value for e in EarconType],
    }


@app.get("/api/audit_log")
async def rest_audit_log() -> dict[str, Any]:
    return op_audit_log()


@app.post("/api/digest_semantic_diff")
async def rest_digest(req: DigestRequest) -> dict[str, Any]:
    result = await op_digest(req)
    result.pop("_wav", None)
    return result


@app.post("/api/drill_down_section")
async def rest_drill_down(req: DrillDownRequest) -> dict[str, Any]:
    try:
        result = await op_drill_down(req)
    except IndexError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    result.pop("_wav", None)
    return result


@app.post("/api/stage_governed_action")
async def rest_stage_action(req: StageActionRequest) -> dict[str, Any]:
    result = op_stage_action(req)
    result.pop("_wav", None)
    return result


@app.post("/api/confirm_action")
async def rest_confirm_action(req: ConfirmActionRequest) -> dict[str, Any]:
    result = await op_confirm_action(req)
    result.pop("_wav", None)
    return result


@app.post("/api/play_earcon")
async def rest_play_earcon(req: PlayEarconRequest) -> Response:
    try:
        etype = EarconType(req.earcon_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Unknown earcon type: {req.earcon_type}") from exc
    _cue, wav_bytes = sonify_use_case.execute(etype)
    return Response(content=wav_bytes, media_type="audio/wav")


@app.post("/api/voice_turn")
async def rest_voice_turn(req: VoiceTurnRequest) -> dict[str, Any]:
    return await voice_turn_use_case.handle_turn(
        session_id=req.session_id,
        user_id=req.user_id,
        repo=req.repository,
        intent=req.intent,
        params=req.params,
    )


@app.post("/api/run_accessible_tests")
async def rest_run_tests() -> dict[str, Any]:
    passed, output = git_adapter.run_tests()
    cue_type = EarconType.TEST_PASSED if passed else EarconType.TEST_FAILED
    cue, wav_bytes = sonify_use_case.execute(cue_type)
    status_phrase = "All tests passed." if passed else "The test suite reported failures."
    return {
        "passed": passed,
        "spoken_text": f"{status_phrase} Processed workspace test execution.",
        "output_snippet": output[:300],
        "earcon": {
            "type": cue.earcon_type.value,
            "wav_base64": base64.b64encode(wav_bytes).decode("ascii"),
        },
    }


@app.post("/api/braille/translate_text")
async def rest_braille_translate(req: BrailleTranslateRequest) -> dict[str, Any]:
    return braille_use_case.translate_text(req.text)


@app.post("/api/braille/diff_digest")
async def rest_braille_diff(req: BrailleDiffRequest) -> dict[str, Any]:
    return braille_use_case.digest_to_braille(req.raw_diff)


@app.post("/api/accessibility/process_switch_pulse")
async def rest_switch_pulse(req: SwitchPulseRequest) -> dict[str, Any]:
    return accessibility_use_case.process_switch_signal(
        input_type_str=req.input_type,
        signal_strength=req.signal_strength,
        duration_ms=req.duration_ms,
        is_long_press=req.is_long_press,
    )


@app.post("/api/accessibility/get_haptic_profile")
async def rest_haptic_profile(req: HapticRequest) -> dict[str, Any]:
    return accessibility_use_case.generate_haptic_profile(req.event_type)


@app.post("/api/ast/check_completeness")
async def rest_ast_check(req: AstCheckRequest) -> dict[str, Any]:
    result = ast_checker.check_syntax_completeness(req.source_code)
    return {
        "is_valid_ast": result.is_valid_ast,
        "syntax_error_message": result.syntax_error_message,
        "node_count": result.node_count,
        "function_count": result.function_count,
        "class_count": result.class_count,
    }


@app.post("/api/companions/ingest_bee_annotation")
async def rest_bee_annotation(req: BeeAnnotationRequest) -> dict[str, Any]:
    return ecosystem_use_case.attach_bee_ambient_note(
        speaker_id=req.speaker_id, transcript=req.transcript, pr_id=req.pr_id,
    )


@app.post("/api/companions/sync_firetv_wallboard")
async def rest_firetv_sync(req: FireTvSyncRequest) -> dict[str, Any]:
    return ecosystem_use_case.sync_firetv_compatibility(
        lease_id=req.lease_id, ttl_sec=req.ttl_sec,
        security_flag=req.security_flag, dora_rating=req.dora_rating,
    )


@app.post("/api/companions/evaluate_ring_presence")
async def rest_ring_presence(req: RingPresenceRequest) -> dict[str, Any]:
    return ecosystem_use_case.evaluate_ring_presence(
        sensor_zone=req.sensor_zone, active_lease_id=req.active_lease_id,
    )


# --- MCP tool catalog -------------------------------------------------------

def _spoken_and_detail(spoken: str, detail: dict[str, Any], wav: bytes | None) -> list[dict[str, Any]]:
    """Spoken text first, then the earcon, then the machine-readable detail."""
    blocks: list[dict[str, Any]] = [text_block(spoken)]
    if wav is not None:
        blocks.append(audio_block(wav))
    blocks.append(json_block(detail))
    return blocks


async def tool_digest(req: DigestRequest) -> list[dict[str, Any]]:
    result = await op_digest(req)
    wav = result.pop("_wav")
    result.pop("earcon", None)
    return _spoken_and_detail(result["voice_summary"], result, wav)


async def tool_drill_down(req: DrillDownRequest) -> list[dict[str, Any]]:
    result = await op_drill_down(req)
    wav = result.pop("_wav")
    result.pop("earcon", None)
    return _spoken_and_detail(result["spoken_text"], result, wav)


async def tool_stage_action(req: StageActionRequest) -> list[dict[str, Any]]:
    result = op_stage_action(req)
    wav = result.pop("_wav")
    result.pop("earcon", None)
    return _spoken_and_detail(result["spoken_prompt"], result, wav)


async def tool_confirm_action(req: ConfirmActionRequest) -> list[dict[str, Any]]:
    result = await op_confirm_action(req)
    wav = result.pop("_wav")
    result.pop("earcon", None)
    return _spoken_and_detail(result["spoken_text"] or "", result, wav)


async def tool_play_earcon(req: PlayEarconRequest) -> list[dict[str, Any]]:
    etype = EarconType(req.earcon_type)  # ValueError becomes isError content
    cue, wav_bytes = sonify_use_case.execute(etype)
    return [audio_block(wav_bytes), text_block(cue.spoken_fallback)]


async def tool_voice_turn(req: VoiceTurnRequest) -> list[dict[str, Any]]:
    result = await voice_turn_use_case.handle_turn(
        session_id=req.session_id, user_id=req.user_id, repo=req.repository,
        intent=req.intent, params=req.params,
    )
    return [text_block(result.get("spoken_text", "")), json_block(result)]


async def tool_braille_translate(req: BrailleTranslateRequest) -> list[dict[str, Any]]:
    result = braille_use_case.translate_text(req.text)
    return [text_block(result["braille_unicode"]), json_block(result)]


async def tool_braille_diff(req: BrailleDiffRequest) -> list[dict[str, Any]]:
    result = braille_use_case.digest_to_braille(req.raw_diff)
    return [text_block(result["braille_summary"]), json_block(result)]


async def tool_switch_pulse(req: SwitchPulseRequest) -> list[dict[str, Any]]:
    result = accessibility_use_case.process_switch_signal(
        input_type_str=req.input_type, signal_strength=req.signal_strength,
        duration_ms=req.duration_ms, is_long_press=req.is_long_press,
    )
    return [text_block(result["description"]), json_block(result)]


async def tool_haptic_profile(req: HapticRequest) -> list[dict[str, Any]]:
    result = accessibility_use_case.generate_haptic_profile(req.event_type)
    return [text_block(result["visual_caption"]), json_block(result)]


async def tool_ast_check(req: AstCheckRequest) -> list[dict[str, Any]]:
    result = ast_checker.check_syntax_completeness(req.source_code)
    spoken = (
        f"Syntax tree parsed: {result.node_count} nodes, {result.function_count} functions, "
        f"{result.class_count} classes."
        if result.is_valid_ast
        else f"Source does not parse. {result.syntax_error_message}"
    )
    return [text_block(spoken), json_block({
        "is_valid_ast": result.is_valid_ast,
        "syntax_error_message": result.syntax_error_message,
        "node_count": result.node_count,
        "function_count": result.function_count,
        "class_count": result.class_count,
    })]


def build_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(ToolDefinition(
        name="digest_semantic_diff",
        title="Digest a patch into a spoken summary",
        description=(
            "Parse a unified git patch, flag security-sensitive changes and return a "
            "hierarchical spoken digest together with the DIFF_READY earcon as audio."
        ),
        input_model=DigestRequest, handler=tool_digest,
    ))
    registry.register(ToolDefinition(
        name="drill_down_section",
        title="Inspect one file section of a patch",
        description="Return a symbol-level spoken explanation of one section of a patch.",
        input_model=DrillDownRequest, handler=tool_drill_down,
    ))
    registry.register(ToolDefinition(
        name="stage_governed_action",
        title="Stage an action for human release",
        description=(
            "Stage a command behind a time-limited approval grant. The command is planned, "
            "never executed, and only a human principal can release it."
        ),
        input_model=StageActionRequest, handler=tool_stage_action,
    ))
    registry.register(ToolDefinition(
        name="confirm_governed_action",
        title="Release a staged action with a grant",
        description=(
            "Present an approval grant to release a staged action. Forged, replayed, expired "
            "or mismatched grants are refused with a reason."
        ),
        input_model=ConfirmActionRequest, handler=tool_confirm_action,
    ))
    registry.register(ToolDefinition(
        name="play_earcon",
        title="Synthesise an accessibility earcon",
        description=(
            "Return a 16-bit PCM WAV earcon as an MCP audio content block, so a client "
            "plays the cue rather than reading a description of it."
        ),
        input_model=PlayEarconRequest, handler=tool_play_earcon,
    ))
    registry.register(ToolDefinition(
        name="voice_turn",
        title="Handle one conversational turn",
        description="Run one multi-turn voice interaction: summarize, stage, approve or reject.",
        input_model=VoiceTurnRequest, handler=tool_voice_turn,
    ))
    registry.register(ToolDefinition(
        name="translate_text_to_braille",
        title="Translate text to Unicode Braille",
        description="Translate text or code into Unicode Braille patterns in the U+2800 block.",
        input_model=BrailleTranslateRequest, handler=tool_braille_translate,
    ))
    registry.register(ToolDefinition(
        name="braille_diff_digest",
        title="Format a patch for a Braille display",
        description="Format a unified patch with tactile add and remove markers for a Braille display.",
        input_model=BrailleDiffRequest, handler=tool_braille_diff,
    ))
    registry.register(ToolDefinition(
        name="process_switch_pulse",
        title="Resolve an adaptive switch pulse",
        description="Map a sip-and-puff, single-button or foot-pedal pulse to a navigation action.",
        input_model=SwitchPulseRequest, handler=tool_switch_pulse,
    ))
    registry.register(ToolDefinition(
        name="get_haptic_profile",
        title="Build a haptic cadence",
        description="Return a vibration cadence and a visual caption for Deaf and hard-of-hearing users.",
        input_model=HapticRequest, handler=tool_haptic_profile,
    ))
    registry.register(ToolDefinition(
        name="check_ast_completeness",
        title="Validate that Python source parses",
        description="Parse Python source and report node, function and class counts or the syntax error.",
        input_model=AstCheckRequest, handler=tool_ast_check,
    ))
    return registry


tool_registry = build_tool_registry()
sessions = SessionRegistry()
dispatcher = McpDispatcher(
    tool_registry,
    instructions=(
        "Volcan turns code review into sound and touch for blind and mobility-impaired "
        "developers. Call digest_semantic_diff first; it returns spoken text and an audio "
        "earcon. Commands are planned, never executed."
    ),
)


# --- MCP Streamable HTTP transport -----------------------------------------

MCP_ALLOW = "GET, POST, DELETE"


def _rpc_error(request_id: Any, code: int, message: str, data: Any = None, status: int = 200) -> JSONResponse:
    body = McpDispatcher.error_response(request_id, JsonRpcError(code, message, data))
    return JSONResponse(status_code=status, content=body, headers={"MCP-Protocol-Version": PROTOCOL_VERSION})


def _origin_refusal(request: Request) -> JSONResponse | None:
    """Rejects a present-but-unexpected Origin.

    An absent Origin is allowed: non-browser MCP clients and curl send none.
    The check exists to stop a hostile page in a browser from driving a server
    bound to loopback, which is the DNS-rebinding case the specification warns
    about.
    """
    origin = request.headers.get("origin")
    if origin is None:
        return None
    if origin in allowed_origins():
        return None
    return JSONResponse(
        status_code=403,
        content={
            "error": "origin_not_allowed",
            "detail": (
                f"Origin '{origin}' is not permitted. Set VOLCAN_ALLOWED_ORIGINS to allow it."
            ),
            "allowed": sorted(allowed_origins()),
        },
    )


def _session_refusal(request: Request) -> JSONResponse | None:
    """A session id this server never issued, or already terminated, is a 404."""
    session_id = request.headers.get("mcp-session-id")
    if session_id is None:
        return None
    if sessions.exists(session_id):
        return None
    return JSONResponse(
        status_code=404,
        content={"error": "unknown_session", "detail": "No such MCP session; run initialize again."},
    )


def _protocol_version_refusal(request: Request, method: str, request_id: Any) -> JSONResponse | None:
    """Every request after initialize must declare MCP-Protocol-Version."""
    if method == "initialize":
        return None
    declared = request.headers.get("mcp-protocol-version")
    if declared is None:
        return _rpc_error(
            request_id, INVALID_REQUEST,
            "Missing MCP-Protocol-Version header; it is required on every request after initialize.",
            {"expected": PROTOCOL_VERSION},
        )
    if declared not in SUPPORTED_PROTOCOL_VERSIONS:
        return _rpc_error(
            request_id, INVALID_REQUEST,
            f"Unsupported MCP-Protocol-Version '{declared}'.",
            {"supported": list(SUPPORTED_PROTOCOL_VERSIONS)},
        )
    return None


@app.api_route("/mcp", methods=["GET", "POST", "DELETE"], include_in_schema=True)
async def mcp_endpoint(request: Request) -> Response:
    """The single MCP endpoint of the Streamable HTTP transport.

    All three methods are bound to one route so that an unsupported method such
    as PUT receives a 405 whose Allow header lists every method this endpoint
    really accepts, rather than whichever route happened to be registered first.
    """
    if request.method == "POST":
        return await mcp_post(request)
    if request.method == "GET":
        return await mcp_get(request)
    return await mcp_delete(request)


async def mcp_post(request: Request) -> Response:
    refusal = _origin_refusal(request) or _session_refusal(request)
    if refusal is not None:
        return refusal

    raw = await request.body()
    try:
        message = json.loads(raw) if raw else None
    except json.JSONDecodeError as exc:
        return _rpc_error(None, PARSE_ERROR, f"Parse error: {exc.msg} at position {exc.pos}.")

    if message is None:
        return _rpc_error(None, INVALID_REQUEST, "Request body is empty.")

    request_id = message.get("id") if isinstance(message, dict) else None
    method = message.get("method") if isinstance(message, dict) else None

    if isinstance(method, str):
        version_refusal = _protocol_version_refusal(request, method, request_id)
        if version_refusal is not None:
            return version_refusal

    started = time.perf_counter()
    try:
        outcome = await dispatcher.dispatch(message)
    except JsonRpcError as exc:
        # JSON-RPC application errors travel as HTTP 200 with an error member;
        # HTTP status is reserved for transport-level problems.
        return _rpc_error(request_id, exc.code, exc.message, exc.data)

    elapsed_ms = (time.perf_counter() - started) * 1000.0

    if outcome.body is None:
        # A JSON-RPC notification gets no response body at all.
        return Response(status_code=202, headers={"MCP-Protocol-Version": PROTOCOL_VERSION})

    headers = {"MCP-Protocol-Version": outcome.negotiated_version}
    if outcome.is_initialize:
        headers["Mcp-Session-Id"] = sessions.create()

    if isinstance(method, str) and method == "tools/call":
        _emit_tool_metric(message, elapsed_ms)

    return JSONResponse(status_code=200, content=outcome.body, headers=headers)


def _emit_tool_metric(message: dict[str, Any], elapsed_ms: float) -> None:
    """Emits one genuinely measured CloudWatch EMF record per tool call."""
    tool_name = "unknown"
    params = message.get("params")
    if isinstance(params, dict) and isinstance(params.get("name"), str):
        tool_name = params["name"]
    harness = PrivateObservabilityHarness()
    harness.record_metric("McpToolDurationMs", round(elapsed_ms, 3))
    harness.add_audit_event(actor="mcp-client", action=f"tools/call:{tool_name}", details={})
    harness.flush()


async def mcp_get(request: Request) -> Response:
    """Opens the server-to-client SSE stream of the Streamable HTTP transport.

    This server has no long-lived server-initiated traffic to push, so the
    stream announces itself and closes rather than holding a socket open for a
    message that will never come. A client that wants request/response traffic
    uses POST.
    """
    refusal = _origin_refusal(request) or _session_refusal(request)
    if refusal is not None:
        return refusal

    session_id = request.headers.get("mcp-session-id")

    def event_stream():
        yield ": volcan mcp stream open\n\n"
        notice = {
            "jsonrpc": "2.0",
            "method": "notifications/message",
            "params": {
                "level": "info",
                "logger": SERVER_NAME,
                "data": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "session": session_id,
                    "note": (
                        "Stream opened. This server pushes no unsolicited messages; "
                        "send JSON-RPC requests to POST /mcp."
                    ),
                },
            },
        }
        yield f"event: message\ndata: {json.dumps(notice)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "MCP-Protocol-Version": PROTOCOL_VERSION,
            "X-Accel-Buffering": "no",
        },
    )


async def mcp_delete(request: Request) -> Response:
    """Terminates an MCP session, as the Streamable HTTP transport allows."""
    refusal = _origin_refusal(request)
    if refusal is not None:
        return refusal
    session_id = request.headers.get("mcp-session-id")
    if session_id is None:
        return JSONResponse(
            status_code=400,
            content={"error": "missing_session", "detail": "DELETE /mcp requires an Mcp-Session-Id header."},
        )
    if not sessions.terminate(session_id):
        return JSONResponse(
            status_code=404,
            content={"error": "unknown_session", "detail": "No such MCP session."},
        )
    return Response(status_code=204, headers={"MCP-Protocol-Version": PROTOCOL_VERSION})


# --- Web companion ----------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
@app.get("/demo", response_class=HTMLResponse)
async def demo_ui() -> HTMLResponse:
    """Serves docs/index.html, the single companion document in this repository."""
    return HTMLResponse(content=load_companion_html())


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
