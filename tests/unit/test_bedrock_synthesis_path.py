"""What the Bedrock adapter does, and what it says when it cannot.

These tests pin the request the adapter builds, the response shapes it can read,
and the bounded public sentence it produces when the call fails. A fallback
nobody can explain is indistinguishable from a design decision; a raw provider
payload can disclose cloud identity and request data.
"""
import asyncio
from types import SimpleNamespace

import pytest

from src.domain.semantic_diff import ChangeCategory, ChangeSignificance, DiffSectionDigest
from src.infrastructure.bedrock_adapter import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL_ID,
    MODE_BEDROCK,
    MODE_HEURISTIC,
    MODEL_CALL_TIMEOUT_SEC,
    MODEL_DIFF_CHAR_BUDGET,
    BedrockSynthesisAdapter,
    shorten_for_speech,
)

SECTION = DiffSectionDigest(
    file_path="src/api/admin.py",
    symbol_name="module_scope",
    category=ChangeCategory.SECURITY_SENSITIVE,
    significance=ChangeSignificance.CRITICAL,
    summary_spoken="Changed 1 line.",
    added_count=1,
    removed_count=1,
    security_flags=["authz_comparison_inverted"],
    security_findings=["an authorization comparison was inverted"],
)


class _StubMessages:
    def __init__(self, response=None, error=None):
        self._response = response
        self._error = error
        self.seen: dict = {}

    def create(self, **kwargs):
        self.seen = kwargs
        if self._error is not None:
            raise self._error
        return self._response


class _StubClient:
    def __init__(self, response=None, error=None):
        self.messages = _StubMessages(response, error)


@pytest.fixture
def with_credentials(monkeypatch):
    monkeypatch.setattr(BedrockSynthesisAdapter, "credentials_present", lambda self: True)


def _run(adapter):
    return asyncio.run(adapter.summarize_diff("diff --git a/x b/x\n+1\n", [SECTION]))


def test_the_pinned_model_id_is_a_current_claude_model_on_bedrock():
    """The retired snapshot this file used to pin answers ResourceNotFoundException."""
    assert DEFAULT_MODEL_ID == "anthropic.claude-opus-5"
    assert "2024" not in DEFAULT_MODEL_ID
    assert BedrockSynthesisAdapter().model_id == DEFAULT_MODEL_ID


def test_the_model_id_can_be_repinned_without_editing_the_source(monkeypatch):
    monkeypatch.setenv("AWS_BEDROCK_MODEL_ID", "us.anthropic.claude-opus-5")
    assert BedrockSynthesisAdapter().model_id == "us.anthropic.claude-opus-5"


def test_a_model_answer_is_labelled_bedrock_with_no_fallback_reason(with_credentials):
    client = _StubClient({"content": [{"type": "text", "text": "Authorization check inverted."}]})
    adapter = BedrockSynthesisAdapter(client_factory=lambda region: client)

    report = _run(adapter)

    assert report.synthesis_mode == MODE_BEDROCK
    assert report.fallback_reason is None
    assert adapter.last_fallback_reason is None
    assert report.executive_spoken_summary == "Authorization check inverted."


def test_the_request_carries_the_pinned_model_and_room_to_finish(with_credentials):
    client = _StubClient({"content": [{"type": "text", "text": "ok"}]})
    adapter = BedrockSynthesisAdapter(client_factory=lambda region: client)

    _run(adapter)

    assert client.messages.seen["model"] == DEFAULT_MODEL_ID
    assert client.messages.seen["max_tokens"] == DEFAULT_MAX_TOKENS
    assert client.messages.seen["max_tokens"] >= 4096, "a small ceiling truncates a thinking model"
    assert client.messages.seen["timeout"] == MODEL_CALL_TIMEOUT_SEC == 25


def test_a_thinking_block_before_the_text_does_not_break_the_digest(with_credentials):
    """Indexing content[0] would return a thinking block and raise."""
    client = _StubClient({"content": [
        {"type": "thinking", "thinking": "weighing the change"},
        {"type": "text", "text": "One authorization comparison was inverted."},
    ]})
    adapter = BedrockSynthesisAdapter(client_factory=lambda region: client)

    report = _run(adapter)

    assert report.synthesis_mode == MODE_BEDROCK
    assert report.executive_spoken_summary == "One authorization comparison was inverted."


def test_sdk_objects_are_read_the_same_way_as_dictionaries(with_credentials):
    client = _StubClient(SimpleNamespace(content=[
        SimpleNamespace(type="thinking", thinking="..."),
        SimpleNamespace(type="text", text="  Spoken by an object.  "),
    ]))
    adapter = BedrockSynthesisAdapter(client_factory=lambda region: client)

    assert _run(adapter).executive_spoken_summary == "Spoken by an object."


def test_a_response_with_no_text_block_degrades_instead_of_raising(with_credentials):
    client = _StubClient({"content": [{"type": "thinking", "thinking": "..."}]})
    adapter = BedrockSynthesisAdapter(client_factory=lambda region: client)

    report = _run(adapter)

    assert report.synthesis_mode == MODE_HEURISTIC
    assert report.fallback_reason == (
        "Amazon Bedrock returned no usable text block; "
        "the local deterministic digest answered instead"
    )


def test_a_failed_call_is_actionable_without_leaking_the_provider_payload(with_credentials):
    """Provider errors can carry account, role and request identifiers."""
    class ResourceNotFoundException(Exception):
        pass

    secret_payload = (
        "This model is not available; User arn:aws:sts::123456789012:assumed-role/demo; "
        "request_id=req_sensitive_123"
    )
    client = _StubClient(error=ResourceNotFoundException(secret_payload))
    adapter = BedrockSynthesisAdapter(client_factory=lambda region: client)

    report = _run(adapter)

    assert report.synthesis_mode == MODE_HEURISTIC
    assert "configured Amazon Bedrock model is unavailable" in report.fallback_reason
    for sensitive in ("123456789012", "assumed-role", "req_sensitive_123", secret_payload):
        assert sensitive not in report.fallback_reason
    assert report.fallback_reason == adapter.last_fallback_reason


def test_a_permission_failure_never_returns_aws_identity_or_request_ids(with_credentials):
    class PermissionDeniedError(Exception):
        pass

    client = _StubClient(error=PermissionDeniedError(
        "User arn:aws:sts::123456789012:assumed-role/volcan/session is not authorized; "
        "request_id=req_private"
    ))
    report = _run(BedrockSynthesisAdapter(client_factory=lambda region: client))

    assert report.fallback_reason.startswith("Amazon Bedrock access is not authorized")
    assert "123456789012" not in report.fallback_reason
    assert "assumed-role" not in report.fallback_reason
    assert "req_private" not in report.fallback_reason


@pytest.mark.parametrize(
    ("provider_message", "public_fragment"),
    [
        ("ThrottlingException: rate limit exceeded", "temporarily throttled"),
        ("request timed out", "before the request deadline"),
        ("service unavailable", "unavailable in this deployment"),
        ("unexpected transport failure", "did not complete the synthesis request"),
    ],
)
def test_every_provider_failure_category_is_bounded(
    with_credentials, provider_message, public_fragment,
):
    private_suffix = " account=123456789012 request_id=req_private"
    client = _StubClient(error=RuntimeError(provider_message + private_suffix))

    report = _run(BedrockSynthesisAdapter(client_factory=lambda region: client))

    assert public_fragment in report.fallback_reason
    assert "123456789012" not in report.fallback_reason
    assert "req_private" not in report.fallback_reason


def test_a_missing_sdk_says_which_package_to_install(with_credentials):
    def _no_sdk(region):
        raise ImportError("No module named 'anthropic'; private_path=C:/operator/home")

    adapter = BedrockSynthesisAdapter(client_factory=_no_sdk)
    report = _run(adapter)

    assert report.synthesis_mode == MODE_HEURISTIC
    assert "anthropic[bedrock]" in report.fallback_reason
    assert "private_path" not in report.fallback_reason


def test_absent_credentials_are_reported_as_the_reason(monkeypatch):
    monkeypatch.setattr(BedrockSynthesisAdapter, "credentials_present", lambda self: False)
    adapter = BedrockSynthesisAdapter()

    report = _run(adapter)

    assert report.synthesis_mode == MODE_HEURISTIC
    assert "credential" in report.fallback_reason.lower()


def test_the_region_reaches_the_client_factory(monkeypatch, with_credentials):
    monkeypatch.setenv("AWS_REGION", "eu-central-1")
    seen = {}

    def _factory(region):
        seen["region"] = region
        return _StubClient({"content": [{"type": "text", "text": "ok"}]})

    _run(BedrockSynthesisAdapter(client_factory=_factory))

    assert seen["region"] == "eu-central-1"


def _run_diff(adapter, raw_diff):
    return asyncio.run(adapter.summarize_diff(raw_diff, [SECTION]))


def test_short_model_prose_passes_through_untouched(with_credentials):
    client = _StubClient({"content": [{"type": "text", "text": "Authorization check inverted."}]})
    adapter = BedrockSynthesisAdapter(client_factory=lambda region: client)

    report = _run(adapter)

    assert report.executive_spoken_summary == "Authorization check inverted."
    assert report.model_prose_full == "Authorization check inverted."


def test_long_model_prose_is_cut_at_a_sentence_end(with_credentials):
    """The September receipt cut mid-word ("admin ac"); speech never does."""
    prose = (
        "In src/auth.py, login now grants a session to any admin flagged user without "
        "verifying their password. High risk: critical authentication bypass of the login "
        "form that guards every protected page and API route in this service."
    )
    client = _StubClient({"content": [{"type": "text", "text": prose}]})
    adapter = BedrockSynthesisAdapter(client_factory=lambda region: client)

    report = _run(adapter)
    spoken = report.executive_spoken_summary

    assert spoken == (
        "In src/auth.py, login now grants a session to any admin flagged user without "
        "verifying their password. \u2026"
    )
    assert report.model_prose_full == prose


def test_the_full_answer_panel_gets_the_prose_without_markdown(with_credentials):
    """The page shows model_prose_full under "The model's full answer" with
    textContent, so raw stars, ticks and quote markers reached the screen and
    the screen reader. The words stay whole; only the markup goes, and a
    code-shaped star survives."""
    prose = "\n".join((
        "**Spoken summary:** the check is _inverted_.",
        "> __Note:__ `user.role != 'admin'` now *lets everyone else* in.",
        "- keep a*b*c as written",
    ))
    client = _StubClient({"content": [{"type": "text", "text": prose}]})
    adapter = BedrockSynthesisAdapter(client_factory=lambda region: client)

    full = _run(adapter).model_prose_full

    assert full.splitlines() == [
        "Spoken summary: the check is inverted.",
        "Note: user.role != 'admin' now lets everyone else in.",
        "keep a*b*c as written",
    ]
    assert "**" not in full and "`" not in full and "_inverted_" not in full
    assert not any(line.startswith(">") for line in full.splitlines())


def test_the_full_answer_panel_keeps_fenced_code_whole(with_credentials):
    """Inside a fence the '-' and '+' diff markers and the '#' comment marker
    carry meaning, so model_prose_full keeps them while the prose around the
    fence still loses its Markdown."""
    prose = "\n".join((
        "**Spoken summary:** the check is *inverted*.",
        "```diff",
        '-    return user.role == "admin"',
        '+    return user.role != "admin"',
        "```",
        "```python",
        "# only admins may delete",
        "```",
    ))
    client = _StubClient({"content": [{"type": "text", "text": prose}]})
    adapter = BedrockSynthesisAdapter(client_factory=lambda region: client)

    report = _run(adapter)

    assert report.model_prose_full.splitlines() == [
        "Spoken summary: the check is inverted.",
        "Code, diff:",
        '-    return user.role == "admin"',
        '+    return user.role != "admin"',
        "End of code.",
        "Code, python:",
        "# only admins may delete",
        "End of code.",
    ]
    assert "```" not in report.executive_spoken_summary


def test_word_boundary_cut_when_no_sentence_end_fits():
    prose = " ".join(f"word{i:03d}" for i in range(60))
    spoken = shorten_for_speech(prose)

    assert spoken.endswith(" \u2026")
    assert "\u2026" not in spoken[:-2]
    assert len(spoken) <= 182
    tail = spoken[:-2].rsplit(" ", 1)[-1]
    assert tail in prose.split(), f"cut inside a word: {tail!r}"


def test_shorten_measures_the_cut_on_words_not_markup():
    """Stars and ticks must not consume the spoken budget or reach the ear."""
    prose = (
        "**Spoken summary:** In permissions dot py, workspace deletion now requires the user *not* be an admin, "
        "because the comparison was inverted in this patch and the surrounding code stayed the same throughout."
    )
    spoken = shorten_for_speech(prose)

    assert "*" not in spoken
    assert spoken.startswith("Spoken summary: In permissions dot py")
    assert spoken.endswith(" \u2026")
    assert len(spoken) <= 182


def test_a_long_patch_records_what_the_model_saw(with_credentials):
    client = _StubClient({"content": [{"type": "text", "text": "ok"}]})
    adapter = BedrockSynthesisAdapter(client_factory=lambda region: client)
    raw_diff = "x" * 5000

    report = _run_diff(adapter, raw_diff)
    sent_prompt = client.messages.seen["messages"][0]["content"]

    assert report.model_input_chars_sent == MODEL_DIFF_CHAR_BUDGET == 3000
    assert report.model_input_chars_total == len(raw_diff)
    assert sent_prompt.endswith("x" * 3000)
    assert "x" * 3001 not in sent_prompt


def test_heuristic_digests_carry_no_model_shaped_data(with_credentials):
    client = _StubClient(error=TimeoutError("timed out"))
    adapter = BedrockSynthesisAdapter(client_factory=lambda region: client)

    report = _run(adapter)

    assert report.synthesis_mode == MODE_HEURISTIC
    assert report.model_prose_full is None
    assert report.model_input_chars_sent is None
    assert report.model_input_chars_total is None
