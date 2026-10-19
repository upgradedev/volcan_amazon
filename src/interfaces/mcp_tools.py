"""Interfaces Layer: the MCP tool catalog.

Each entry pairs a pydantic request model with an async handler that returns
MCP content blocks. The model supplies ``inputSchema`` through
``ToolDefinition.to_catalog_entry``, so a renamed field changes the published
schema in the same commit that changes the parsing code.

Earcons are returned as audio content blocks rather than described in text. A
blind reviewer hears the cue; a client that only renders text still gets the
spoken fallback in the block beside it.

The first text block of the digest, drill-down and review-turn tools is the
``*_for_speech`` form of the sentence: code operators named ("not equals" for
``!=``) and Markdown removed. A voice client reads that block aloud, and a
voice that drops or slurs ``!=`` turns the finding into its opposite. The
literal code stays in the JSON detail block (``voice_summary``,
``spoken_text``, ``readback`` and ``spoken``) for a client that shows it.

Three tools also publish an ``outputSchema`` and return ``structuredContent``:
``digest_semantic_diff``, ``drill_down_section`` and ``review_dialogue_turn``.
The structured result is the same object as the JSON text block, which stays
for clients that predate the field, and the speech text stays the first block.
``review_dialogue_turn`` links the ui:// review card through ``_meta.ui``.
"""
from typing import Any

from src.application.review_card import REVIEW_CARD_URI
from src.domain.sonification import EarconType
from src.interfaces.composition import (
    accessibility_use_case,
    ast_checker,
    braille_use_case,
    review_dialogue_use_case,
    sonify_use_case,
    voice_turn_use_case,
)
from src.interfaces.dto import (
    AstCheckRequest,
    BrailleDiffRequest,
    BrailleTranslateRequest,
    ConfirmActionRequest,
    DigestRequest,
    DigestResult,
    DrillDownRequest,
    DrillDownResult,
    HapticRequest,
    PlayEarconRequest,
    ReviewTurnRequest,
    ReviewTurnResult,
    StageActionRequest,
    SwitchPulseRequest,
    VoiceTurnRequest,
)
from src.interfaces.mcp_protocol import (
    ResourceRegistry,
    ToolDefinition,
    ToolOutput,
    ToolRegistry,
    audio_block,
    json_block,
    text_block,
)
from src.interfaces.operations import (
    op_confirm_action,
    op_digest,
    op_drill_down,
    op_stage_action,
)
from src.interfaces.review_card_view import review_card_resource


def _spoken_and_detail(spoken: str, detail: dict[str, Any], wav: bytes | None) -> list[dict[str, Any]]:
    """Spoken text first, then the earcon, then the machine-readable detail."""
    blocks: list[dict[str, Any]] = [text_block(spoken)]
    if wav is not None:
        blocks.append(audio_block(wav))
    blocks.append(json_block(detail))
    return blocks


def _structured(spoken: str, detail: dict[str, Any], wav: bytes | None) -> ToolOutput:
    """The same blocks as ``_spoken_and_detail``, plus ``detail`` as structuredContent."""
    return ToolOutput(content=_spoken_and_detail(spoken, detail, wav), structured=detail)


async def tool_digest(req: DigestRequest) -> ToolOutput:
    result = await op_digest(req)
    wav = result.pop("_wav")
    result.pop("earcon", None)
    return _structured(result["voice_summary_for_speech"], result, wav)


async def tool_drill_down(req: DrillDownRequest) -> ToolOutput:
    result = await op_drill_down(req)
    wav = result.pop("_wav")
    result.pop("earcon", None)
    return _structured(result["spoken_text_for_speech"], result, wav)


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


async def tool_review_turn(req: ReviewTurnRequest) -> ToolOutput:
    """Readback first, then the answer, then the cue, then the detail.

    The readback precedes the answer in the text block for the same reason the
    earcon precedes the sentence: a listener who is told what was understood
    before hearing the consequence can interrupt a misheard command.
    """
    result = await review_dialogue_use_case.handle_turn(
        session_id=req.session_id, user_id=req.user_id, transcript=req.transcript,
        pr_url=req.pr_url, raw_diff=req.raw_diff, approval_grant=req.approval_grant,
    )
    wav = result.pop("_wav", None)
    result.pop("earcon", None)
    spoken = f"{result['readback_for_speech']} {result['spoken_for_speech']}".strip()
    return _structured(spoken, result, wav)


async def tool_braille_translate(req: BrailleTranslateRequest) -> list[dict[str, Any]]:
    result = braille_use_case.translate_text(req.text, req.fidelity)
    return [text_block(result["braille_unicode"]), json_block(result)]


async def tool_braille_diff(req: BrailleDiffRequest) -> list[dict[str, Any]]:
    result = braille_use_case.digest_to_braille(req.raw_diff, req.fidelity)
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
            "hierarchical spoken digest together with an earcon as audio. The earcon "
            "encodes the verdict: the falling SECURITY_FINDING cue when the patch "
            "carries a security finding, the rising DIFF_READY cue when it does not."
        ),
        input_model=DigestRequest, handler=tool_digest, output_model=DigestResult,
    ))
    registry.register(ToolDefinition(
        name="drill_down_section",
        title="Inspect one file section of a patch",
        description=(
            "Return a spoken explanation of one file section of a patch: the local rules' "
            "finding first, then Claude on Amazon Bedrock's answer about that file alone when "
            "a model answers (model_answered names it, and the coverage fields say how much "
            "of the file it read), or the reason none did. The falling SECURITY_FINDING "
            "earcon plays when that section is flagged."
        ),
        input_model=DrillDownRequest, handler=tool_drill_down, output_model=DrillDownResult,
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
        name="review_dialogue_turn",
        title="Converse about a pull request and submit a governed review",
        description=(
            "One turn of a spoken code review. Send what the developer said: open a pull request "
            "by URL (a live unauthenticated GitHub read) or open a pasted patch; then summary, "
            "file by file, what changed in <file>, next, previous, read the lines (the exact "
            "numbered source lines of a hunk), line <n>, spell that, findings, repeat, slower, "
            "faster, stop, 'no, I said <command>' to correct a misheard command, and 'request "
            "changes <comment>' followed by confirm or cancel. Every answer reads back what was "
            "understood before acting. A confirmed review is bound to the head commit by a "
            "single-use grant and re-checked live; it is recorded and not sent unless the server "
            "runs with VOLCAN_GITHUB_WRITE=1 and a GITHUB_TOKEN, and the outcome says which. "
            "A host that supports MCP Apps can draw the result as the ui://volcan/review-card view."
        ),
        input_model=ReviewTurnRequest, handler=tool_review_turn, output_model=ReviewTurnResult,
        meta={"ui": {"resourceUri": REVIEW_CARD_URI}},
    ))
    registry.register(ToolDefinition(
        name="translate_text_to_braille",
        title="Translate text to Unicode Braille",
        description=(
            "Translate text or code into Unicode Braille patterns in the U+2800 block, in "
            "eight-dot code fidelity (one cell per character, lossless) or six-dot literary "
            "fidelity (lossy for code, with the collisions named in the result)."
        ),
        input_model=BrailleTranslateRequest, handler=tool_braille_translate,
    ))
    registry.register(ToolDefinition(
        name="braille_diff_digest",
        title="Format a patch for a Braille display",
        description=(
            "Format a unified patch with tactile add and remove markers for a Braille display. "
            "Defaults to eight-dot code fidelity so every code symbol keeps its own cell; the "
            "result says whether the rendering is lossless."
        ),
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


def build_resource_registry() -> ResourceRegistry:
    registry = ResourceRegistry()
    registry.register(review_card_resource())
    return registry
