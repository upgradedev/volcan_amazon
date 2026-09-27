"""Explicit JSON codecs for Volcan's durable application state.

No pickle or dynamic class loading is used: state read from DynamoDB is data,
never executable input.  Pull-request diffs are not duplicated in the session
item after their semantic report has been built; a resume re-fetches the diff
from the bound pull-request URL before it needs fresh source text.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from src.domain.governed_action import (
    ActionState,
    AuditLogRecord,
    GovernedAction,
    Principal,
    PrincipalRole,
)
from src.domain.review_dialogue import (
    DialogueState,
    DialogueTurn,
    PullRequestSnapshot,
    ReviewDialogue,
)
from src.domain.review_grammar import Command
from src.domain.semantic_diff import (
    ChangeCategory,
    ChangeSignificance,
    DiffHunk,
    DiffLine,
    DiffSectionDigest,
    SemanticDiffReport,
)
from src.domain.sonification import EarconType
from src.domain.voice_session import VoiceSessionContext

MAX_HISTORY_ENTRIES = 100


def action_to_dict(action: GovernedAction) -> dict[str, Any]:
    return {
        "action_id": action.action_id,
        "action_type": action.action_type,
        "command_or_path": action.command_or_path,
        "payload_hash": action.payload_hash,
        "summary_spoken": action.summary_spoken,
        "staged_by": principal_to_dict(action.staged_by),
        "state": action.state.value,
        "created_at_epoch": action.created_at_epoch,
        "lease_duration_sec": action.lease_duration_sec,
        "approval_token": action.approval_token,
        "approved_by": principal_to_dict(action.approved_by) if action.approved_by else None,
        "execution_result": action.execution_result,
        "audit_scope": action.audit_scope,
    }


def action_from_dict(value: dict[str, Any]) -> GovernedAction:
    return GovernedAction(
        action_id=str(value["action_id"]),
        action_type=str(value["action_type"]),
        command_or_path=str(value["command_or_path"]),
        payload_hash=str(value["payload_hash"]),
        summary_spoken=str(value["summary_spoken"]),
        staged_by=principal_from_dict(value["staged_by"]),
        state=ActionState(str(value["state"])),
        created_at_epoch=float(value["created_at_epoch"]),
        lease_duration_sec=float(value["lease_duration_sec"]),
        approval_token=value.get("approval_token"),
        approved_by=(
            principal_from_dict(value["approved_by"]) if value.get("approved_by") else None
        ),
        execution_result=value.get("execution_result"),
        audit_scope=str(value.get("audit_scope", "local")),
    )


def principal_to_dict(principal: Principal) -> dict[str, str]:
    return {"principal_id": principal.principal_id, "role": principal.role.value}


def principal_from_dict(value: dict[str, Any]) -> Principal:
    return Principal(str(value["principal_id"]), PrincipalRole(str(value["role"])))


def voice_session_to_dict(session: VoiceSessionContext) -> dict[str, Any]:
    return {
        "session_id": session.session_id,
        "user_id": session.user_id,
        "current_repo": session.current_repo,
        "active_diff_id": session.active_diff_id,
        "focused_file": session.focused_file,
        "focused_section_index": session.focused_section_index,
        "staged_action_id": session.staged_action_id,
        "staged_action_grant": session.staged_action_grant,
        "dialogue_history": list(session.dialogue_history[-MAX_HISTORY_ENTRIES:]),
        "created_at": session.created_at.isoformat(),
    }


def voice_session_from_dict(value: dict[str, Any]) -> VoiceSessionContext:
    return VoiceSessionContext(
        session_id=str(value["session_id"]),
        user_id=str(value["user_id"]),
        current_repo=str(value["current_repo"]),
        active_diff_id=value.get("active_diff_id"),
        focused_file=value.get("focused_file"),
        focused_section_index=int(value.get("focused_section_index", 0)),
        staged_action_id=value.get("staged_action_id"),
        staged_action_grant=value.get("staged_action_grant"),
        dialogue_history=list(value.get("dialogue_history") or []),
        created_at=datetime.fromisoformat(str(value["created_at"])),
    )


def review_dialogue_to_dict(dialogue: ReviewDialogue) -> dict[str, Any]:
    undo = None
    if dialogue._undo:
        undo = {
            "state": dialogue._undo["state"].value,
            "file_index": int(dialogue._undo["file_index"]),
            "hunk_index": int(dialogue._undo["hunk_index"]),
            "line_index": int(dialogue._undo["line_index"]),
            "last_turn": turn_to_dict(dialogue._undo.get("last_turn")),
        }
    return {
        "session_id": dialogue.session_id,
        "state": dialogue.state.value,
        "report": report_to_dict(dialogue.report) if dialogue.report else None,
        "pull_request": snapshot_to_dict(dialogue.pull_request) if dialogue.pull_request else None,
        "file_index": dialogue.file_index,
        "hunk_index": dialogue.hunk_index,
        "line_index": dialogue.line_index,
        "speech_rate": dialogue.speech_rate,
        "pending_body": dialogue.pending_body,
        "last_turn": turn_to_dict(dialogue.last_turn),
        "last_outcome": dialogue.last_outcome,
        "history": list(dialogue.history[-MAX_HISTORY_ENTRIES:]),
        "undo": undo,
    }


def review_dialogue_from_dict(value: dict[str, Any]) -> ReviewDialogue:
    dialogue = ReviewDialogue(
        session_id=str(value["session_id"]),
        state=DialogueState(str(value.get("state", DialogueState.IDLE.value))),
        report=report_from_dict(value["report"]) if value.get("report") else None,
        pull_request=(
            snapshot_from_dict(value["pull_request"]) if value.get("pull_request") else None
        ),
        file_index=int(value.get("file_index", 0)),
        hunk_index=int(value.get("hunk_index", 0)),
        line_index=int(value.get("line_index", 0)),
        # A state saved before the single cursor may carry "spell_index"; it
        # is ignored, and line_index alone says where the listener is.
        speech_rate=float(value.get("speech_rate", 1.0)),
        pending_body=value.get("pending_body"),
        last_turn=turn_from_dict(value.get("last_turn")),
        last_outcome=value.get("last_outcome"),
        history=list(value.get("history") or []),
    )
    undo = value.get("undo")
    if undo:
        dialogue._undo = {
            "state": DialogueState(str(undo["state"])),
            "file_index": int(undo["file_index"]),
            "hunk_index": int(undo["hunk_index"]),
            "line_index": int(undo["line_index"]),
            "last_turn": turn_from_dict(undo.get("last_turn")),
        }
    return dialogue


def command_to_dict(command: Command | None) -> dict[str, Any] | None:
    if command is None:
        return None
    return {
        "name": command.name,
        "slots": command.slots,
        "raw": command.raw,
        "corrected": command.corrected,
    }


def command_from_dict(value: dict[str, Any] | None) -> Command | None:
    if value is None:
        return None
    return Command(
        name=str(value["name"]),
        slots=dict(value.get("slots") or {}),
        raw=str(value.get("raw", "")),
        corrected=bool(value.get("corrected", False)),
    )


def turn_to_dict(turn: DialogueTurn | None) -> dict[str, Any] | None:
    if turn is None:
        return None
    return {
        "understood": turn.understood,
        "readback": turn.readback,
        "spoken": turn.spoken,
        "state": turn.state.value,
        "earcon_type": turn.earcon_type.value if turn.earcon_type else None,
        "focus": turn.focus,
        "speech_rate": turn.speech_rate,
        "line": turn.line,
        "error": turn.error,
        "silent": turn.silent,
        "needs": turn.needs,
        "command": command_to_dict(turn.command),
    }


def turn_from_dict(value: dict[str, Any] | None) -> DialogueTurn | None:
    if value is None:
        return None
    return DialogueTurn(
        understood=str(value["understood"]),
        readback=str(value["readback"]),
        spoken=str(value["spoken"]),
        state=DialogueState(str(value["state"])),
        earcon_type=(EarconType(str(value["earcon_type"])) if value.get("earcon_type") else None),
        focus=dict(value.get("focus") or {}),
        speech_rate=float(value.get("speech_rate", 1.0)),
        line=value.get("line"),
        error=bool(value.get("error", False)),
        silent=bool(value.get("silent", False)),
        needs=value.get("needs"),
        command=command_from_dict(value.get("command")),
    )


def snapshot_to_dict(snapshot: PullRequestSnapshot) -> dict[str, Any]:
    return {
        "owner": snapshot.owner,
        "repo": snapshot.repo,
        "number": snapshot.number,
        "url": snapshot.url,
        "title": snapshot.title,
        "state": snapshot.state,
        "head_sha": snapshot.head_sha,
        "head_ref": snapshot.head_ref,
        "base_ref": snapshot.base_ref,
        "author": snapshot.author,
        "fetched_with_token": snapshot.fetched_with_token,
    }


def snapshot_from_dict(value: dict[str, Any]) -> PullRequestSnapshot:
    return PullRequestSnapshot(
        owner=str(value["owner"]),
        repo=str(value["repo"]),
        number=int(value["number"]),
        url=str(value["url"]),
        title=str(value.get("title", "")),
        state=str(value.get("state", "")),
        head_sha=str(value["head_sha"]),
        head_ref=str(value.get("head_ref", "")),
        base_ref=str(value.get("base_ref", "")),
        author=str(value.get("author", "")),
        diff="",
        fetched_with_token=bool(value.get("fetched_with_token", False)),
    )


def report_to_dict(report: SemanticDiffReport) -> dict[str, Any]:
    return {
        "total_files_changed": report.total_files_changed,
        "total_insertions": report.total_insertions,
        "total_deletions": report.total_deletions,
        "executive_spoken_summary": report.executive_spoken_summary,
        "category_breakdown": report.category_breakdown,
        "critical_findings": report.critical_findings,
        "sections": [section_to_dict(section) for section in report.sections],
        "synthesis_mode": report.synthesis_mode,
        "fallback_reason": report.fallback_reason,
    }


def report_from_dict(value: dict[str, Any]) -> SemanticDiffReport:
    return SemanticDiffReport(
        total_files_changed=int(value["total_files_changed"]),
        total_insertions=int(value["total_insertions"]),
        total_deletions=int(value["total_deletions"]),
        executive_spoken_summary=str(value["executive_spoken_summary"]),
        category_breakdown={str(k): int(v) for k, v in value["category_breakdown"].items()},
        critical_findings=[str(item) for item in value.get("critical_findings") or []],
        sections=[section_from_dict(item) for item in value.get("sections") or []],
        synthesis_mode=str(value.get("synthesis_mode", "heuristic-local")),
        fallback_reason=value.get("fallback_reason"),
    )


def section_to_dict(section: DiffSectionDigest) -> dict[str, Any]:
    return {
        "file_path": section.file_path,
        "symbol_name": section.symbol_name,
        "category": section.category.value,
        "significance": section.significance.value,
        "summary_spoken": section.summary_spoken,
        "added_count": section.added_count,
        "removed_count": section.removed_count,
        "security_flags": section.security_flags,
        "security_findings": section.security_findings,
        "hunks": [hunk_to_dict(hunk) for hunk in section.hunks],
    }


def section_from_dict(value: dict[str, Any]) -> DiffSectionDigest:
    return DiffSectionDigest(
        file_path=str(value["file_path"]),
        symbol_name=str(value.get("symbol_name", "")),
        category=ChangeCategory(str(value["category"])),
        significance=ChangeSignificance(str(value["significance"])),
        summary_spoken=str(value["summary_spoken"]),
        added_count=int(value["added_count"]),
        removed_count=int(value["removed_count"]),
        security_flags=[str(item) for item in value.get("security_flags") or []],
        security_findings=[str(item) for item in value.get("security_findings") or []],
        hunks=[hunk_from_dict(item) for item in value.get("hunks") or []],
    )


def hunk_to_dict(hunk: DiffHunk) -> dict[str, Any]:
    return {
        "old_start": hunk.old_start,
        "old_lines": hunk.old_lines,
        "new_start": hunk.new_start,
        "new_lines": hunk.new_lines,
        "header": hunk.header,
        "added_lines": hunk.added_lines,
        "removed_lines": hunk.removed_lines,
        "lines": [
            {"kind": line.kind, "text": line.text, "old_no": line.old_no, "new_no": line.new_no}
            for line in hunk.lines
        ],
    }


def hunk_from_dict(value: dict[str, Any]) -> DiffHunk:
    return DiffHunk(
        old_start=int(value["old_start"]),
        old_lines=int(value["old_lines"]),
        new_start=int(value["new_start"]),
        new_lines=int(value["new_lines"]),
        header=str(value.get("header", "")),
        added_lines=[str(item) for item in value.get("added_lines") or []],
        removed_lines=[str(item) for item in value.get("removed_lines") or []],
        lines=[
            DiffLine(
                kind=str(item["kind"]), text=str(item["text"]),
                old_no=(int(item["old_no"]) if item.get("old_no") is not None else None),
                new_no=(int(item["new_no"]) if item.get("new_no") is not None else None),
            )
            for item in value.get("lines") or []
        ],
    )


def audit_to_dict(record: AuditLogRecord) -> dict[str, Any]:
    return {
        "record_id": record.record_id,
        "action_id": record.action_id,
        "action_type": record.action_type,
        "command": record.command,
        "payload_hash": record.payload_hash,
        "approver_token_hash": record.approver_token_hash,
        "state": record.state.value,
        "execution_stdout": record.execution_stdout,
        "timestamp": record.timestamp,
        "staged_by": record.staged_by,
        "approved_by": record.approved_by,
        "audit_scope": record.audit_scope,
        "sequence": record.sequence,
        "previous_hash": record.previous_hash,
        "entry_hash": record.entry_hash,
    }


def audit_from_dict(value: dict[str, Any]) -> AuditLogRecord:
    return AuditLogRecord(
        record_id=str(value["record_id"]),
        action_id=str(value["action_id"]),
        action_type=str(value["action_type"]),
        command=str(value["command"]),
        payload_hash=str(value["payload_hash"]),
        approver_token_hash=str(value["approver_token_hash"]),
        state=ActionState(str(value["state"])),
        execution_stdout=str(value["execution_stdout"]),
        timestamp=str(value["timestamp"]),
        staged_by=str(value.get("staged_by", "unknown")),
        approved_by=str(value.get("approved_by", "unapproved")),
        audit_scope=str(value.get("audit_scope", "local")),
        sequence=int(value.get("sequence", -1)),
        previous_hash=str(value.get("previous_hash", "")),
        entry_hash=str(value.get("entry_hash", "")),
    )
