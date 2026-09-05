"""Unit tests for Haptic Feedback & Deaf/HOH Tactile Notifications."""
from src.application.accessibility_use_case import AccessibilityOrchestratorUseCase
from src.domain.haptic_feedback import (
    HapticPatternType,
    HapticProfile,
)


def test_haptic_profile_success():
    profile = HapticProfile.from_event("TASK_COMPLETED")
    assert profile.pattern_type == HapticPatternType.PULSE_SUCCESS
    assert profile.total_duration_ms > 0
    assert len(profile.steps) == 3
    assert "[HAPTIC: Double Pulse" in profile.visual_caption


def test_haptic_profile_security_flag():
    profile = HapticProfile.from_event("SECURITY_FLAG")
    assert profile.pattern_type == HapticPatternType.SECURITY_ALERT_RHYTHM
    assert len(profile.steps) == 5
    assert "[HAPTIC: Triple Buzz" in profile.visual_caption


def test_haptic_orchestrator_use_case():
    use_case = AccessibilityOrchestratorUseCase()
    res = use_case.generate_haptic_profile("SECURITY_FLAG")
    assert res["pattern_type"] == "SECURITY_ALERT"
    assert len(res["steps"]) == 5
    assert "visual_caption" in res
