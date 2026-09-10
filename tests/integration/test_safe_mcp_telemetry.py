"""Exercise the real MCP boundary and capture its actual logger output locally."""
import json

from fastapi.testclient import TestClient

from src.interfaces.mcp_protocol import PROTOCOL_VERSION
from src.interfaces.mcp_server import app


def test_mcp_emits_measured_emf_without_request_or_patch_content(caplog):
    secret = "synthetic_mcp_secret_+302101234567_api_key"
    patch = ("diff --git a/demo.py b/demo.py\n--- a/demo.py\n+++ b/demo.py\n"
             "@@ -1 +1,2 @@\n+password = '" + secret + "'\n")
    client = TestClient(app)
    initialized = client.post("/mcp", json={
        "jsonrpc": "2.0", "id": secret, "method": "initialize", "params": {
            "protocolVersion": PROTOCOL_VERSION, "capabilities": {},
            "clientInfo": {"name": secret, "version": "1"},
        },
    })
    assert initialized.status_code == 200
    session = initialized.headers["Mcp-Session-Id"]
    result = client.post("/mcp", headers={"Mcp-Session-Id": session,
                         "MCP-Protocol-Version": PROTOCOL_VERSION}, json={
        "jsonrpc": "2.0", "id": secret, "method": "tools/call", "params": {
            "name": "digest_semantic_diff", "arguments": {"raw_diff": patch, "level": 0},
            "actor": secret, "tenant": secret, "nested": {"api_key": secret},
        },
    })
    assert result.status_code == 200
    assert result.json()["result"]["isError"] is False
    messages = [r.getMessage() for r in caplog.records if r.name == "volcan-voice-ide"]
    assert len(messages) == 1
    assert secret not in messages[0]
    assert session not in messages[0]
    payload = json.loads(messages[0])
    metric = payload["McpToolDurationMs"]
    assert type(metric) is float and metric >= 0
    assert payload["AuditEvents"] == [{
        "actor": "mcp-client", "action": "tools/call",
        "details": {"tool": "digest_semantic_diff", "duration_ms": metric},
    }]
    directive = payload["_aws"]["CloudWatchMetrics"][0]
    assert directive["Namespace"] == "Volcan/VoiceIDE"
    assert {"Name": "McpToolDurationMs", "Unit": "Milliseconds"} in directive["Metrics"]
