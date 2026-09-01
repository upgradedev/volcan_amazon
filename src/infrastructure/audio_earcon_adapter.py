"""Infrastructure Adapter: Audio Earcon Generator & Sound Player."""
from src.domain.sonification import EarconType, AudioCue


class AudioEarconAdapter:
    def __init__(self):
        self._cues = {
            EarconType.AGENT_THINKING: AudioCue(EarconType.AGENT_THINKING, 440, 200, "Agent working"),
            EarconType.DIFF_READY: AudioCue(EarconType.DIFF_READY, 587, 150, "Diff summary ready"),
            EarconType.TEST_PASSED: AudioCue(EarconType.TEST_PASSED, 880, 250, "Tests passed"),
            EarconType.TEST_FAILED: AudioCue(EarconType.TEST_FAILED, 220, 400, "Tests failed"),
            EarconType.GOVERNANCE_CHALLENGE: AudioCue(EarconType.GOVERNANCE_CHALLENGE, 660, 300, "Approval required"),
            EarconType.ACTION_COMMITTED: AudioCue(EarconType.ACTION_COMMITTED, 988, 200, "Action completed"),
        }

    def get_cue(self, earcon_type: EarconType) -> AudioCue:
        return self._cues.get(
            earcon_type,
            AudioCue(earcon_type, 440, 100, "Event notification")
        )
