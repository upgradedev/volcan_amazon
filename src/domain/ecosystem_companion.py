"""Pure domain models for Volcan Amazon Ecosystem Companions.

Connects Alexa+ central voice intelligence with ambient companion peripherals:
- Bee Wearable: Spontaneous out-of-desk voice annotations on pull requests.
- Fire TV: High-contrast 10-foot ambient wallboard for team war-rooms.
- Ring: Focus sanctuary presence alerts with acoustic earcons.
"""
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class CompanionDeviceType(str, Enum):
    BEE_WEARABLE = "BEE_WEARABLE"
    FIRE_TV_WALLBOARD = "FIRE_TV_WALLBOARD"
    RING_SANCTUARY = "RING_SANCTUARY"


@dataclass(frozen=True)
class AmbientVoiceAnnotation:
    """Spontaneous voice note captured by Bee Wearable attached to an AST diff."""
    annotation_id: str
    speaker_id: str
    transcript: str
    target_pr_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    impact_level: str = "NORMAL"

    @classmethod
    def create(cls, speaker_id: str, transcript: str, target_pr_id: str, impact_level: str = "NORMAL") -> "AmbientVoiceAnnotation":
        if not transcript or not transcript.strip():
            raise ValueError("Ambient transcript cannot be empty")
        return cls(
            annotation_id=f"ann_{uuid.uuid4().hex[:8]}",
            speaker_id=speaker_id,
            transcript=transcript.strip(),
            target_pr_id=target_pr_id,
            impact_level=impact_level
        )


@dataclass(frozen=True)
class WallboardTelemetryFrame:
    """10-foot Fire TV high-contrast visual display frame."""
    frame_id: str
    active_lease_id: Optional[str]
    lease_ttl_remaining_sec: int
    ast_security_flag: bool
    dora_velocity_rating: str
    high_contrast: bool = True
    rendered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def from_lease(cls, lease_id: Optional[str], ttl_sec: int, security_flag: bool, rating: str = "ELITE") -> "WallboardTelemetryFrame":
        return cls(
            frame_id=f"frame_{uuid.uuid4().hex[:8]}",
            active_lease_id=lease_id,
            lease_ttl_remaining_sec=max(0, ttl_sec),
            ast_security_flag=security_flag,
            dora_velocity_rating=rating,
            high_contrast=True
        )


@dataclass(frozen=True)
class FocusSanctuaryState:
    """Ring physical presence & focus state during dual-custody lease sessions."""
    session_id: str
    sanctuary_active: bool
    lease_id: Optional[str]
    last_presence_event: Optional[str] = None
    earcon_chime_code: str = "FOCUS_ACTIVE"

    @classmethod
    def enter_sanctuary(cls, lease_id: str) -> "FocusSanctuaryState":
        return cls(
            session_id=f"sanc_{uuid.uuid4().hex[:8]}",
            sanctuary_active=True,
            lease_id=lease_id,
            earcon_chime_code="SANCTUARY_SHIELD_ENGAGED"
        )
