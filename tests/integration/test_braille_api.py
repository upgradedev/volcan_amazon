"""Integration tests for Braille accessibility MCP endpoints in Volcan."""
from fastapi.testclient import TestClient
from src.interfaces.mcp_server import app

client = TestClient(app)


def test_translate_text_to_braille_endpoint():
    resp = client.post(
        "/mcp/tools/braille/translate_text",
        json={"text": "Aws Bedrock 2026"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["original_text"] == "Aws Bedrock 2026"
    assert "braille_unicode" in data
    assert len(data["braille_unicode"]) > 0


def test_digest_diff_to_braille_endpoint():
    resp = client.post(
        "/mcp/tools/braille/diff_digest",
        json={
            "raw_diff": "+ return KMS_KEY_ID\n- return hardcoded_secret",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "braille_summary" in data
    assert data["additions"] == 1
    assert data["deletions"] == 1
    assert len(data["lines"]) == 2
