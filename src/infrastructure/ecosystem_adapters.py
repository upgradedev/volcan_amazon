"""Infrastructure adapters for Amazon Ecosystem Companions in Volcan.

Integrates:
- Bee Wearable: Spontaneous voice annotations attached to PR diffs.
- Fire TV: 10-foot high-contrast wallboard state broadcaster.
- Ring: Focus sanctuary presence sensor adapter with acoustic earcon triggers.
"""
from typing import Dict, Any, Optional, List
from src.domain.ecosystem_companion import (
    AmbientVoiceAnnotation,
    WallboardTelemetryFrame,
    FocusSanctuaryState,
    CompanionDeviceType,
)


class BeeCompanionAdapter:
    """Adapter for Bee Wearable ambient audio capture relay."""

    def __init__(self):
        self._annotations: List[AmbientVoiceAnnotation] = []

    def ingest_ambient_note(self, speaker_id: str, transcript: str, pr_id: str) -> AmbientVoiceAnnotation:
        # Evaluate security impact from spoken keywords
        impact = "HIGH" if any(i in transcript.lower() for i in ["security", "auth", "kms", "secret", "token"]) else "NORMAL"
        annotation = AmbientVoiceAnnotation.create(
            speaker_id=speaker_id,
            transcript=transcript,
            target_pr_id=pr_id,
            impact_level=impact
        )
        self._annotations.append(annotation)
        return annotation

    def get_annotations_for_pr(self, pr_id: str) -> List[AmbientVoiceAnnotation]:
        return [a for a in self._annotations if a.target_pr_id == pr_id]


class FireTvWallboardAdapter:
    """Adapter for broadcasting visual telemetry to Fire TV 10-Foot companion display."""

    def __init__(self):
        self._last_frame: Optional[WallboardTelemetryFrame] = None

    def broadcast_telemetry(self, lease_id: Optional[str], ttl_remaining: int, security_flag: bool, dora_rating: str = "ELITE") -> Dict[str, Any]:
        frame = WallboardTelemetryFrame.from_lease(lease_id, ttl_remaining, security_flag, dora_rating)
        self._last_frame = frame
        return {
            "device": CompanionDeviceType.FIRE_TV_WALLBOARD.value,
            "frame_id": frame.frame_id,
            "lease_id": frame.active_lease_id,
            "ttl_sec": frame.lease_ttl_remaining_sec,
            "security_flag": frame.ast_security_flag,
            "dora_velocity": frame.dora_velocity_rating,
            "high_contrast": frame.high_contrast,
            "rendered_at": frame.rendered_at.isoformat(),
        }

    @property
    def latest_frame(self) -> Optional[WallboardTelemetryFrame]:
        return self._last_frame


class RingSanctuaryAdapter:
    """Adapter for Ring physical presence alerts during dual-custody focus sessions."""

    def __init__(self):
        self._active_sanctuary: Optional[FocusSanctuaryState] = None

    def engage_sanctuary(self, lease_id: str) -> FocusSanctuaryState:
        self._active_sanctuary = FocusSanctuaryState.enter_sanctuary(lease_id)
        return self._active_sanctuary

    def handle_presence_event(self, sensor_zone: str) -> Dict[str, Any]:
        if not self._active_sanctuary or not self._active_sanctuary.sanctuary_active:
            return {
                "sanctuary_active": False,
                "action": "STANDARD_PASSTHROUGH[",
                "acoustic_earcon": None,
            }
        
        # During active release lease, suppress abrasive chimes and play subtle focus earcon
        return {
            "sanctuary_active": True,
            "lease_id": self._active_sanctuary.lease_id,
            "zone": sensor_zone,
            "action": "SUPPRESS_LOUD_CHIME",
            "acoustic_earcon": "EARCON_GENTLE_SANCTUARY_CUE_440HZ",
            "spoken_digest": f"Gentle notice: Motion at {sensor_zone}. Focus sanctuary active.",
        }
