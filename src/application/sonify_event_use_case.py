"""Use Case: Dispatch Audio Earcons and Generate PCM WAV Waveforms."""

from src.domain.sonification import AudioCue, AudioTone, EarconType, WaveformSynthesizer


class SonifyEventUseCase:
    def __init__(self):
        self._cue_catalog: dict[EarconType, AudioCue] = {
            EarconType.AGENT_THINKING: AudioCue(
                EarconType.AGENT_THINKING,
                [AudioTone(440.0, 150, 0.4), AudioTone(554.37, 150, 0.4)],
                "Volcan is analyzing your workspace."
            ),
            EarconType.DIFF_READY: AudioCue(
                EarconType.DIFF_READY,
                [AudioTone(523.25, 120, 0.5), AudioTone(659.25, 120, 0.5), AudioTone(783.99, 200, 0.5)],
                "Semantic diff digest is ready."
            ),
            EarconType.TEST_PASSED: AudioCue(
                EarconType.TEST_PASSED,
                [AudioTone(587.33, 100, 0.5), AudioTone(880.0, 250, 0.6)],
                "All test assertions passed cleanly."
            ),
            EarconType.TEST_FAILED: AudioCue(
                EarconType.TEST_FAILED,
                [AudioTone(311.13, 150, 0.6), AudioTone(220.0, 350, 0.6)],
                "Test suite execution failed."
            ),
            EarconType.LINT_WARNING: AudioCue(
                EarconType.LINT_WARNING,
                [AudioTone(466.16, 200, 0.4)],
                "Linter raised warnings."
            ),
            EarconType.GOVERNANCE_CHALLENGE: AudioCue(
                EarconType.GOVERNANCE_CHALLENGE,
                [AudioTone(659.25, 150, 0.6), AudioTone(523.25, 150, 0.6), AudioTone(659.25, 200, 0.6)],
                "Voice authorization required for this action."
            ),
            EarconType.ACTION_COMMITTED: AudioCue(
                EarconType.ACTION_COMMITTED,
                [AudioTone(440.0, 100, 0.5), AudioTone(880.0, 150, 0.6), AudioTone(1174.66, 200, 0.6)],
                "Action executed successfully."
            ),
            EarconType.DRILL_DOWN_OPENED: AudioCue(
                EarconType.DRILL_DOWN_OPENED,
                [AudioTone(523.25, 80, 0.4), AudioTone(783.99, 120, 0.5)],
                "Inspecting symbol details."
            ),
        }

    def execute(self, earcon_type: EarconType) -> tuple[AudioCue, bytes]:
        cue = self._cue_catalog.get(
            earcon_type,
            AudioCue(earcon_type, [AudioTone(440.0, 100, 0.3)], "Notification")
        )
        wav_bytes = WaveformSynthesizer.generate_wav_bytes(cue.tones)
        return cue, wav_bytes
