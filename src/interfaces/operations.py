"""Interfaces Layer: operations shared by the REST and MCP surfaces.

Each function here runs one application operation and returns a plain
dictionary. The REST routes serialise it directly; the MCP tool handlers wrap
it in content blocks. Both surfaces therefore execute identical logic, and a
behaviour that appears on one cannot silently differ on the other.

A ``_wav`` key carries raw audio to the caller that wants it. REST strips it;
MCP turns it into an audio content block.
"""
import base64
from typing import Any

from src.application.durable_state import review_audit_scope
from src.application.public_audit import (
    PUBLIC_AUDIT_LIMIT,
    PUBLIC_DEMO_AUDIT_SCOPE,
    PUBLIC_VIEW_NOTE,
    public_record_view,
)
from src.application.review_authorization import current_review_principal
from src.domain.governed_action import AuditLogRecord, Principal
from src.domain.semantic_diff import category_words, line_counts
from src.domain.sonification import EarconType, earcon_for_report, earcon_for_section
from src.domain.spoken_form import speakable
from src.interfaces.composition import (
    audit_repo,
    digest_use_case,
    dry_run_executor,
    governed_use_case,
    sonify_use_case,
)
from src.interfaces.dto import (
    ConfirmActionRequest,
    DigestRequest,
    DrillDownRequest,
    StageActionRequest,
)


async def op_digest(req: DigestRequest, engine: str = "auto") -> dict[str, Any]:
    report = await digest_use_case.execute(req.raw_diff, engine=engine)
    # The cue carries the verdict, so it is read off the report rather than
    # fixed at the call site. A benign patch and a security-sensitive one must
    # not return the same bytes; tests/unit/test_earcon_encodes_the_verdict.py
    # compares the two payloads.
    cue, wav_bytes = sonify_use_case.execute(earcon_for_report(report))
    return {
        "voice_summary": report.to_voice_summary(level=req.level),
        # The same sentence as a speech engine should say it: code operators
        # named ("not equals" for !=), so a synthesiser that drops or slurs a
        # symbol cannot turn the finding into its opposite. The display text
        # above keeps the literal code, as does the Braille.
        "voice_summary_for_speech": speakable(report.to_voice_summary(level=req.level)),
        "synthesis_mode": report.synthesis_mode,
        # Null when a model answered. Otherwise a bounded product-owned category
        # explains why the deterministic path answered. Provider payloads can
        # contain cloud identity and request identifiers and never cross the API.
        "synthesis_fallback_reason": report.fallback_reason,
        "total_files": report.total_files_changed,
        "insertions": report.total_insertions,
        "deletions": report.total_deletions,
        "category_breakdown": report.category_breakdown,
        "critical_findings": report.critical_findings,
        "earcon": {
            "type": cue.earcon_type.value,
            "spoken_fallback": cue.spoken_fallback,
            "wav_base64": base64.b64encode(wav_bytes).decode("ascii"),
        },
        "_wav": wav_bytes,
    }


async def op_drill_down(req: DrillDownRequest) -> dict[str, Any]:
    report = await digest_use_case.execute(req.raw_diff)
    if req.section_index < 0 or req.section_index >= len(report.sections):
        raise IndexError(
            f"Section index {req.section_index} is out of bounds; the patch has "
            f"{len(report.sections)} sections."
        )
    sec = report.sections[req.section_index]
    cue, wav_bytes = sonify_use_case.execute(earcon_for_section(sec))
    # Words a listener hears, not identifiers: "business logic, low
    # significance", and counts that agree with their noun. The raw enum
    # values stay in the category and significance fields below.
    spoken = (
        f"Inspecting {sec.file_path}: {category_words(sec.category)}, "
        f"{sec.significance.value.lower()} significance. "
        f"{line_counts(sec.added_count, sec.removed_count)}."
    )
    if sec.security_findings:
        spoken += " Security alert: " + " ".join(
            f"{finding}." for finding in sec.security_findings
        )
    elif sec.security_flags:
        spoken += f" Security alert: Flagged for {', '.join(sec.security_flags)}."
    return {
        "spoken_text": spoken,
        "spoken_text_for_speech": speakable(spoken),
        "file_path": sec.file_path,
        "category": sec.category.value,
        "significance": sec.significance.value,
        "security_flags": sec.security_flags,
        "security_findings": sec.security_findings,
        "earcon": {
            "type": cue.earcon_type.value,
            "spoken_fallback": cue.spoken_fallback,
            "wav_base64": base64.b64encode(wav_bytes).decode("ascii"),
        },
        "_wav": wav_bytes,
    }


def op_stage_action(req: StageActionRequest) -> dict[str, Any]:
    ticket = governed_use_case.stage_action(
        req.action_id, req.action_type, req.command, req.summary_spoken, req.lease_sec,
        staged_by=Principal.agent(req.staged_by),
    )
    plan = dry_run_executor.plan(req.command)
    cue, wav_bytes = sonify_use_case.execute(EarconType.GOVERNANCE_CHALLENGE)
    return {
        "action_id": ticket.action.action_id,
        "state": ticket.action.state.value,
        "payload_hash": ticket.action.payload_hash,
        "approval_grant": ticket.grant,
        "expires_at_epoch": ticket.expires_at_epoch,
        "lease_sec": req.lease_sec,
        "plan": plan.to_dict(),
        "spoken_prompt": (
            f"Volcan staged action: {ticket.action.summary_spoken}. "
            "A human must approve it with the authorization grant before the lease expires."
        ),
        "earcon": {
            "type": cue.earcon_type.value,
            "spoken_fallback": cue.spoken_fallback,
            "wav_base64": base64.b64encode(wav_bytes).decode("ascii"),
        },
        "_wav": wav_bytes,
    }


async def op_confirm_action(req: ConfirmActionRequest) -> dict[str, Any]:
    outcome = await governed_use_case.confirm_and_execute(
        req.action_id, req.approval_grant, approver=Principal.human(req.approver_id),
    )
    earcon = EarconType.ACTION_COMMITTED if outcome.approved else EarconType.TEST_FAILED
    cue, wav_bytes = sonify_use_case.execute(earcon)
    return {
        "approved": outcome.approved,
        "status": "PLANNED" if outcome.approved else "REFUSED",
        "output": outcome.output,
        "refusal_code": outcome.refusal_code,
        "refusal_detail": outcome.refusal_detail,
        "spoken_text": outcome.spoken_reason if outcome.refused else outcome.output,
        "earcon": {
            "type": cue.earcon_type.value,
            "spoken_fallback": cue.spoken_fallback,
            "wav_base64": base64.b64encode(wav_bytes).decode("ascii"),
        },
        "_wav": wav_bytes,
    }


def _full_record_view(r: AuditLogRecord) -> dict[str, Any]:
    return {
        "id": r.record_id,
        "action": r.action_id,
        "action_type": r.action_type,
        "command": r.command,
        "payload_hash": r.payload_hash,
        "state": r.state.value,
        # What the release produced, in the words the executor used.
        # For a review this is where "dry run, not sent" lives.
        "outcome": r.execution_stdout,
        "staged_by": r.staged_by,
        "approved_by": r.approved_by,
        "timestamp": r.timestamp,
    }


def op_audit_log() -> dict[str, Any]:
    """The audit trail this caller may read.

    Process memory: every record this process sealed, as before. Durable
    mode: anyone gets the newest part of the public demo chain with
    caller-written text withheld; a roster credential adds that reviewer's
    own review chains in full. No caller names a scope, and a credential that
    does not match the roster is treated as no credential.
    """
    if not getattr(audit_repo, "is_durable", False):
        records = audit_repo.list_records()
        return {
            "uri": "volcan://governance/audit_log",
            "mimeType": "application/json",
            "view": "process_memory",
            "total_records": len(records),
            "records": [_full_record_view(r) for r in records],
        }

    public = audit_repo.list_recent(PUBLIC_DEMO_AUDIT_SCOPE, PUBLIC_AUDIT_LIMIT)
    rows = [(r.timestamp, public_record_view(r)) for r in public]
    principal = current_review_principal.get()
    if principal is not None:
        scopes = [
            review_audit_scope(principal.identity, repository)
            for repository in principal.repositories
        ]
        rows += [
            (r.timestamp, {**_full_record_view(r), "chain": "reviewer", "sequence": r.sequence})
            for r in audit_repo.list_records(scopes)
        ]
    # Oldest first, as in process-memory mode; the page reverses for display.
    rows.sort(key=lambda row: row[0])
    return {
        "uri": "volcan://governance/audit_log",
        "mimeType": "application/json",
        "view": "public_and_reviewer" if principal is not None else "public",
        "note": PUBLIC_VIEW_NOTE,
        "total_records": len(rows),
        "public_chain_records": audit_repo.record_count(PUBLIC_DEMO_AUDIT_SCOPE),
        "public_records_shown_limit": PUBLIC_AUDIT_LIMIT,
        "records": [row[1] for row in rows],
    }
