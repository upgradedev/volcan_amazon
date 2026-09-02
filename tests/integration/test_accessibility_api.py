"""Integration tests for Switch and Haptic accessibility endpoints."""
from fastapi.testclient import TestClient
from src.interfaces.mcp_server import app

client = TestClient(app)


def test_process_switch_pulse_endpoint():
    resp = client.post(
        "/mcp/tools/accessibility/process_switch_pulse",
        json={
            "input_type": "SIP_AND_PUFF",
            "signal_strength": 0.85,
            "duration_ms": 200,
            "is_long_press": False,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["resolved_action"] == "CONFIRM_LEASE"
    assert data["input_type"] == "SIP_AND_PUFF"


def test_get_haptic_profile_endpoint():
    resp = client.post(
        "/mcp/tools/accessibility/get_haptic_profile",
        json={"event_type": "SECURITY_FLAG"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["pattern_type"] == "SECURITY_ALERT"
    assert "visual_caption" in data
    assert len(data["steps"]) == 5
