"""The default Origin allowlist follows the port the server binds.

A review served the page on port 8742 and pressed "Run a real MCP handshake":
the server refused its own page with a 403, because the default allowlist named
port 8000 only, and the page printed "The handshake failed: ." with the reason
dropped. One setting now moves the bind port and the allowlist together, and
the page prints the server's own refusal sentence.
"""
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.interfaces import composition
from src.interfaces.mcp_server import _main, app

INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
PAGE = Path(__file__).resolve().parents[2] / "docs" / "index.html"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("VOLCAN_ALLOWED_ORIGINS", raising=False)
    return TestClient(app)


def test_the_default_port_keeps_the_8000_allowlist(client, monkeypatch):
    monkeypatch.delenv("VOLCAN_PORT", raising=False)
    assert composition.allowed_origins() == {"http://127.0.0.1:8000", "http://localhost:8000"}
    ok = client.post("/mcp", headers={"Origin": "http://127.0.0.1:8000"}, json=INIT)
    assert ok.status_code == 200


def test_a_configured_port_allows_the_page_it_serves(client, monkeypatch):
    monkeypatch.setenv("VOLCAN_PORT", "8743")
    assert composition.allowed_origins() == {"http://127.0.0.1:8743", "http://localhost:8743"}
    for origin in ("http://127.0.0.1:8743", "http://localhost:8743"):
        assert client.post("/mcp", headers={"Origin": origin}, json=INIT).status_code == 200
    # The old port is no longer on the list once the server moved.
    moved = client.post("/mcp", headers={"Origin": "http://127.0.0.1:8000"}, json=INIT)
    assert moved.status_code == 403


def test_a_foreign_origin_is_still_refused_on_any_port(client, monkeypatch):
    monkeypatch.setenv("VOLCAN_PORT", "8743")
    for origin in ("https://evil.example.com", "http://127.0.0.1:8744", "http://evil.localhost:8743"):
        refused = client.post("/mcp", headers={"Origin": origin}, json=INIT)
        assert refused.status_code == 403, origin
        assert "VOLCAN_ALLOWED_ORIGINS" in refused.json()["detail"]


def test_an_explicit_allowlist_still_wins_over_the_port(client, monkeypatch):
    monkeypatch.setenv("VOLCAN_PORT", "8743")
    monkeypatch.setenv("VOLCAN_ALLOWED_ORIGINS", "https://volcan.example.com")
    assert composition.allowed_origins() == {"https://volcan.example.com"}


@pytest.mark.parametrize("raw", ["eighty", "0", "70000"])
def test_a_bad_port_is_refused_with_a_sentence(monkeypatch, raw):
    monkeypatch.setenv("VOLCAN_PORT", raw)
    with pytest.raises(RuntimeError, match="VOLCAN_PORT"):
        composition.local_port()


def test_the_port_flag_moves_the_bind_port_and_the_allowlist(monkeypatch):
    seen = {}
    # setenv first so the value _main writes is rolled back after the test.
    monkeypatch.setenv("VOLCAN_PORT", "8000")
    monkeypatch.delenv("VOLCAN_ALLOWED_ORIGINS", raising=False)
    import uvicorn
    # _main warms the credential cache in a thread; keep that off the network here.
    monkeypatch.setattr(composition.bedrock_adapter, "credentials_present", lambda: False)
    monkeypatch.setattr(uvicorn, "run", lambda app, host, port: seen.update(host=host, port=port))
    _main(["--port", "8743"])
    assert seen == {"host": "127.0.0.1", "port": 8743}
    assert "http://127.0.0.1:8743" in composition.allowed_origins()


def test_the_page_prints_the_servers_refusal_instead_of_dropping_it():
    script = PAGE.read_text(encoding="utf-8")
    rpc = script.split("async function rpc(", 1)[1].split("async function runMcpHandshake", 1)[0]
    assert "response.ok" in rpc, "a refused handshake must be detected by its status"
    assert "body.detail" in rpc, "the server's own reason must reach the page"
    assert not re.search(r'"The handshake failed: " \+ error\.message \+ "\."', script)
