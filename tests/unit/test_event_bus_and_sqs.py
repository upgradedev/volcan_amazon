"""Unit tests for Amazon EventBridge & SQS Dead-Letter Queue adapter."""
import pytest
from src.infrastructure.event_bus_adapter import AmazonEventBridgeAdapter


def test_eventbridge_event_publishing():
    bus = AmazonEventBridgeAdapter()
    envelope = bus.publish_event("vesta.ring", "DoorbellRingEvent", {"device_id": "doorbell_front"})
    assert envelope.source == "vesta.ring"
    assert envelope.detail_type == "DoorbellRingEvent"
    assert envelope.detail["device_id"] == "doorbell_front"
    assert len(bus.published_events) == 1


def test_dead_letter_queue_routing():
    bus = AmazonEventBridgeAdapter()
    dlq = bus.send_to_dead_letter_queue({"event": "bad_payload"}, "RateLimitExceeded")
    assert dlq["failure_reason"] == "RateLimitExceeded"
    assert dlq["max_receive_count"] == 3
    assert len(bus.dlq_messages) == 1
