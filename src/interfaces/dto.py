"""Interfaces Layer: request models shared by the REST and MCP surfaces.

These pydantic models are the single definition of what each operation accepts.
The REST routes validate against them and the MCP tool catalog generates its
``inputSchema`` from them, so the published schema and the code that parses the
arguments can never disagree.
"""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.domain.sonification import EarconType

#: Largest patch the digest endpoints accept. Local parsing reads the whole
#: patch, so findings near the end of a large patch must survive; the model
#: excerpt is separately capped at 3000 characters. This bound stops absurd
#: payloads, not real patches: one million characters is an order of
#: magnitude past the largest patch in the test corpus.
MAX_RAW_DIFF_CHARS = 1_000_000


class DigestRequest(BaseModel):
    raw_diff: str = Field(
        ..., max_length=MAX_RAW_DIFF_CHARS, description="Unified git patch content"
    )
    level: int = Field(0, description="Digest detail level (0 executive, 1 file-by-file, 2 drill-down)")


class CompanionDigestRequest(DigestRequest):
    """The REST digest request, with one field the MCP tool does not publish.

    The companion page draws the default patch's real answer when it loads,
    before anyone has asked for anything. A page view must never start a billed
    model call, so that request names the local engine. Every request the
    person makes leaves ``engine`` at ``auto``.
    """

    engine: Literal["auto", "local"] = Field(
        "auto",
        description="auto attempts Amazon Bedrock when it is available; local never calls a model",
    )


class DrillDownRequest(BaseModel):
    raw_diff: str = Field(
        ..., max_length=MAX_RAW_DIFF_CHARS, description="Unified git patch content"
    )
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


#: One sentence, reused by both Braille models so the two surfaces describe the
#: choice in the same words.
_FIDELITY_DESCRIPTION = (
    "'code' for eight-dot computer Braille, one cell per printable ASCII character and "
    "lossless; 'literary' for six-dot cells with capital and number prefixes, which is "
    "lossy for code because ( ) and = share one cell"
)


class BrailleTranslateRequest(BaseModel):
    text: str = Field(..., description="ASCII text or code to translate into Unicode Braille")
    fidelity: str = Field("literary", description=_FIDELITY_DESCRIPTION + "; prose defaults to literary")


class BrailleDiffRequest(BaseModel):
    raw_diff: str = Field(..., description="Unified git patch to format for a Braille display")
    fidelity: str = Field("code", description=_FIDELITY_DESCRIPTION + "; a patch defaults to code")


class ReviewTurnRequest(BaseModel):
    """One turn of the spoken review dialogue.

    ``transcript`` is what the developer said or typed. The page sends the
    pull request URL and the pasted patch with every turn so an ``open``
    command can act on whichever one is filled in, and it sends back the
    approval grant it received from a ``request changes`` turn so a ``confirm``
    can present it.
    """

    session_id: str = Field(..., description="Conversation session identifier")
    user_id: str = Field("developer", description="Dry-run display identity; live approver comes only from the authenticated reviewer credential")
    transcript: str = Field(..., description="What was heard or typed, e.g. 'what changed in auth.py'")
    pr_url: str | None = Field(None, description="GitHub pull request URL an 'open' command should fetch")
    raw_diff: str | None = Field(None, description="Pasted unified patch an 'open' command should use when no URL is given")
    approval_grant: str | None = Field(None, description="The single-use grant issued by 'request changes', presented by 'confirm'")


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


# --- structured results ------------------------------------------------------
#
# The tool catalog publishes these models' JSON Schemas as ``outputSchema``.
# MCP revision 2025-11-25 (server/tools, "Output Schema") says a server that
# provides an output schema MUST return structured results that conform to it.
# Each model forbids unknown top-level keys, so a key added to an operation
# without being added here fails tests/integration/test_mcp_structured_results.py
# instead of quietly breaking the published contract.

_STRICT = ConfigDict(extra="forbid")


class DigestResult(BaseModel):
    model_config = _STRICT

    voice_summary: str = Field(..., description="The digest as displayed, with code operators literal")
    voice_summary_for_speech: str = Field(..., description="The same digest with each code operator named for a speech engine")
    synthesis_mode: str = Field(..., description="bedrock when a model answered, heuristic-local otherwise")
    synthesis_fallback_reason: str | None = Field(..., description="Why the local engine answered; null when a model did")
    model_prose_full: str | None = Field(..., description="The model's full answer; null unless a model answered")
    model_input_truncated: bool = Field(..., description="True when the model was shown only a prefix of the patch")
    model_input_chars_sent: int | None = Field(..., description="Patch characters the model was shown")
    model_input_chars_total: int | None = Field(..., description="Patch characters in total")
    model_answered: str | None = Field(..., description="The Bedrock model id that answered; null unless a model answered")
    total_files: int
    insertions: int
    deletions: int
    category_breakdown: dict[str, int]
    critical_findings: list[str] = Field(..., description="One sentence per rule that matched; empty when no rule matched")


class DrillDownResult(BaseModel):
    model_config = _STRICT

    spoken_text: str
    spoken_text_for_speech: str
    file_path: str
    category: str
    significance: str
    security_flags: list[str] = Field(..., description="Machine labels of the rules that matched in this section")
    security_findings: list[str] = Field(..., description="One sentence per matched rule, in the same order")


class ReviewFocus(BaseModel):
    model_config = _STRICT

    state: str
    file_index: int | None
    file_path: str | None
    total_files: int
    hunk_index: int | None
    total_hunks: int
    line_index: int | None
    total_lines: int
    pull_request: str | None
    head_sha: str | None
    pending_review: str | None


class ReviewLine(BaseModel):
    model_config = _STRICT

    kind: Literal["context", "add", "remove"]
    text: str
    old_no: int | None
    new_no: int | None
    index: int
    total: int
    spelled: str


class PullRequestSummary(BaseModel):
    model_config = _STRICT

    owner: str
    repo: str
    number: int
    url: str
    title: str
    state: str | None
    head_sha: str
    head_ref: str | None
    base_ref: str | None
    author: str | None
    diff_bytes: int


class PendingReview(BaseModel):
    model_config = _STRICT

    action_id: str
    payload_hash: str
    expires_at_epoch: float
    lease_sec: float
    body: str
    head_sha: str
    pull_request: str


class ReviewOutcome(BaseModel):
    """How a confirm ended. The submission adds its own fields, so more are allowed."""

    model_config = ConfigDict(extra="allow")

    submitted: bool
    dry_run: bool
    refusal_code: str | None = None
    spoken: str | None = None


class ReviewCardLine(BaseModel):
    model_config = _STRICT

    kind: Literal["added", "removed"]
    number: int | None = Field(..., description="New line number for an added line, old line number for a removed one")
    text: str
    braille: str = Field(..., description="The line in eight-dot code Braille, one cell per character")


class ReviewCard(BaseModel):
    """What the ui:// review card draws: one file, its finding, its changed lines."""

    model_config = _STRICT

    resource_uri: str
    file_path: str
    file_index: int
    total_files: int
    finding: str | None = Field(..., description="The first matched rule's sentence; null when no rule matched in this file")
    finding_count: int
    changed_lines: list[ReviewCardLine]
    changed_lines_shown: int
    changed_lines_total: int = Field(..., description="Added and removed lines in the hunk the card shows")
    braille_fidelity: Literal["code"]
    braille_lossless: bool = Field(..., description="False when a shown line holds a character the code table has no cell for")
    can_submit: bool = Field(..., description="False for a pasted patch, which has no pull request to review")
    awaiting_confirmation: bool


class ReviewTurnResult(BaseModel):
    model_config = _STRICT

    state: Literal["IDLE", "OVERVIEW", "FILE", "LINES", "CONFIRM_REVIEW", "SUBMITTED", "RECORDED", "REFUSED"]
    understood: str
    readback: str
    spoken: str
    readback_for_speech: str
    spoken_for_speech: str
    speech_rate: float
    silent: bool
    error: bool
    focus: ReviewFocus
    line: ReviewLine | None
    pull_request: PullRequestSummary | None
    pending_review: PendingReview | None
    approval_grant: str | None = Field(..., description="The single-use grant a confirm must present; set only by a request changes turn")
    review_outcome: ReviewOutcome | None
    review_path: dict[str, Any] = Field(..., description="The review write capability, as /health reports it")
    awaiting_confirmation: bool
    review_card: ReviewCard | None = Field(..., description="What the ui:// review card draws; null until a patch is open")
