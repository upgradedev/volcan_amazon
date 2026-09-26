"""The first thing a listener hears is the finding, not the category.

A review pressed the product's own preset and heard "Security-sensitive
changes in src/auth/permissions.py. Modified 1 file with 1 addition and 1
deletion. Note: 1 critical finding requires your verification." The inverted
comparison, the one change no keyword matcher can see, was never spoken. The
level 0 summary is what the page speaks, what the MCP tool returns as text and
what the dialogue's summary turn says, so the order is fixed here, once.
"""
import asyncio

from fastapi.testclient import TestClient

from src.application.digest_diff_use_case import DigestDiffUseCase
from src.infrastructure.bedrock_adapter import BedrockSynthesisAdapter
from src.interfaces.mcp_server import app

INVERTED = """diff --git a/src/auth/permissions.py b/src/auth/permissions.py
--- a/src/auth/permissions.py
+++ b/src/auth/permissions.py
@@ -10,3 +10,3 @@ def can_delete_workspace(user, workspace):
-    return user.role == "admin"
+    return user.role != "admin"
"""

CLEAN = """diff --git a/src/app/greeting.py b/src/app/greeting.py
--- a/src/app/greeting.py
+++ b/src/app/greeting.py
@@ -1,2 +1,2 @@ def greet(name):
-    return "Hello " + name
+    return f"Hello, {name}"
"""

FINDING = "an authorization comparison was inverted"


def _report(diff):
    return asyncio.run(DigestDiffUseCase(BedrockSynthesisAdapter()).execute(diff, engine="local"))


def test_level_zero_opens_with_the_finding_and_keeps_the_counts():
    summary = _report(INVERTED).to_voice_summary(level=0)
    assert summary.startswith("In src/auth/permissions.py, " + FINDING), summary
    assert "Modified 1 file with 1 addition and 1 deletion." in summary
    assert summary.endswith("Note: 1 critical finding requires your verification.")
    assert ".." not in summary


def test_a_clean_change_says_no_finding_first():
    summary = _report(CLEAN).to_voice_summary(level=0)
    assert "critical finding" not in summary
    assert summary.startswith("Changes are")


def test_the_rest_endpoint_and_the_local_engine_speak_it_first():
    body = TestClient(app).post(
        "/api/digest_semantic_diff", json={"raw_diff": INVERTED, "level": 0, "engine": "local"},
    ).json()
    assert body["voice_summary"].startswith("In src/auth/permissions.py, " + FINDING)
    assert body["voice_summary"].split(". ")[0] + "." == body["critical_findings"][0] or \
        body["voice_summary"].startswith(body["critical_findings"][0])
