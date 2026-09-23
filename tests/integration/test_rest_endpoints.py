"""Integration tests for the REST surface at /api (this surface is not MCP)."""
from fastapi.testclient import TestClient

from src.interfaces.mcp_protocol import PROTOCOL_VERSION
from src.interfaces.mcp_server import app

client = TestClient(app)

SAMPLE_DIFF = """diff --git a/src/auth.py b/src/auth.py
--- a/src/auth.py
+++ b/src/auth.py
@@ -1 +1,2 @@
+import hmac
"""


def test_health_endpoint_describes_both_surfaces():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["mcp"]["protocol_version"] == PROTOCOL_VERSION
    assert data["mcp"]["endpoint"] == "/mcp"
    assert data["mcp"]["transport"] == "Streamable HTTP"
    assert data["rest_prefix"] == "/api"
    assert isinstance(data["bedrock_model_path"], dict)


def test_digest_reports_which_synthesis_path_ran():
    response = client.post("/api/digest_semantic_diff", json={"raw_diff": SAMPLE_DIFF, "level": 0})
    assert response.status_code == 200
    data = response.json()
    assert "voice_summary" in data
    assert data["total_files"] == 1
    assert data["synthesis_mode"] in {"heuristic-local", "bedrock"}
    assert len(data["earcon"]["wav_base64"]) > 50

    # A mode without a reason makes a reviewer guess. Exactly one of these two
    # states is legal: a model answered, or the response says why none did.
    assert "synthesis_fallback_reason" in data
    if data["synthesis_mode"] == "heuristic-local":
        assert data["synthesis_fallback_reason"], "an unexplained fallback is not acceptable"
    else:
        assert data["synthesis_fallback_reason"] is None


def test_drill_down_section():
    response = client.post("/api/drill_down_section", json={"raw_diff": SAMPLE_DIFF, "section_index": 0})
    assert response.status_code == 200
    data = response.json()
    assert "src/auth.py" in data["spoken_text"]
    assert "category" in data


def test_drill_down_out_of_bounds_is_404():
    response = client.post("/api/drill_down_section", json={"raw_diff": SAMPLE_DIFF, "section_index": 7})
    assert response.status_code == 404


def test_stage_then_confirm_then_audit():
    stage = client.post("/api/stage_governed_action", json={
        "action_id": "rest-act-101",
        "action_type": "RUN_TESTS",
        "command": "pytest tests/unit",
        "summary_spoken": "Run the unit suite",
    })
    assert stage.status_code == 200
    staged = stage.json()
    assert staged["state"] == "PENDING_APPROVAL"
    assert staged["plan"]["allowed"] is True
    assert staged["plan"]["executed"] is False

    confirm = client.post("/api/confirm_action", json={
        "action_id": "rest-act-101",
        "approval_grant": staged["approval_grant"],
        "approver_id": "reviewer-1",
    })
    assert confirm.status_code == 200
    assert confirm.json()["approved"] is True
    assert confirm.json()["status"] == "PLANNED"

    audit = client.get("/api/audit_log")
    assert audit.status_code == 200
    assert audit.json()["total_records"] >= 1


def test_play_earcon_returns_a_wav_stream():
    response = client.post("/api/play_earcon", json={"earcon_type": "DIFF_READY"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.content.startswith(b"RIFF")


def test_ast_completeness_endpoint_reports_a_real_syntax_error():
    good = client.post("/api/ast/check_completeness", json={"source_code": "def f():\n    return 1\n"})
    assert good.json()["is_valid_ast"] is True
    assert good.json()["function_count"] == 1

    bad = client.post("/api/ast/check_completeness", json={"source_code": "def f(:\n"})
    assert bad.json()["is_valid_ast"] is False
    assert "SyntaxError" in bad.json()["syntax_error_message"]


def test_root_and_demo_serve_the_single_companion_document():
    root = client.get("/")
    demo = client.get("/demo")
    assert root.status_code == 200
    assert demo.status_code == 200
    assert root.text == demo.text
    assert "Volcan" in root.text
