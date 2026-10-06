"""The model-evidence fields must survive the use case to the API.

The adapter emits the model's full prose and what it was shown, but the use
case rebuilt the report without them: a digest synthesised from a 3000-char
prefix of a 4107-char patch answered ``model_input_truncated: false`` with
every evidence field null. These tests drive the real use case (and the real
shared operation behind REST and MCP) with a stub provider, so no model is
called and the propagation itself is what is pinned.
"""
import asyncio

from src.application.digest_diff_use_case import DigestDiffUseCase
from src.infrastructure.bedrock_adapter import (
    MODEL_CALL_TIMEOUT_SEC,
    MODEL_DIFF_CHAR_BUDGET,
    BedrockSynthesisAdapter,
    public_model_label,
)

BENIGN_FILE = """diff --git a/src/utils/text.py b/src/utils/text.py
--- a/src/utils/text.py
+++ b/src/utils/text.py
@@ -1,3 +1,60 @@ def normalise(data):
-    return data.strip()
{added}"""
PADDED_LINE = '+    cleaned = "padding to push the patch past the model budget %03d"\n'

LATE_INVERSION = """diff --git a/src/auth/permissions.py b/src/auth/permissions.py
--- a/src/auth/permissions.py
+++ b/src/auth/permissions.py
@@ -10,3 +10,3 @@ def can_delete_workspace(user, workspace):
-    return user.role == "admin"
+    return user.role != "admin"
"""


class _StubMessages:
    def __init__(self, prose):
        self._prose = prose

    def create(self, **kwargs):
        return {"content": [{"type": "text", "text": self._prose}]}


class _StubClient:
    def __init__(self, prose):
        self.messages = _StubMessages(prose)


def _use_case(prose, monkeypatch):
    monkeypatch.setattr(BedrockSynthesisAdapter, "credentials_present", lambda self: True)
    adapter = BedrockSynthesisAdapter(client_factory=lambda region: _StubClient(prose))
    return DigestDiffUseCase(adapter)


def _over_budget_patch():
    padding = "".join(PADDED_LINE % i for i in range(80))
    patch = BENIGN_FILE.format(added=padding) + LATE_INVERSION
    assert len(patch) > MODEL_DIFF_CHAR_BUDGET
    return patch


def test_the_use_case_carries_model_prose_and_coverage(monkeypatch):
    """The adapter emits prose plus sent/total; the rebuilt report used to
    drop all three to null, answering truncated:false for a prefix the
    model never saw whole."""
    prose = "Complete model prose retained at adapter boundary."
    use_case = _use_case(prose, monkeypatch)

    report = asyncio.run(use_case.execute(LATE_INVERSION))

    assert report.synthesis_mode == "bedrock"
    assert report.model_prose_full == prose
    assert report.model_input_chars_sent == len(LATE_INVERSION)
    assert report.model_input_chars_total == len(LATE_INVERSION)
    assert report.model_answered == public_model_label(BedrockSynthesisAdapter().model_id)


def test_over_budget_multifile_patch_reports_truncation_and_keeps_late_findings(monkeypatch):
    """The model reads a prefix; the local rules read the whole patch.

    The late file sits past the 3000-char budget, so a prefix-only product
    would miss the inversion. The digest must say what the model saw and
    still name the late finding.
    """
    use_case = _use_case("Two files changed; review the late one first.", monkeypatch)
    patch = _over_budget_patch()

    report = asyncio.run(use_case.execute(patch))

    assert report.model_input_chars_sent == MODEL_DIFF_CHAR_BUDGET == 3000
    assert report.model_input_chars_total == len(patch) > 3000
    assert report.model_prose_full == "Two files changed; review the late one first."
    assert any("src/auth/permissions.py" in finding for finding in report.critical_findings), (
        report.critical_findings
    )


def test_the_api_dict_reports_truncation_from_the_use_case(monkeypatch):
    """REST and MCP share op_digest; both must see truncated:true."""
    import src.interfaces.operations as operations

    use_case = _use_case("Two files changed.", monkeypatch)
    monkeypatch.setattr(operations, "digest_use_case", use_case)
    from src.interfaces.dto import DigestRequest

    body = asyncio.run(operations.op_digest(DigestRequest(raw_diff=_over_budget_patch())))

    assert body["synthesis_mode"] == "bedrock"
    assert body["model_input_truncated"] is True
    assert body["model_input_chars_sent"] == 3000
    assert body["model_input_chars_total"] > 3000
    assert body["model_prose_full"] == "Two files changed."
    # The page names the model from this field, never from a constant.
    assert body["model_answered"] == public_model_label(BedrockSynthesisAdapter().model_id)


def test_the_heuristic_path_claims_no_model_coverage():
    """A digest no model touched must not carry model-shaped data."""
    import src.interfaces.operations as operations
    from src.interfaces.dto import DigestRequest

    body = asyncio.run(operations.op_digest(DigestRequest(raw_diff=LATE_INVERSION), engine="local"))

    assert body["synthesis_mode"] == "heuristic-local"
    assert body["model_input_truncated"] is False
    assert body["model_prose_full"] is None
    assert body["model_input_chars_sent"] is None
    assert body["model_input_chars_total"] is None
    assert body["model_answered"] is None
    assert any("src/auth/permissions.py" in finding for finding in body["critical_findings"])


def test_the_model_deadline_fits_inside_the_function_budget():
    assert MODEL_CALL_TIMEOUT_SEC == 25
    assert MODEL_CALL_TIMEOUT_SEC < 30, "the production function budget is 30 seconds"


# --- Input bounds: absurd payloads are refused before parsing. ---


def test_patches_past_the_bound_are_refused_with_422():
    from fastapi.testclient import TestClient

    from src.interfaces.dto import MAX_RAW_DIFF_CHARS
    from src.interfaces.mcp_server import app

    oversized = "x" * (MAX_RAW_DIFF_CHARS + 1)
    response = TestClient(app).post(
        "/api/digest_semantic_diff", json={"raw_diff": oversized, "level": 0, "engine": "local"}
    )

    assert response.status_code == 422


def test_the_bound_sits_past_real_patches():
    from src.interfaces.dto import MAX_RAW_DIFF_CHARS, DigestRequest, DrillDownRequest

    assert MAX_RAW_DIFF_CHARS == 1_000_000
    assert DigestRequest(raw_diff="x" * MAX_RAW_DIFF_CHARS).raw_diff
    assert DrillDownRequest(raw_diff="x" * MAX_RAW_DIFF_CHARS, section_index=0).raw_diff
