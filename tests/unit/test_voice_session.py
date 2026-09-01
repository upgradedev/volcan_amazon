"""Unit tests for Voice Session Context."""
from src.domain.voice_session import VoiceSessionContext


def test_voice_session_turn_recording():
    session = VoiceSessionContext(session_id="sess-01", user_id="user-alex", current_repo="volcan_amazon")
    session.record_turn("user", "Summarize diff")
    session.record_turn("volcan", "Modified 2 files.")

    assert len(session.dialogue_history) == 2
    assert session.dialogue_history[0]["role"] == "user"
    assert session.dialogue_history[1]["role"] == "volcan"


def test_voice_session_diff_focus():
    session = VoiceSessionContext(session_id="sess-02", user_id="user-alex", current_repo="volcan_amazon")
    session.set_diff_focus("diff-101", file_name="src/auth.py")

    assert session.active_diff_id == "diff-101"
    assert session.focused_file == "src/auth.py"
    assert session.focused_section_index == 0
    assert session.next_section() == 1
