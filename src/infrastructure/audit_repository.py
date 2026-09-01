"""Infrastructure Adapter: Audit Log Repository."""
from typing import Dict, List
from src.domain.governed_action import AuditLogRecord


class InMemoryAuditRepository:
    def __init__(self):
        self._records: Dict[str, AuditLogRecord] = {}

    def append_audit_record(self, record: AuditLogRecord) -> None:
        self._records[record.record_id] = record

    def list_records(self) -> List[AuditLogRecord]:
        return list(self._records.values())

    def get_record(self, record_id: str) -> AuditLogRecord:
        return self._records.get(record_id)
