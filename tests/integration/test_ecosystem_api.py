"""Integration tests for Amazon Ecosystem Companion MCP endpoints in Volcan."""
from fastapi.testclient import TestClient

from src.interfaces.mcp_server import app

client = TestClient(app)

def test_ingest_bee_annotation_endpoint():
    resp = client.post(
        "/api/companions/ingest_bee_annotation",
        json={
            "speaker_id": "engineer_alexa",
            "transcript": "Spoken decision: use SSE transport for realtime diff streaming.",
            "pr_id": "PR-202"
        }
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["speaker_id"] == "engineer_alexa"
    assert data["pr_id"] == "PR-202"
    assert "spoken_digest" in data

def test_sync_firetv_wallboard_endpoint():
    resp = client.post(
        "/api/companions/sync_firetv_wallboard",
        json={
            "lease_id": "act_5544",
            "ttl_sec": 280,
            "security_flag": True,
            "dora_rating": "ELITE"
        }
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["rendered_at"] is not None
    assert data["device"] == "FIRE_TV_WALLBOARD"
    assert data["ttl_sec"] == 285 or data["ttl_sec"] == 280

def test_evaluate_ring_presence_endpoint():
    resp = client.post(
        "/api/companions/evaluate_ring_presence",
        json={
            "sensor_zone": "Backgate Camera",
            "active_lease_id": "act_5544"
        }
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["sanctuary_active"] is True
    assert data["action"] == "SUPPRESS_LOUD_CHIME"
