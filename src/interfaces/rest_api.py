"""Interfaces Layer: the REST surface at /api.

This is ordinary JSON over HTTP for the web companion and for curl. It is not
the Model Context Protocol and is never described as MCP; the MCP surface lives
at /mcp and speaks JSON-RPC.
"""
import base64
from typing import Any

from fastapi import APIRouter, HTTPException, Response

from src.domain.sonification import EarconType
from src.interfaces.composition import (
    accessibility_use_case,
    ast_checker,
    bedrock_adapter,
    braille_use_case,
    dry_run_executor,
    ecosystem_use_case,
    github_adapter,
    review_dialogue_use_case,
    sessions,
    sonify_use_case,
    voice_turn_use_case,
)
from src.interfaces.dto import (
    AstCheckRequest,
    BeeAnnotationRequest,
    BrailleDiffRequest,
    BrailleTranslateRequest,
    ConfirmActionRequest,
    DigestRequest,
    DrillDownRequest,
    FireTvSyncRequest,
    HapticRequest,
    PlayEarconRequest,
    ReviewTurnRequest,
    RingPresenceRequest,
    StageActionRequest,
    SwitchPulseRequest,
    VoiceTurnRequest,
)
from src.interfaces.mcp_protocol import PROTOCOL_VERSION, SERVER_NAME, SERVER_VERSION
from src.interfaces.operations import (
    op_audit_log,
    op_confirm_action,
    op_digest,
    op_drill_down,
    op_stage_action,
)

router = APIRouter()


@router.get("/health")
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
        # One field, not two half-facts. ``bedrock_credentials_present`` used to
        # sit here on its own and was read as a promise that a model would
        # answer: credentials resolve on the development machine, where the SDK
        # is absent and no call can be attempted at all. The resolved capability
        # accounts for both, and the evidence stays beside it.
        "bedrock_model_path": bedrock_adapter.model_path_capability(),
        # Same shape, same reason: whether a confirmed review is sent or
        # recorded is decided by two facts, and the page prints the conclusion
        # the server drew from both rather than guessing from one.
        "github_review_path": github_adapter.capability(),
        "supported_earcons": [e.value for e in EarconType],
    }


@router.get("/api/audit_log")
async def rest_audit_log() -> dict[str, Any]:
    return op_audit_log()


@router.post("/api/digest_semantic_diff")
async def rest_digest(req: DigestRequest) -> dict[str, Any]:
    result = await op_digest(req)
    result.pop("_wav", None)
    return result


@router.post("/api/drill_down_section")
async def rest_drill_down(req: DrillDownRequest) -> dict[str, Any]:
    try:
        result = await op_drill_down(req)
    except IndexError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    result.pop("_wav", None)
    return result


@router.post("/api/stage_governed_action")
async def rest_stage_action(req: StageActionRequest) -> dict[str, Any]:
    result = op_stage_action(req)
    result.pop("_wav", None)
    return result


@router.post("/api/confirm_action")
async def rest_confirm_action(req: ConfirmActionRequest) -> dict[str, Any]:
    result = await op_confirm_action(req)
    result.pop("_wav", None)
    return result


@router.post("/api/play_earcon")
async def rest_play_earcon(req: PlayEarconRequest) -> Response:
    try:
        etype = EarconType(req.earcon_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Unknown earcon type: {req.earcon_type}") from exc
    _cue, wav_bytes = sonify_use_case.execute(etype)
    return Response(content=wav_bytes, media_type="audio/wav")


@router.post("/api/voice_turn")
async def rest_voice_turn(req: VoiceTurnRequest) -> dict[str, Any]:
    return await voice_turn_use_case.handle_turn(
        session_id=req.session_id,
        user_id=req.user_id,
        repo=req.repository,
        intent=req.intent,
        params=req.params,
    )


@router.post("/api/review/turn")
async def rest_review_turn(req: ReviewTurnRequest) -> dict[str, Any]:
    """One turn of the spoken review dialogue.

    The transcript came from the browser's SpeechRecognition API or from the
    keyboard; the server cannot tell and does not need to. The response reads
    back what was understood, says what happened, and carries the earcon when
    the turn has one.
    """
    result = await review_dialogue_use_case.handle_turn(
        session_id=req.session_id,
        user_id=req.user_id,
        transcript=req.transcript,
        pr_url=req.pr_url,
        raw_diff=req.raw_diff,
        approval_grant=req.approval_grant,
    )
    result.pop("_wav", None)
    return result


@router.post("/api/plan_accessible_test_run")
async def rest_plan_test_run() -> dict[str, Any]:
    """Plans the workspace test command and speaks the plan. Runs nothing.

    An earlier version of this route called subprocess to run pytest, with no
    body, no grant and no custody check, which contradicted the promise the rest
    of the product makes. It now returns what it would run, and the developer
    runs it.
    """
    plan = dry_run_executor.plan("pytest tests/unit")
    cue, wav_bytes = sonify_use_case.execute(EarconType.GOVERNANCE_CHALLENGE)
    return {
        "executed": plan.executed,
        "allowed": plan.allowed,
        "plan": plan.to_dict(),
        "spoken_text": plan.spoken,
        "earcon": {
            "type": cue.earcon_type.value,
            "spoken_fallback": cue.spoken_fallback,
            "wav_base64": base64.b64encode(wav_bytes).decode("ascii"),
        },
    }


@router.post("/api/braille/translate_text")
async def rest_braille_translate(req: BrailleTranslateRequest) -> dict[str, Any]:
    try:
        return braille_use_case.translate_text(req.text, req.fidelity)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/braille/diff_digest")
async def rest_braille_diff(req: BrailleDiffRequest) -> dict[str, Any]:
    try:
        return braille_use_case.digest_to_braille(req.raw_diff, req.fidelity)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/accessibility/process_switch_pulse")
async def rest_switch_pulse(req: SwitchPulseRequest) -> dict[str, Any]:
    return accessibility_use_case.process_switch_signal(
        input_type_str=req.input_type,
        signal_strength=req.signal_strength,
        duration_ms=req.duration_ms,
        is_long_press=req.is_long_press,
    )


@router.post("/api/accessibility/get_haptic_profile")
async def rest_haptic_profile(req: HapticRequest) -> dict[str, Any]:
    return accessibility_use_case.generate_haptic_profile(req.event_type)


@router.post("/api/ast/check_completeness")
async def rest_ast_check(req: AstCheckRequest) -> dict[str, Any]:
    result = ast_checker.check_syntax_completeness(req.source_code)
    return {
        "is_valid_ast": result.is_valid_ast,
        "syntax_error_message": result.syntax_error_message,
        "node_count": result.node_count,
        "function_count": result.function_count,
        "class_count": result.class_count,
    }


@router.post("/api/companions/ingest_bee_annotation")
async def rest_bee_annotation(req: BeeAnnotationRequest) -> dict[str, Any]:
    return ecosystem_use_case.attach_bee_ambient_note(
        speaker_id=req.speaker_id, transcript=req.transcript, pr_id=req.pr_id,
    )


@router.post("/api/companions/sync_firetv_wallboard")
async def rest_firetv_sync(req: FireTvSyncRequest) -> dict[str, Any]:
    return ecosystem_use_case.sync_firetv_compatibility(
        lease_id=req.lease_id, ttl_sec=req.ttl_sec,
        security_flag=req.security_flag, dora_rating=req.dora_rating,
    )


@router.post("/api/companions/evaluate_ring_presence")
async def rest_ring_presence(req: RingPresenceRequest) -> dict[str, Any]:
    return ecosystem_use_case.evaluate_ring_presence(
        sensor_zone=req.sensor_zone, active_lease_id=req.active_lease_id,
    )
