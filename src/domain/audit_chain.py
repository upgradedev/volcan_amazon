"""Domain: a tamper-evident hash chain over audit records.

Each sealed record carries the hash of the record before it, so editing any
field of any earlier entry changes that entry's hash and breaks every link
after it. That is what "tamper-evident" means here, stated precisely:

* it **detects** an edit to a stored record, and names the first broken link
* it does **not** prevent an edit, and it does not stop someone who can rewrite
  the whole chain from re-sealing it end to end

Making it tamper-proof would need the head hash published somewhere the writer
cannot reach. Volcan does not do that, and does not claim to.
"""
import hashlib
import json
from dataclasses import dataclass, replace

from src.domain.governed_action import AuditLogRecord

GENESIS_HASH = "0" * 64


@dataclass(frozen=True)
class ChainVerdict:
    intact: bool
    verified_entries: int
    broken_at_sequence: int | None = None
    detail: str = ""


def _fingerprint(record: AuditLogRecord, previous_hash: str, sequence: int) -> str:
    """Hashes every field that carries meaning, plus the link to the entry before."""
    payload = json.dumps(
        {
            "sequence": sequence,
            "previous_hash": previous_hash,
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
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def seal(record: AuditLogRecord, previous_hash: str, sequence: int) -> AuditLogRecord:
    """Returns the record with its position and its link to the previous entry."""
    return replace(
        record,
        sequence=sequence,
        previous_hash=previous_hash,
        entry_hash=_fingerprint(record, previous_hash, sequence),
    )


def verify_chain(records: list[AuditLogRecord]) -> ChainVerdict:
    """Recomputes every link and reports the first that does not match."""
    previous = GENESIS_HASH
    for expected_sequence, record in enumerate(records):
        if record.sequence != expected_sequence:
            return ChainVerdict(
                False, expected_sequence, expected_sequence,
                f"entry {record.record_id} claims sequence {record.sequence}, "
                f"expected {expected_sequence}",
            )
        if record.previous_hash != previous:
            return ChainVerdict(
                False, expected_sequence, expected_sequence,
                f"entry {record.record_id} links to {record.previous_hash[:12]}, "
                f"expected {previous[:12]}",
            )
        recomputed = _fingerprint(record, previous, expected_sequence)
        if recomputed != record.entry_hash:
            return ChainVerdict(
                False, expected_sequence, expected_sequence,
                f"entry {record.record_id} content does not match its seal; "
                "a stored field was altered after it was written",
            )
        previous = record.entry_hash

    return ChainVerdict(True, len(records), None, f"head hash {previous[:16]}")
