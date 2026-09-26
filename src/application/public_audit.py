"""The public audit view a durable deployment shows an anonymous visitor.

In durable mode every governed action staged through the public surface (the
REST and MCP ``stage_governed_action``, which carry no credential) is sealed
into one shared hash chain, ``PUBLIC_DEMO_AUDIT_SCOPE``. Anyone may read the
newest part of that chain, so anything a caller typed is withheld on the way
out: the command, the action id, the action type and the principal names are
shown only when they are the companion page's own fixed values. The payload
hash, the state, the timestamp and the chain position are always shown, so the
record stays checkable without repeating what a stranger wrote.

Records of anonymous review sessions and voice sessions stay in their private
per-session chains and are never listed here. A reviewer who presents a roster
credential additionally sees their own review chains, unredacted.
"""
from __future__ import annotations

import re
from typing import Any

from src.domain.governed_action import AuditLogRecord

#: The one chain the anonymous public surface writes to and reads from.
PUBLIC_DEMO_AUDIT_SCOPE = "public:governed-demo"

#: How many of the newest public records one audit read returns.
PUBLIC_AUDIT_LIMIT = 50

#: Owner of durable voice sessions opened without a roster credential. The
#: roster refuses any identity containing ":", so no reviewer can share it.
ANONYMOUS_VOICE_OWNER = "public:anonymous"

WITHHELD = "withheld: written by a caller"

#: The companion page's own values (docs/index.html STAGED_COMMAND, its
#: approver_id and the DTO defaults). Anything else a caller sent is withheld.
PUBLIC_COMMANDS = frozenset({"git diff HEAD"})
PUBLIC_ACTION_TYPES = frozenset({"TERMINAL_COMMAND"})
PUBLIC_PRINCIPALS = frozenset({"volcan-agent", "companion-operator", "developer", "unapproved"})
_PAGE_ACTION_ID = re.compile(r"act_[0-9]{1,12}")
_REFUSAL_CODE = re.compile(r"REFUSED [A-Z_]{1,40}")

#: Opening sentences the planner and the use case write. When the command is
#: withheld, only the sentence is kept: the rest can repeat the command.
_OUTCOME_SENTENCES = (
    "Dry run only, nothing was executed.",
    "Refused, and nothing was executed.",
    "Action rejected by operator.",
)

PUBLIC_VIEW_NOTE = (
    "Durable mode: this list is the newest part of the public demo chain. A command, "
    "action id, action type or name typed by a caller is withheld; the payload hash "
    "still binds it. Anonymous review and voice sessions are sealed in their own "
    "private chains and are not listed here."
)


def _shown(value: str, allowed: frozenset[str]) -> str:
    return value if value in allowed else WITHHELD


def _public_outcome(outcome: str, command_shown: bool) -> str:
    if command_shown:
        return outcome
    if _REFUSAL_CODE.fullmatch(outcome):
        return outcome
    for sentence in _OUTCOME_SENTENCES:
        if outcome.startswith(sentence):
            return sentence if outcome == sentence else f"{sentence} The rest is withheld."
    return WITHHELD


def public_record_view(record: AuditLogRecord) -> dict[str, Any]:
    """One public-chain record, with caller-written text withheld."""
    command_shown = record.command in PUBLIC_COMMANDS
    action_shown = bool(_PAGE_ACTION_ID.fullmatch(record.action_id))
    return {
        "id": record.record_id if action_shown else f"public-{record.sequence}",
        "action": record.action_id if action_shown else WITHHELD,
        "action_type": _shown(record.action_type, PUBLIC_ACTION_TYPES),
        "command": record.command if command_shown else WITHHELD,
        "payload_hash": record.payload_hash,
        "state": record.state.value,
        "outcome": _public_outcome(record.execution_stdout, command_shown),
        "staged_by": _shown(record.staged_by, PUBLIC_PRINCIPALS),
        "approved_by": _shown(record.approved_by, PUBLIC_PRINCIPALS),
        "timestamp": record.timestamp,
        "chain": "public",
        "sequence": record.sequence,
    }
