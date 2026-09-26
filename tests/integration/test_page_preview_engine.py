"""The companion page's on-load preview can never start a billed model call.

The page draws the default patch's real answer as soon as it loads. That
request names ``engine: local``. These tests prove the local engine answers it
even where a model call would otherwise be attempted, that the reason printed
is the product's own sentence, and that the MCP tool does not publish the field.
"""
import asyncio

from fastapi.testclient import TestClient

from src.application.digest_diff_use_case import LOCAL_ENGINE_REQUESTED, DigestDiffUseCase
from src.infrastructure.bedrock_adapter import MODE_HEURISTIC, BedrockSynthesisAdapter
from src.interfaces import composition
from src.interfaces.mcp_server import app
from src.interfaces.mcp_tools import build_tool_registry

PATCH = (
    "diff --git a/src/auth/permissions.py b/src/auth/permissions.py\n"
    "--- a/src/auth/permissions.py\n"
    "+++ b/src/auth/permissions.py\n"
    "@@ -12,7 +12,7 @@ def can_delete_workspace(user, workspace):\n"
    "     if workspace.locked:\n"
    "         return False\n"
    "-    return user.role == \"admin\"\n"
    "+    return user.role != \"admin\"\n"
)


class _NoModel:
    """A synthesis port whose model path fails the test if it is ever reached."""

    def __init__(self):
        self.model_calls = 0
        self._local = BedrockSynthesisAdapter()

    async def summarize_diff(self, raw_diff, sections):
        self.model_calls += 1
        raise AssertionError("the model path was reached")

    def summarize_locally(self, raw_diff, sections, reason):
        return self._local.summarize_locally(raw_diff, sections, reason)


def test_the_local_engine_answers_without_reaching_the_model_path():
    port = _NoModel()
    report = asyncio.run(DigestDiffUseCase(port).execute(PATCH, engine="local"))
    assert port.model_calls == 0
    assert report.synthesis_mode == MODE_HEURISTIC
    assert report.fallback_reason == LOCAL_ENGINE_REQUESTED
    assert report.critical_findings, "the deterministic finding must still be named"


def test_the_adapter_builds_no_client_when_asked_for_the_local_engine(monkeypatch):
    built = []
    adapter = BedrockSynthesisAdapter(client_factory=lambda: built.append(1))
    monkeypatch.setattr(BedrockSynthesisAdapter, "credentials_present", lambda self: True)
    report = adapter.summarize_locally(PATCH, [], LOCAL_ENGINE_REQUESTED)
    assert built == []
    assert adapter.last_fallback_reason is None, "nothing failed, so no failure is recorded"
    assert report.fallback_reason == LOCAL_ENGINE_REQUESTED


def test_the_rest_route_honours_engine_local_where_a_model_would_be_attempted(monkeypatch):
    attempts = []

    async def model(raw_diff, sections):
        attempts.append(raw_diff)
        raise AssertionError("a page view reached the model path")

    monkeypatch.setattr(composition.bedrock_adapter, "summarize_diff", model)
    client = TestClient(app)
    response = client.post("/api/digest_semantic_diff",
                           json={"raw_diff": PATCH, "level": 0, "engine": "local"})
    assert response.status_code == 200
    body = response.json()
    assert attempts == []
    assert body["synthesis_mode"] == MODE_HEURISTIC
    assert body["synthesis_fallback_reason"] == LOCAL_ENGINE_REQUESTED
    assert body["earcon"]["type"] == "SECURITY_FINDING"


def test_an_unknown_engine_is_refused_and_the_default_still_attempts_the_model(monkeypatch):
    attempts = []
    local = BedrockSynthesisAdapter()

    async def model(raw_diff, sections):
        attempts.append(raw_diff)
        return local.summarize_locally(raw_diff, sections, "stub")

    monkeypatch.setattr(composition.bedrock_adapter, "summarize_diff", model)
    client = TestClient(app)
    refused = client.post("/api/digest_semantic_diff",
                          json={"raw_diff": PATCH, "engine": "bedrock-please"})
    assert refused.status_code == 422
    assert client.post("/api/digest_semantic_diff", json={"raw_diff": PATCH}).status_code == 200
    assert len(attempts) == 1, "a request that names no engine keeps today's behaviour"


def test_the_mcp_tool_does_not_publish_the_engine_field():
    entry = [tool for tool in build_tool_registry().catalog()
             if tool["name"] == "digest_semantic_diff"]
    assert entry, "the digest tool is missing"
    assert "engine" not in entry[0]["inputSchema"].get("properties", {})
    assert "raw_diff" in entry[0]["inputSchema"]["properties"]
