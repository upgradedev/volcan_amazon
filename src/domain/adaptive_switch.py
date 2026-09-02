"""Pure Domain Layer: Adaptive Switch & Motor Accessibility Controls.

Supports:
- Single-Switch Scanning & Dwell Selection
- Sip-and-Puff (Puff = Approve, Sip = Reject)
- Foot Pedal & Head Switch binary pulse inputs for quadriplegic and motor-impaired developers
"""
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class SwitchInputType(str, Enum):
    SINGLE_BUTTON = "SINGLE_BUTTON"
    SIP_AND_PUFF = "SIP_AND_PUFF"
    FOOT_PEDAL = "FOOT_PEDAL"
    HEAD_SWITCH = "HEAD_SWITCH"
    EYE_GAZE_DWELL = "EYE_GAZE_DWELL"


class SwitchAction(str, Enum):
    CONFIRM_LEASE = "CONFIRM_LEASE"
    REJECT_LEASE = "REJECT_LEASE"
    NEXT_DIFF_SECTION = "NEXT_DIFF_SECTION"
    REPEAT_AUDIO = "REPEAT_AUDIO"
    TRIGGER_EMERGENCY_STOP = "TRIGGER_EMERGENCY_STOP"


@dataclass(frozen=True)
class SwitchSignal:
    input_type: SwitchInputType
    signal_strength: float  # 0.0 to 1.0 (e.g. pressure for sip/puff)
    duration_ms: int
    is_long_press: bool

    def map_to_action(self) -> SwitchAction:
        """Deterministic mapping of binary switch pulses to governance actions."""
        if self.input_type == SwitchInputType.SIP_AND_PUFF:
            # Positive pressure (Puff) = Confirm, Negative/Low (Sip) = Reject
            if self.signal_strength >= 0.5:
                return SwitchAction.CONFIRM_LEASE
            return SwitchAction.REJECT_LEASE

        if self.is_long_press or self.duration_ms >= 1000:
            # Long press / dwell = Reject / Emergency Stop
            return SwitchAction.TRIGGER_EMERGENCY_STOP

        # Standard short press = Confirm / Next
        return SwitchAction.CONFIRM_LEASE


@dataclass(frozen=True)
class SwitchNavigationState:
    current_focus_index: int
    total_sections: int
    is_scanning_active: bool
    selected_action: Optional[SwitchAction] = None

    def advance_scan(self) -> "SwitchNavigationState":
        next_idx = (self.current_focus_index + 1) % max(1, self.total_sections)
        return SwitchNavigationState(
            current_focus_index=next_idx,
            total_sections=self.total_sections,
            is_scanning_active=True,
            selected_action=None,
        )

    def select_current(self, action: SwitchAction) -> "SwitchNavigationState":
        return SwitchNavigationState(
            current_focus_index=self.current_focus_index,
            total_sections=self.total_sections,
            is_scanning_active=False,
            selected_action=action,
        )
