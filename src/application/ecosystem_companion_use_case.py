"""Application use case for orchestrating Amazon Ecosystem Companions in Volcan."""
from typing import Any, Dict, Optional

from src.infrastructure.ecosystem_adapters import (
    BeeCompanionAdapter,
    FireTvWallboardAdapter,
    RingSanctuaryAdapter,
)


class OrchestrateEcosystemCompanionUseCase:
    """Orchestrates Amazon Alexa+ central voice forge with Bee, Fire TV, and Ring companions."""

    def __init__(
        self,
        bee_adapter: Optional[BeeCompanionAdapter] = None,
        firetv_adapter: Optional[FireTvWallboardAdapter] = None,
        ring_adapter: Optional[RingSanctuaryAdapter] = None,
    ):
        self.bee = bee_adapter or BeeCompanionAdapter()
        self.firetv = firetv_adapter or FireTvWallboardAdapter()
        self.ring = ring_adapter or RingSanctuaryAdapter()

    def attach_bee_ambient_note(
        self,
        speaker_id: str,
        transcript: str,
        pr_id: str
    ) -> Dict[str, Any]:
        """Ingests voice annotation from Bee Wearable and generates Alexa spoken confirmation."""
        annotation = self.bee.ingest_ambient_note(speaker_id, transcript, pr_id)
        
        earcon = "EARCON_SECURITY_FLAG_320HZ" if annotation.impact_level == "HIGH" else "EARCON_NOTE_ATTACHED_440HZ"
        spoken = f"Ambient voice note captured from Bee Wearable by {speaker_id} for PR {pr_id}. Impact: {annotation.impact_level}."
        return {
            "annotation_id": annotation.annotation_id,
            "speaker_id": annotation.speaker_id,
            "transcript": annotation.transcript,
            "pr_id": annotation.target_pr_id,
            "impact_level": annotation.impact_level,
            "earcon": earcon,
            "spoken_digest": spoken,
        }

    def sync_firetv_compatibility(
        self,
        lease_id: Optional[str],
        ttl_sec: int,
        security_flag: bool,
        dora_rating: str = "ELITE"
    ) -> Dict[str, Any]:
        """Broadcasts telemetry frame to 10-foot Fire TV ambient warroom display."""
        return self.firetv.broadcast_telemetry(lease_id, ttl_sec, security_flag, dora_rating)

    def evaluate_ring_presence(
        self,
        sensor_zone: str,
        active_lease_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Processes Ring presence event and returns acoustic focus chime."""
        if active_lease_id:
            self.ring.engage_sanctuary(active_lease_id)
        return self.ring.handle_presence_event(sensor_zone)
