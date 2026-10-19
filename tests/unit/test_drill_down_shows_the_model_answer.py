"""The drill-down returns the model's answer for the focused file, or says why not.

Before this, ``op_drill_down`` asked the model about the whole patch (a billed
call on the live endpoint) and then threw the answer away, while the page
labelled the result "local AST drill-down". These tests drive the real shared
operation behind REST and MCP with stub clients, so no model is called. They
pin four things:

* the model is shown the focused file's part of the patch, not the whole patch;
* the answer, the model id and the coverage counts reach the API;
* every branch where no model answered (refusal, timeout, no credentials)
  carries its named reason, in the spoken text as well as in the field, and
  no model-shaped data;
* a Bedrock answer is labelled as one even when it names no model;
* an index outside the patch is refused before any model call;
* the MCP tool returns the same fields, with the model sentence first.
"""
import asyncio
import dataclasses
import os
import re

import pytest

import src.interfaces.operations as operations
from src.application.digest_diff_use_case import DigestDiffUseCase
from src.domain.semantic_diff import UnifiedDiffParser
from src.infrastructure.bedrock_adapter import (
    MODEL_DIFF_CHAR_BUDGET,
    NO_TEXT_PUBLIC_REASONS,
    NO_TEXT_REFUSAL,
    BedrockSynthesisAdapter,
)
from src.interfaces.dto import DrillDownRequest, DrillDownResult
from src.interfaces.mcp_protocol import PROTOCOL_VERSION

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

README_FILE = """diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1,2 +1,2 @@
-# Old title
+# New title
"""

PERMISSIONS_FILE = """diff --git a/src/auth/permissions.py b/src/auth/permissions.py
--- a/src/auth/permissions.py
+++ b/src/auth/permissions.py
@@ -10,3 +10,3 @@ def can_delete_workspace(user, workspace):
-    return user.role == "admin"
+    return user.role != "admin"
"""

TWO_FILES = README_FILE + PERMISSIONS_FILE

PROSE = "**Inverted admin check.** Non-admins can now delete workspaces. Revert the comparison."


class _Recorder:
    def __init__(self, reply=None, error=None):
        self.calls = []
        self._reply = reply
        self._error = error

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return self._reply


class _Client:
    def __init__(self, messages):
        self.messages = messages


class APITimeoutError(Exception):
    """Named like the SDK's timeout error, which the adapter classifies by name."""


def _install(monkeypatch, reply=None, error=None, credentials=True):
    recorder = _Recorder(reply=reply, error=error)
    monkeypatch.setattr(BedrockSynthesisAdapter, "credentials_present", lambda self: credentials)
    adapter = BedrockSynthesisAdapter(client_factory=lambda region: _Client(recorder))
    monkeypatch.setattr(operations, "digest_use_case", DigestDiffUseCase(adapter))
    return recorder


def _drill(index, raw_diff=TWO_FILES):
    return asyncio.run(operations.op_drill_down(DrillDownRequest(raw_diff=raw_diff, section_index=index)))


def _text_reply(text):
    return {"stop_reason": "end_turn", "content": [{"type": "text", "text": text}]}


def _prompt(recorder):
    assert len(recorder.calls) == 1, recorder.calls
    return recorder.calls[0]["messages"][0]["content"]


# --- the model's answer reaches the API ---------------------------------------


def test_the_model_is_asked_about_the_focused_file_only(monkeypatch):
    recorder = _install(monkeypatch, reply=_text_reply(PROSE))

    body = _drill(1)

    prompt = _prompt(recorder)
    assert "src/auth/permissions.py" in prompt
    assert 'user.role != "admin"' in prompt
    assert "README.md" not in prompt, "the model was shown another file of the patch"
    assert body["file_path"] == "src/auth/permissions.py"


def test_the_drill_down_returns_the_model_answer_and_its_coverage(monkeypatch):
    _install(monkeypatch, reply=_text_reply(PROSE))

    body = _drill(1)

    assert body["synthesis_mode"] == "bedrock"
    assert body["synthesis_fallback_reason"] is None
    assert body["model_answered"] == "anthropic.claude-sonnet-5"
    # Markdown removed, nothing cut: the same rule as the main digest.
    assert body["model_prose_full"] == (
        "Inverted admin check. Non-admins can now delete workspaces. Revert the comparison."
    )
    file_patch = UnifiedDiffParser.parse_patch_with_text(TWO_FILES)[1][1]
    assert body["model_input_chars_total"] == len(file_patch)
    assert body["model_input_chars_sent"] == len(file_patch)
    assert body["model_input_truncated"] is False


def test_the_spoken_drill_down_names_the_model_after_the_finding(monkeypatch):
    _install(monkeypatch, reply=_text_reply(PROSE))

    body = _drill(1)

    spoken = body["spoken_text"]
    assert spoken.startswith("Inspecting src/auth/permissions.py:")
    local_end = spoken.index("Claude Sonnet 5 on Amazon Bedrock says:")
    assert "an authorization comparison was inverted" in spoken[:local_end]
    assert "Inverted admin check." in spoken[local_end:]
    assert "Claude Sonnet 5 on Amazon Bedrock says:" in body["spoken_text_for_speech"]
    assert "not equals" in body["spoken_text_for_speech"]


def test_a_long_file_reports_the_prefix_the_model_read(monkeypatch):
    recorder = _install(monkeypatch, reply=_text_reply("Long file."))
    padding = "".join(f'+    note_{i:03d} = "padding to push this file past the model budget"\n' for i in range(80))
    long_file = PERMISSIONS_FILE + padding

    body = _drill(1, raw_diff=README_FILE + long_file)

    assert len(_prompt(recorder)) < len(long_file) + 400
    assert body["model_input_chars_sent"] == MODEL_DIFF_CHAR_BUDGET
    assert body["model_input_chars_total"] > MODEL_DIFF_CHAR_BUDGET
    assert body["model_input_truncated"] is True
    # The local rules still read the whole file.
    assert any("inverted" in finding for finding in body["security_findings"])


def test_rest_and_mcp_publish_the_same_drill_down_fields(monkeypatch):
    _install(monkeypatch, reply=_text_reply(PROSE))

    body = _drill(1)
    body.pop("_wav")
    body.pop("earcon")

    assert set(body) == set(DrillDownResult.model_fields)
    DrillDownResult.model_validate(body)


# --- every branch where no model answered is labelled -------------------------


def _assert_no_model_data(body, reason):
    assert body["synthesis_fallback_reason"] == reason
    # The listener hears it too: this text is what the status line, a Braille
    # display and an MCP client get, and the meter is not read aloud.
    assert body["spoken_text"].endswith(f" No model answered: {reason}."), body["spoken_text"]
    assert "No model answered: " in body["spoken_text_for_speech"]
    assert body["synthesis_mode"] == "heuristic-local"
    assert body["model_answered"] is None
    assert body["model_prose_full"] is None
    assert body["model_input_chars_sent"] is None
    assert body["model_input_chars_total"] is None
    assert body["model_input_truncated"] is False
    assert "Amazon Bedrock says" not in body["spoken_text"]
    # The local rules still answer for the file.
    assert body["file_path"] == "src/auth/permissions.py"
    assert any("inverted" in finding for finding in body["security_findings"])


def test_a_refusal_is_named_and_carries_no_model_answer(monkeypatch):
    _install(monkeypatch, reply={"stop_reason": "refusal", "content": []})

    body = _drill(1)

    _assert_no_model_data(body, NO_TEXT_PUBLIC_REASONS[NO_TEXT_REFUSAL])


def test_a_timeout_is_named_and_carries_no_model_answer(monkeypatch):
    _install(monkeypatch, error=APITimeoutError("Request timed out."))

    body = _drill(1)

    _assert_no_model_data(body, (
        "Amazon Bedrock did not answer before the request deadline; "
        "the local deterministic digest answered instead"
    ))


def test_no_credentials_is_named_and_calls_no_model(monkeypatch):
    recorder = _install(monkeypatch, reply=_text_reply(PROSE), credentials=False)

    body = _drill(1)

    assert recorder.calls == []
    _assert_no_model_data(body, "no AWS credentials were resolved by the boto3 credential chain")


class _FixedReportUseCase:
    """The real local section, with a report this test chooses."""

    def __init__(self, report):
        self._report = report

    async def drill_down(self, raw_diff, section_index, engine="auto"):
        return UnifiedDiffParser.parse_patch(raw_diff)[section_index], self._report


def test_a_bedrock_answer_that_names_no_model_is_still_labelled_a_model_answer(monkeypatch):
    _install(monkeypatch, reply=_text_reply(PROSE))
    file_text = UnifiedDiffParser.parse_patch_with_text(TWO_FILES)[1][1]
    answered = asyncio.run(operations.digest_use_case.execute(file_text))
    assert answered.synthesis_mode == "bedrock"
    unnamed = dataclasses.replace(answered, model_answered=None)
    monkeypatch.setattr(operations, "digest_use_case", _FixedReportUseCase(unnamed))

    body = _drill(1)

    assert body["synthesis_mode"] == "bedrock"
    assert body["model_answered"] is None
    assert body["model_prose_full"] == answered.model_prose_full
    assert "Amazon Bedrock, model not named, says: Inverted admin check." in body["spoken_text"]
    assert "No model answered" not in body["spoken_text"]


def _mcp_drill(index):
    from fastapi.testclient import TestClient

    from src.interfaces.mcp_server import app

    response = TestClient(app).post(
        "/mcp", headers={"MCP-Protocol-Version": PROTOCOL_VERSION},
        json={"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
            "name": "drill_down_section",
            "arguments": {"raw_diff": TWO_FILES, "section_index": index},
        }},
    )
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert result.get("isError") is not True, result
    return result


def test_the_mcp_tool_returns_the_same_fields_with_the_model_sentence_first(monkeypatch):
    _install(monkeypatch, reply=_text_reply(PROSE))

    result = _mcp_drill(1)

    structured = result["structuredContent"]
    assert set(structured) == set(DrillDownResult.model_fields)
    DrillDownResult.model_validate(structured)
    assert structured["model_answered"] == "anthropic.claude-sonnet-5"
    first = result["content"][0]
    assert first["type"] == "text"
    assert "Claude Sonnet 5 on Amazon Bedrock says: Inverted admin check." in first["text"]


def test_the_mcp_tool_says_no_model_answered_and_why(monkeypatch):
    _install(monkeypatch, reply=_text_reply(PROSE), credentials=False)

    result = _mcp_drill(1)

    assert result["structuredContent"]["synthesis_mode"] == "heuristic-local"
    assert result["content"][0]["text"].endswith(
        "No model answered: no AWS credentials were resolved by the boto3 credential chain."
    )


def test_an_index_outside_the_patch_is_refused_before_any_model_call(monkeypatch):
    recorder = _install(monkeypatch, reply=_text_reply(PROSE))

    with pytest.raises(IndexError):
        _drill(7)
    with pytest.raises(IndexError):
        _drill(-1)

    assert recorder.calls == [], "an out-of-range press still reached the model"


# --- the section text and the parsed sections cannot drift apart ---------------


def test_each_section_comes_with_its_own_part_of_the_patch():
    pairs = UnifiedDiffParser.parse_patch_with_text(TWO_FILES)

    assert [section.file_path for section, _ in pairs] == ["README.md", "src/auth/permissions.py"]
    assert [section for section, _ in pairs] == UnifiedDiffParser.parse_patch(TWO_FILES)
    assert pairs[0][1].startswith("diff --git a/README.md")
    assert pairs[1][1].startswith("diff --git a/src/auth/permissions.py")
    # Each part parses back to its own section alone.
    for section, text in pairs:
        assert UnifiedDiffParser.parse_patch(text) == [section]


# --- the label is read from model_answered -----------------------------------


@pytest.mark.parametrize("model_id, words", [
    ("anthropic.claude-sonnet-5", "Claude Sonnet 5"),
    ("anthropic.claude-haiku-4-5", "Claude Haiku 4.5"),
    ("eu.anthropic.claude-opus-4-8", "Claude Opus 4.8"),
    ("anthropic.claude-3-5-sonnet-20241022-v2:0", "anthropic.claude-3-5-sonnet-20241022-v2:0"),
    ("a configured inference profile", "a configured inference profile"),
])
def test_model_words_name_the_model_from_its_id(model_id, words):
    from src.application.digest_diff_use_case import model_words

    assert model_words(model_id) == words


def test_the_page_names_the_model_by_the_same_rule():
    """The page has its own copy of the rule; both must read the id the same way."""
    with open(os.path.join(REPO_ROOT, "docs", "index.html"), encoding="utf-8") as handle:
        page = handle.read()
    body = re.search(r"function modelWords\(id\) \{(.*?)\n    \}", page, re.S)
    assert body, "docs/index.html has no modelWords(id)"
    assert r"^(?:[a-z]{2,6}\.)?anthropic\.claude-([a-z]+)((?:-\d+)+)$" in body.group(1)


def test_the_page_makes_no_local_ast_claim_on_the_drill_down():
    with open(os.path.join(REPO_ROOT, "docs", "index.html"), encoding="utf-8") as handle:
        page = handle.read()
    assert "local AST" not in page
