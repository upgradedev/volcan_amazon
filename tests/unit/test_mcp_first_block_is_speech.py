"""The first MCP text block is the sentence a voice should say.

A voice client reads a tool's first text block aloud. Until 2026-10-05 the
digest, drill-down and review-turn tools put the literal sentence there,
"user.role == 'admin' became user.role != 'admin'", while the speakable form
with each operator named sat only inside the JSON detail block. A voice that
drops or slurs "!=" turns that finding into its opposite. The first block now
carries the ``*_for_speech`` form; the literal code stays in the detail block,
so a client that shows code loses nothing.
"""
import asyncio
import json
import re

from src.interfaces.dto import DigestRequest, DrillDownRequest, ReviewTurnRequest
from src.interfaces.mcp_tools import tool_digest, tool_drill_down, tool_review_turn

INVERTED = """diff --git a/src/auth/permissions.py b/src/auth/permissions.py
--- a/src/auth/permissions.py
+++ b/src/auth/permissions.py
@@ -10,3 +10,3 @@ def can_delete_workspace(user, workspace):
-    return user.role == "admin"
+    return user.role != "admin"
"""

#: Every operator spoken_form names, longest first so the message is exact.
BARE_OPERATORS = re.compile(r"!==|===|!=|==|<=|>=|&&|\|\|")


def _first_text(blocks):
    return next(block["text"] for block in blocks if block["type"] == "text")


def _detail(blocks):
    return json.loads(blocks[-1]["text"])


def _assert_no_bare_operator(text):
    found = BARE_OPERATORS.findall(text)
    assert not found, f"the first text block carries bare operators {found}: {text!r}"


def test_the_digest_tool_speaks_named_operators_first():
    blocks = asyncio.run(tool_digest(DigestRequest(raw_diff=INVERTED, level=0)))
    first = _first_text(blocks)
    _assert_no_bare_operator(first)
    assert "user.role not equals 'admin'" in first, first
    assert first.lower().startswith("in src/auth/permissions.py, an authorization comparison was inverted")
    # Nothing was lost: the literal code is still in the machine-readable detail.
    detail = _detail(blocks)
    assert "user.role != 'admin'" in detail["voice_summary"]
    assert first == detail["voice_summary_for_speech"]


def test_the_drill_down_tool_speaks_named_operators_first():
    blocks = asyncio.run(tool_drill_down(DrillDownRequest(raw_diff=INVERTED, section_index=0)))
    first = _first_text(blocks)
    _assert_no_bare_operator(first)
    detail = _detail(blocks)
    assert first == detail["spoken_text_for_speech"]


def test_the_review_turn_tool_speaks_named_operators_first():
    payload = {"session_id": "first-block-is-speech", "user_id": "dev", "raw_diff": INVERTED}
    asyncio.run(tool_review_turn(ReviewTurnRequest(**payload, transcript="open")))
    blocks = asyncio.run(tool_review_turn(ReviewTurnRequest(**payload, transcript="summary")))
    first = _first_text(blocks)
    _assert_no_bare_operator(first)
    assert "not equals" in first, first
    detail = _detail(blocks)
    assert "!=" in detail["spoken"], "the literal code must stay in the detail block"
    assert first == f"{detail['readback_for_speech']} {detail['spoken_for_speech']}".strip()
