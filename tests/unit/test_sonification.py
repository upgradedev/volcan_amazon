"""Unit tests for Audio Sonification and Waveform Synthesizer."""
from src.application.sonify_event_use_case import SonifyEventUseCase
from src.domain.sonification import AudioTone, EarconType, WaveformSynthesizer


def test_waveform_synthesizer_generates_valid_wav_header():
    tones = [AudioTone(frequency_hz=440.0, duration_ms=100, volume=0.5)]
    wav_bytes = WaveformSynthesizer.generate_wav_bytes(tones)
    
    assert len(wav_bytes) > 44  # Minimum valid WAV header size
    assert wav_bytes.startswith(b"RIFF")
    assert b"WAVE" in wav_bytes[:12]
    assert b"fmt " in wav_bytes
    assert b"data" in wav_bytes


def test_sonify_event_use_case_all_earcons():
    use_case = SonifyEventUseCase()
    
    for earcon_type in EarconType:
        cue, wav_bytes = use_case.execute(earcon_type)
        assert cue.earcon_type == earcon_type
        assert len(wav_bytes) > 100
        assert len(cue.tones) >= 1
        assert cue.spoken_fallback != ""
