"""Unit tests for Amazon Ecosystem Companions in Volcan."""
pytest = __import__("pytest")
from src.domain.ecosystem_companion import (
    AmbientVoiceAnnotation,
    WallboardTelemetryFrame,
    FocusSanctuaryState,
    CompanionDeviceType,
)
from src.infrastructure.ecosystem_adapters import (
    BeeCompanionAdapter,
    FireTvWallboardAdapter,
    RingSanctuaryAdapter,
)
from src.application.ecosystem_companion_use_case import OrchestrateEcosystemCompanionUseCase


def test_bee_annotation_creation_and_validation():
    ann = AmbientVoiceAnnotation.create(
        speaker_id="speaker_1",
        transcript="Refactor auth service to use validated tokens.",
        target_pr_id="PR-42",
        impact_level="HIGH"
    )
    assert ann.speaker_id == "speaker_1"
    assert ann.target_pr_id == "PR-42"
    assert ann.impact_level == "HIGH"
    assert ann.annotation_id.startswith("ann_")

    with pytest.raises(ValueError):
        AmbientVoiceAnnotation.create("speaker_1", "  ", "PR-42")


def test_firetv_wallboard_framing():
    frame = WallboardTelemetryFrame.from_lease(
        lease_id="act_9909",
        ttl_sec=240,
        security_flag=True,
        rating="ELITE"
    )
    assert frame.active_lease_id == "act_9909"
    assert frame.lease_ttl_remaining_sec == 240
    assert frame.ast_security_flag is True
    assert frame.high_contrast is True


def test_ring_sanctuary_state():
    sanctuary = FocusSanctuaryState.enter_sanctuary("act_1234")
    assert sanctuary.sanctuary_active is True
    assert sanctuary.lease_id == "act_1234"
    assert sanctuary.earcon_chime_code == "SANCTUARY_SHIELD_ENGAGED"


def test_ecosystem_orchestrator_use_case_flow():
    use_case = OrchestrateEcosystemCompanionUseCase()

    # 1. Bee ambient audio input
    bee_res = use_case.attach_bee_ambient_note(
        speaker_id="engineer_dev",
        transcript="We must ensure KMS keys are rotated before shipping.",
        pr_id="PR-88"
    )
    assert bee_res["impact_level"] == "HIGH"
    assert "ambient voice note" in bee_res["spoken_digest"].lower()

    # 2. Fire TV wallboard sync
    tv_res = use_case.sync_firetv_compatibility(
        lease_id="act_8818",
        ttl_sec=300,
        security_flag=True
    )
    assert tv_res["device"] == "FIRE_TV_WALLBOARD"
    assert tv_res["ttl_sec"] == 300

    # 3. Ring focus presence
    ring_res = use_case.evaluate_ring_presence(
        sensor_zone="Front Doorbell",
        active_lease_id="act_8818"
    )
    assert ring_res["sanctuary_active"] is True
    assert ring_res["action"] == "SUPPRESS_LOUD_CHIME"
    assert "focus sanctuary" in ring_res["spoken_digest"].lower()
