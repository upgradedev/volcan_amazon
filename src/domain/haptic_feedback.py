"""Pure Domain Layer: Haptic Feedback & Tactile Vibration Patterns.

Supports:
- Deaf and Hard-of-Hearing (HOH) developers who cannot hear audio earcons
- Wearable haptic alerts (Bee Wearable, Apple Watch, Smart Ring, Tactile Belt)
- Silent notification cadence for quiet hours and privacy
"""
from dataclasses import dataclass
from enum import Enum
from typing import List


class HapticPatternType(str, Enum):
    PULSE_SUCCESS = "PULSE_SUCCESS"          # Short gentle double pulse (200ms on, 100ms off, 200ms on)
    WARNING_BUZZ = "WARNING_BUZZ"            # Medium intensity continuous buzz (500ms)
    SECURITY_ALERT_RHYTHM = "SECURITY_ALERT" # Triple rapid high-frequency buzz (100ms, 50ms, 100ms, 50ms, 100ms)
    HEARTBEAT_LEASE = "HEARTBEAT_LEASE"      # Rhythmic slow tick indicating active countdown
    SILENT_MUTE = "SILENT_MUTE"


@dataclass(frozen=True)
class HapticVibrationStep:
    duration_ms: int
    intensity: float  # 0.0 to 1.0


@dataclass(frozen=True)
class HapticProfile:
    pattern_type: HapticPatternType
    steps: List[HapticVibrationStep]
    total_duration_ms: int
    visual_caption: str  # Closed-caption equivalent for visual / screen display

    @classmethod
    def from_event(cls, event_type: str) -> "HapticProfile":
        """Deterministic mapping of development events to tactile vibration patterns."""
        if event_type in ("TASK_COMPLETED", "DIFF_READY", "CONFIRM"):
            steps = [
                HapticVibrationStep(duration_ms=150, intensity=0.6),
                HapticVibrationStep(duration_ms=80, intensity=0.0),
                HapticVibrationStep(duration_ms=200, intensity=0.9),
            ]
            return cls(
                pattern_type=HapticPatternType.PULSE_SUCCESS,
                steps=steps,
                total_duration_ms=430,
                visual_caption="[HAPTIC: Double Pulse — Diff Ready / Task Completed]",
            )

        if event_type in ("SECURITY_FLAG", "ALERT", "KMS_WARNING"):
            steps = [
                HapticVibrationStep(duration_ms=100, intensity=1.0),
                HapticVibrationStep(duration_ms=50, intensity=0.0),
                HapticVibrationStep(duration_ms=100, intensity=1.0),
                HapticVibrationStep(duration_ms=50, intensity=0.0),
                HapticVibrationStep(duration_ms=150, intensity=1.0),
            ]
            return cls(
                pattern_type=HapticPatternType.SECURITY_ALERT_RHYTHM,
                steps=steps,
                total_duration_ms=450,
                visual_caption="[HAPTIC: Triple Buzz — Security Flag / Review Required]",
            )

        if event_type in ("LEASE_TICK", "LEASE_ACTIVE"):
            steps = [
                HapticVibrationStep(duration_ms=80, intensity=0.3),
                HapticVibrationStep(duration_ms=920, intensity=0.0),
            ]
            return cls(
                pattern_type=HapticPatternType.HEARTBEAT_LEASE,
                steps=steps,
                total_duration_ms=1000,
                visual_caption="[HAPTIC: Slow Pulse — Dual-Custody Lease Active]",
            )

        return cls(
            pattern_type=HapticPatternType.SILENT_MUTE,
            steps=[],
            total_duration_ms=0,
            visual_caption="[HAPTIC: Idle]",
        )
