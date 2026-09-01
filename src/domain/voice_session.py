"""Domain model for Multi-Turn Conversational Voice Sessions on Alexa+."""
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class VoiceSessionContext:
    session_id: str
    user_id: str
    current_repo: str
    active_diff_id: str | None = None
    focused_file: str | None = None
    focused_section_index: int = 0
    staged_action_id: str | None = None
    dialogue_history: list[dict[str, str]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)

    def record_turn(self, role: str, text: str) -> None:
        self.dialogue_history.append({
            "role": role,
            "text": text,
            "timestamp": datetime.utcnow().isoformat()
        })

    def set_diff_focus(self, diff_id: str, file_name: str | None = None) -> None:
        self.active_diff_id = diff_id
        self.focused_file = file_name
        self.focused_section_index = 0

    def next_section(self) -> int:
        self.focused_section_index += 1
        return self.focused_section_index
