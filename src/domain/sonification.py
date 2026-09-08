"""Domain model and pure-Python Acoustic Waveform Synthesizer for Audio Earcons."""
import io
import math
import struct
from dataclasses import dataclass
from enum import Enum

from src.domain.semantic_diff import ChangeCategory


class EarconType(str, Enum):
    AGENT_THINKING = "AGENT_THINKING"
    DIFF_READY = "DIFF_READY"
    SECURITY_FINDING = "SECURITY_FINDING"
    TEST_PASSED = "TEST_PASSED"
    TEST_FAILED = "TEST_FAILED"
    LINT_WARNING = "LINT_WARNING"
    GOVERNANCE_CHALLENGE = "GOVERNANCE_CHALLENGE"
    ACTION_COMMITTED = "ACTION_COMMITTED"
    DRILL_DOWN_OPENED = "DRILL_DOWN_OPENED"
    #: A side effect was recorded and deliberately not sent. It must not sound
    #: like ACTION_COMMITTED, because a listener who cannot see the page has
    #: only the cue to tell "sent" from "would have sent".
    DRY_RUN_RECORDED = "DRY_RUN_RECORDED"


def earcon_for_report(report) -> EarconType:
    """The digest cue, chosen from the verdict the digest reached.

    The cue is the pre-verbal triage layer: a listener learns the falling pair
    in one session and knows a security finding is coming before any word
    arrives. That only works if the cue is a function of the result, so this is
    the single place the choice is made. Every surface that speaks a digest -
    REST, MCP and the voice turn - calls it, because a cue that means one thing
    on one surface and another thing on the next is worse than no cue.
    """
    if getattr(report, "critical_findings", None):
        return EarconType.SECURITY_FINDING
    if ChangeCategory.SECURITY_SENSITIVE.value in (getattr(report, "category_breakdown", None) or {}):
        return EarconType.SECURITY_FINDING
    return EarconType.DIFF_READY


def earcon_for_section(section) -> EarconType:
    """The drill-down cue for one file section, chosen the same way.

    A drill-down is where a reviewer lands on the one file that matters, so the
    same falling cue has to survive the descent. A section carries either a
    parsed finding or a raw keyword flag; either one is a security verdict.
    """
    if getattr(section, "security_findings", None) or getattr(section, "security_flags", None):
        return EarconType.SECURITY_FINDING
    return EarconType.DRILL_DOWN_OPENED


@dataclass(frozen=True)
class AudioTone:
    frequency_hz: float
    duration_ms: int
    volume: float = 0.5  # 0.0 to 1.0


@dataclass(frozen=True)
class AudioCue:
    earcon_type: EarconType
    tones: list[AudioTone]
    spoken_fallback: str


class WaveformSynthesizer:
    """Pure-Python PCM WAV synthesizer for generating distinct acoustic earcons."""

    SAMPLE_RATE = 22050

    @classmethod
    def generate_wav_bytes(cls, tones: list[AudioTone]) -> bytes:
        total_samples = []
        for tone in tones:
            num_samples = int((tone.duration_ms / 1000.0) * cls.SAMPLE_RATE)
            for i in range(num_samples):
                # Apply simple envelope (attack and decay) to prevent click artifacts
                envelope = 1.0
                attack_len = int(0.05 * num_samples)
                decay_len = int(0.15 * num_samples)
                if i < attack_len:
                    envelope = i / max(1, attack_len)
                elif i > num_samples - decay_len:
                    envelope = (num_samples - i) / max(1, decay_len)

                t = float(i) / cls.SAMPLE_RATE
                sample_val = math.sin(2.0 * math.pi * tone.frequency_hz * t) * tone.volume * envelope
                # 16-bit PCM scale (-32767 to 32767)
                int_sample = int(sample_val * 32767.0)
                int_sample = max(-32767, min(32767, int_sample))
                total_samples.append(int_sample)

        # Pack into WAV container format
        byte_stream = io.BytesIO()
        data_size = len(total_samples) * 2  # 2 bytes per 16-bit mono sample
        
        # RIFF header
        byte_stream.write(b"RIFF")
        byte_stream.write(struct.pack("<I", 36 + data_size))
        byte_stream.write(b"WAVE")
        
        # fmt chunk
        byte_stream.write(b"fmt ")
        byte_stream.write(struct.pack("<I", 16))  # chunk size
        byte_stream.write(struct.pack("<H", 1))   # audio format: PCM
        byte_stream.write(struct.pack("<H", 1))   # mono
        byte_stream.write(struct.pack("<I", cls.SAMPLE_RATE))
        byte_stream.write(struct.pack("<I", cls.SAMPLE_RATE * 2))  # byte rate
        byte_stream.write(struct.pack("<H", 2))   # block align
        byte_stream.write(struct.pack("<H", 16))  # bits per sample
        
        # data chunk
        byte_stream.write(b"data")
        byte_stream.write(struct.pack("<I", data_size))
        for s in total_samples:
            byte_stream.write(struct.pack("<h", s))

        return byte_stream.getvalue()
