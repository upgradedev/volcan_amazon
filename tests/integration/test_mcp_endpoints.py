"""Integration tests for Volcan FastMCP HTTP Endpoints."""
from fastapi.testclient import TestClient

from src.interfaces.mcp_server import app

client = TestClient(app)

SAMPLE_DIFF = """diff --git a/src/auth.py b/src/auth.py
--- a/src/auth.py
+++ b/src/auth.py
@@ -1 +1,2 @@
+import hmac
"""


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["mcp_spec"] == "2025-11-25"


def test_digest_semantic_diff_tool():
    response = client.post("/mcp/tools/digest_semantic_diff", json={"raw_diff": SAMPLE_DIFF, "level": 0})
    assert response.status_code == 200
    data = response.json()
    assert "voice_summary" in data
    assert data["total_files"] == 1
    assert "earcon" in data
    assert len(data["earcon"]["wav_base64"]) > 50


def test_drill_down_section_tool():
    response = client.post("/mcp/tools/drill_down_section", json={"raw_diff": SAMPLE_DIFF, "section_index": 0})
    assert response.status_code == 200
    data = response.json()
    assert "src/auth.py" in data["spoken_text"]
    assert "category" in data


def test_governed_action_staging_and_confirmation_flow():
    # 1. Stage Action
    stage_res = client.post("/mcp/tools/stage_governed_action", json={
        "action_id": "mcp-act-101",
        "action_type": "DEPLOY",
        "command": "deploy staging",
        "summary_spoken": "Deploy branch to staging cluster"
    })
    assert stage_res.status_code == 200
    stage_data = stage_res.json()
    assert stage_data["state"] == "PENDING_APPROVAL"

    # 2. Confirm Action
    confirm_res = client.post("/mcp/tools/confirm_action", json={
        "action_id": "mcp-act-101",
        "voice_token": "ALEX_VOICE_SIG_987"
    })
    assert confirm_res.status_code == 200
    confirm_data = confirm_res.json()
    assert confirm_data["status"] == "EXECUTED"

    # 3. Check Audit Resource
    audit_res = client.get("/mcp/resources/audit_log")
    assert audit_res.status_code == 200
    audit_data = audit_res.json()
    assert audit_data["total_records"] >= 1


def test_play_earcon_binary_stream():
    response = client.post("/mcp/tools/play_earcon", json={"earcon_type": "DIFF_READY"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.content.startswith(b"RIFF")
