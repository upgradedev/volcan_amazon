"""Interfaces Layer: request models shared by the REST and MCP surfaces.

These pydantic models are the single definition of what each operation accepts.
The REST routes validate against them and the MCP tool catalog generates its
``inputSchema`` from them, so the published schema and the code that parses the
arguments can never disagree.
"""
from typing import Any

from pydantic import BaseModel, Field

from src.domain.sonification import EarconType


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
