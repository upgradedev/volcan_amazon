"""Application Layer: Multi-Modal Accessibility Orchestration Use Cases.

Coordinates:
- Adaptive Switch binary pulse processing
- Haptic vibration pattern formatting for Deaf/HOH & wearables
"""
from typing import Any, Dict
from src.domain.adaptive_switch import SwitchInputType, SwitchSignal, SwitchNavigationState, SwitchAction
from src.domain.haptic_feedback import HapticProfile


class AccessibilityOrchestratorUseCase:
    """Orchestrates multi-modal accessible controls across switch, voice, braille, and haptics."""

    def process_switch_signal(
        self,
        input_type_str: str,
        signal_strength: float = 1.0,
        duration_ms: int = 150,
        is_long_press: bool = False,
    ) -> Dict[str, Any]:
        try:
            in_type = SwitchInputType(input_type_str)
        except ValueError:
            in_type = SwitchInputType.SINGLE_BUTTON

        signal = SwitchSignal(
            input_type=in_type,
            signal_strength=signal_strength,
            duration_ms=duration_ms,
            is_long_press=is_long_press,
        )
        action = signal.map_to_action()

        return {
            "input_type": in_type.value,
            "signal_strength": signal_strength,
            "duration_ms": duration_ms,
            "resolved_action": action.value,
            "description": f"Switch pulse resolved to {action.value} for hands-free operator.",
        }

    def generate_haptic_profile(self, event_type: str) -> Dict[str, Any]:
        profile = HapticProfile.from_event(event_type)
        return {
            "event_type": event_type,
            "pattern_type": profile.pattern_type.value,
            "total_duration_ms": profile.total_duration_ms,
            "steps": [
                {"duration_ms": s.duration_ms, "intensity": s.intensity}
                for s in profile.steps
            ],
            "visual_caption": profile.visual_caption,
        }
