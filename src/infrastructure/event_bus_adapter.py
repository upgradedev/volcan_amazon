"""Amazon EventBridge & SQS Dead-Letter Queue (DLQ) Integration Adapter."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from typing import Dict, Any, List, Optional


@dataclass
class EventBridgeEnvelope:
    source: str
    detail_type: str
    detail: Dict[str, Any]
    event_bus_name: str = "default"
    time_iso: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AmazonEventBridgeAdapter:
    """Publishes decoupled telemetry events to EventBridge with SQS DLQ fallback."""

    def __init__(self, event_bus_name: str = "amazon-challenge-event-bus") -> None:
        self.event_bus_name = event_bus_name
        self.published_events: List[EventBridgeEnvelope] = []
        self.dlq_messages: List[Dict[str, Any]] = []

    def publish_event(self, source: str, detail_type: str, detail: Dict[str, Any]) -> EventBridgeEnvelope:
        """Publishes event onto the custom event bus."""
        envelope = EventBridgeEnvelope(
            source=source,
            detail_type=detail_type,
            detail=detail,
            event_bus_name=self.event_bus_name
        )
        self.published_events.append(envelope)
        return envelope

    def send_to_dead_letter_queue(self, original_event: Dict[str, Any], failure_reason: str) -> Dict[str, Any]:
        """Routes failed events to Amazon SQS Dead-Letter Queue (DLQ) for replay."""
        dlq_entry = {
            "dlq_timestamp": datetime.now(timezone.utc).isoformat(),
            "failure_reason": failure_reason,
            "original_payload": original_event,
            "max_receive_count": 3
        }
        self.dlq_messages.append(dlq_entry)
        return dlq_entry
