"""Infrastructure Adapter: an append-only, hash-chained audit repository.

Records are kept in process memory and are lost when the process exits, which
is stated in the README. What survives inside a run is the chain: every record
is sealed with the hash of the record before it, so an edit to any stored entry
is detectable by ``verify_integrity``.
"""
from src.domain.audit_chain import GENESIS_HASH, ChainVerdict, seal, verify_chain
from src.domain.governed_action import AuditLogRecord


class InMemoryAuditRepository:
    def __init__(self) -> None:
        self._records: list[AuditLogRecord] = []

    def append_audit_record(self, record: AuditLogRecord) -> AuditLogRecord:
        previous_hash = self._records[-1].entry_hash if self._records else GENESIS_HASH
        sealed = seal(record, previous_hash, len(self._records))
        self._records.append(sealed)
        return sealed

    def list_records(self) -> list[AuditLogRecord]:
        return list(self._records)

    def get_record(self, record_id: str) -> AuditLogRecord | None:
        return next((r for r in self._records if r.record_id == record_id), None)

    def verify_integrity(self) -> ChainVerdict:
        return verify_chain(self._records)

    @property
    def head_hash(self) -> str:
        return self._records[-1].entry_hash if self._records else GENESIS_HASH
