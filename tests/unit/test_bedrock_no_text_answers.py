"""A Bedrock message that arrives with no text, and what Volcan does with it.

On 2026-10-06 the live 'Hear this code review' press fell back in 2 of 4
takes with "Amazon Bedrock returned no usable text block". Reproduced against
anthropic.claude-opus-5 in eu-west-1, the message was a refusal:
stop_reason "refusal", stop_details category "cyber", content [] and 0 output
tokens. These tests pin each no-text shape to its own public reason, the
bounded retry and its shared deadline, the request body, and the private
telemetry line, which must carry the answer's shape and never its words.
"""
import asyncio
import json
import logging
import sys
from types import SimpleNamespace

import pytest

import src.infrastructure.bedrock_adapter as ba
from src.domain.semantic_diff import ChangeCategory, ChangeSignificance, DiffSectionDigest

SECTION = DiffSectionDigest(
    file_path="src/auth/permissions.py",
    symbol_name="can_delete_workspace",
    category=ChangeCategory.SECURITY_SENSITIVE,
    significance=ChangeSignificance.CRITICAL,
    summary_spoken="Changed 1 line.",
    added_count=1,
    removed_count=1,
    security_flags=["authz_comparison_inverted"],
    security_findings=["an authorization comparison was inverted"],
)

TAKE4_DIFF = (
    "diff --git a/src/auth/permissions.py b/src/auth/permissions.py\n"
    "index 4c1a9f2..b7d3e88 100644\n"
    "--- a/src/auth/permissions.py\n"
    "+++ b/src/auth/permissions.py\n"
    "@@ -12,7 +12,7 @@ def can_delete_workspace(user, workspace):\n"
    "     if workspace.locked:\n"
    "         return False\n"
    "-    return user.role == \"admin\"\n"
    "+    return user.role != \"admin\"\n"
)

SECRET_WORDS = "SECRET-MODEL-WORDS"
SECRET_EXPLANATION = "SECRET-REFUSAL-EXPLANATION"
SECRET_ID = "msg_SECRET_ID_123"


def _usage(output_tokens=0, thinking_tokens=None):
    details = None if thinking_tokens is None else SimpleNamespace(thinking_tokens=thinking_tokens)
    return SimpleNamespace(
        input_tokens=231, output_tokens=output_tokens, output_tokens_details=details,
        cache_read_input_tokens=0, cache_creation_input_tokens=0,
    )


def _message(content, stop_reason="end_turn", category=None, output_tokens=0, thinking_tokens=None):
    """An SDK-shaped Message, with the fields anthropic 1.8.0's types carry."""
    stop_details = None
    if stop_reason == "refusal":
        stop_details = SimpleNamespace(type="refusal", category=category, explanation=SECRET_EXPLANATION)
    return SimpleNamespace(
        id=SECRET_ID, type="message", role="assistant", model="anthropic.claude-opus-5",
        content=content, stop_reason=stop_reason, stop_details=stop_details,
        usage=_usage(output_tokens, thinking_tokens),
    )


def _thinking(text=""):
    return SimpleNamespace(type="thinking", thinking=text, signature="sig")


def _text(text):
    return SimpleNamespace(type="text", text=text, citations=None)


REFUSAL = _message([], stop_reason="refusal", category="cyber")
REFUSAL_AFTER_THINKING = _message([_thinking("")], stop_reason="refusal", category="cyber",
                                  output_tokens=40, thinking_tokens=40)
THINKING_ONLY = _message([_thinking("")], output_tokens=120, thinking_tokens=120)
EMPTY_TEXT = _message([_thinking(""), _text("   ")], output_tokens=125, thinking_tokens=120)
MAX_TOKENS = _message([_thinking("")], stop_reason="max_tokens", output_tokens=16000, thinking_tokens=16000)
ANSWER = _message([_thinking(""), _text(SECRET_WORDS + " Admin check inverted.")],
                  output_tokens=190, thinking_tokens=120)


class _ScriptedMessages:
    """Answers each create() with the next scripted message, and advances a
    fake clock by each call's scripted duration."""

    def __init__(self, script, clock=None):
        self._script = list(script)
        self._clock = clock
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        response, seconds = self._script.pop(0)
        if self._clock is not None:
            self._clock.now += seconds
        if isinstance(response, Exception):
            raise response
        return response


class _Client:
    def __init__(self, script, clock=None):
        self.messages = _ScriptedMessages(script, clock)


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now


@pytest.fixture
def with_credentials(monkeypatch):
    monkeypatch.setattr(ba.BedrockSynthesisAdapter, "credentials_present", lambda self: True)


@pytest.fixture
def clock(monkeypatch):
    """A fake clock for the adapter module only; asyncio keeps the real one."""
    fake = _Clock()
    monkeypatch.setattr(ba, "time", SimpleNamespace(monotonic=fake.monotonic))
    return fake


def _press(client):
    adapter = ba.BedrockSynthesisAdapter(client_factory=lambda region: client)
    return asyncio.run(adapter.summarize_diff(TAKE4_DIFF, [SECTION]))


def _invoke(client):
    adapter = ba.BedrockSynthesisAdapter(client_factory=lambda region: client)
    return adapter._invoke(TAKE4_DIFF)


# --- Each no-text shape has its own public reason. ---


def test_the_observed_refusal_says_a_safety_filter_declined(with_credentials):
    """The live shape: stop_reason refusal, category cyber, no content."""
    client = _Client([(REFUSAL, 1.4)])

    report = _press(client)

    assert report.synthesis_mode == ba.MODE_HEURISTIC
    assert report.fallback_reason == (
        "Amazon Bedrock's safety filter declined to summarize this patch; "
        "the local deterministic digest answered instead"
    )
    assert SECRET_EXPLANATION not in report.fallback_reason


def test_a_refusal_after_thinking_is_still_a_refusal(with_credentials):
    report = _press(_Client([(REFUSAL_AFTER_THINKING, 3.0)]))

    assert report.fallback_reason.startswith("Amazon Bedrock's safety filter declined")


def test_a_refusal_after_partial_text_is_not_spoken_as_an_answer(with_credentials):
    """A classifier can stop a message after output began. The cut-off words
    are not a finished answer, so the refusal is reported instead."""
    partial = _message([_text(SECRET_WORDS + " The change")], stop_reason="refusal",
                       category="cyber", output_tokens=12)

    report = _press(_Client([(partial, 9.0)]))

    assert report.synthesis_mode == ba.MODE_HEURISTIC
    assert report.fallback_reason.startswith("Amazon Bedrock's safety filter declined")
    assert report.model_prose_full is None


def test_thinking_with_no_answer_is_named(with_credentials):
    report = _press(_Client([(THINKING_ONLY, 2.0), (THINKING_ONLY, 2.0)]))

    assert report.synthesis_mode == ba.MODE_HEURISTIC
    assert report.fallback_reason == (
        "Amazon Bedrock reasoned about the patch but wrote no answer; "
        "the local deterministic digest answered instead"
    )


def test_an_empty_text_block_is_named(with_credentials):
    report = _press(_Client([(EMPTY_TEXT, 2.0), (EMPTY_TEXT, 2.0)]))

    assert report.fallback_reason == (
        "Amazon Bedrock returned an empty answer; "
        "the local deterministic digest answered instead"
    )


def test_running_out_of_output_room_is_named(with_credentials):
    report = _press(_Client([(MAX_TOKENS, 20.0)]))

    assert report.fallback_reason.startswith(
        "Amazon Bedrock used its whole output allowance before writing an answer"
    )


def test_the_no_text_cause_wins_over_wording_in_the_exception():
    """The substring rules below it look for words like 'timeout' and
    'permission'; a no-text answer is classified by its cause first."""
    for cause, reason in ba.NO_TEXT_PUBLIC_REASONS.items():
        exc = ba.NoSpokenText(cause, "end_turn")
        exc.args = ("permission timeout not found throttled",)
        assert ba.BedrockSynthesisAdapter._public_failure_reason(exc) == reason


# --- One bounded retry, inside one deadline. ---


def test_a_refusal_is_not_resent(clock):
    """An identical resend after a refusal recovered 0 of 4 when measured live."""
    client = _Client([(REFUSAL, 1.4), (ANSWER, 3.0)], clock)

    with pytest.raises(ba.NoSpokenText) as raised:
        _invoke(client)

    assert raised.value.cause == ba.NO_TEXT_REFUSAL
    assert len(client.messages.calls) == 1


def test_a_thinking_only_answer_is_asked_once_more_with_the_time_left(clock):
    client = _Client([(THINKING_ONLY, 6.0), (ANSWER, 3.0)], clock)

    spoken = _invoke(client)

    assert spoken.endswith("Admin check inverted.")
    first, second = client.messages.calls
    assert first["timeout"] == ba.MODEL_CALL_TIMEOUT_SEC == 25
    assert second["timeout"] == pytest.approx(ba.MODEL_CALL_TIMEOUT_SEC - 6.0)


def test_there_is_never_a_third_attempt(clock):
    client = _Client([(THINKING_ONLY, 1.0), (THINKING_ONLY, 1.0), (ANSWER, 1.0)], clock)

    with pytest.raises(ba.NoSpokenText):
        _invoke(client)

    assert len(client.messages.calls) == 2


def test_no_retry_when_too_little_of_the_deadline_remains(clock):
    """A first answer at 18 s leaves 7 s, under the 8 s floor: no second call,
    so the press can never outlive the 30-second function budget."""
    assert ba.RETRY_MIN_REMAINING_SEC == 8.0
    client = _Client([(THINKING_ONLY, 18.0), (ANSWER, 3.0)], clock)

    with pytest.raises(ba.NoSpokenText):
        _invoke(client)

    assert len(client.messages.calls) == 1


def test_running_out_of_output_room_is_not_resent(clock):
    client = _Client([(MAX_TOKENS, 2.0), (ANSWER, 3.0)], clock)

    with pytest.raises(ba.NoSpokenText):
        _invoke(client)

    assert len(client.messages.calls) == 1


class _StatusError(Exception):
    def __init__(self, status_code):
        super().__init__(f"status {status_code} account=123456789012")
        self.status_code = status_code


class APIConnectionError(Exception):
    pass


class APITimeoutError(APIConnectionError):
    pass


@pytest.mark.parametrize("error", [_StatusError(429), _StatusError(503), APIConnectionError("reset")])
def test_a_transient_failure_is_tried_once_more_within_the_deadline(clock, error):
    """The SDK used to retry these on its own, ignoring the deadline."""
    client = _Client([(error, 1.0), (ANSWER, 3.0)], clock)

    assert _invoke(client).endswith("Admin check inverted.")
    assert client.messages.calls[1]["timeout"] == pytest.approx(ba.MODEL_CALL_TIMEOUT_SEC - 1.0)


@pytest.mark.parametrize("error", [_StatusError(400), _StatusError(403), APITimeoutError("timed out")])
def test_a_permanent_failure_or_a_timeout_is_not_tried_again(clock, error):
    client = _Client([(error, 1.0), (ANSWER, 3.0)], clock)

    with pytest.raises(type(error)):
        _invoke(client)

    assert len(client.messages.calls) == 1


def test_a_transient_failure_late_in_the_deadline_is_not_tried_again(clock):
    client = _Client([(_StatusError(503), 20.0), (ANSWER, 3.0)], clock)

    with pytest.raises(_StatusError):
        _invoke(client)

    assert len(client.messages.calls) == 1


# --- The request the adapter sends. ---


def test_the_request_body_is_the_one_with_live_evidence(with_credentials):
    """The live body answered 2 of 4 calls on 2026-10-06; three trial variants
    (a system prompt, a trimmed prompt at effort low with adaptive thinking
    stated, a resend) answered 0 of 12. Nothing is added to the request."""
    client = _Client([(ANSWER, 3.0)])

    _press(client)

    (sent,) = client.messages.calls
    assert set(sent) == {"model", "max_tokens", "timeout", "messages"}
    assert sent["model"] == ba.DEFAULT_MODEL_ID == "anthropic.claude-opus-5"
    assert sent["max_tokens"] == ba.DEFAULT_MAX_TOKENS == 16000
    assert sent["timeout"] == ba.MODEL_CALL_TIMEOUT_SEC == 25
    assert sent["messages"] == [{"role": "user", "content": (
        "You are Volcan, an accessibility agent assisting a visually impaired engineer. "
        "Summarize the following code changes into a clear, concise (under 25 words) "
        "executive spoken summary. Identify any high-risk changes.\n\n"
        "Diff:\n" + TAKE4_DIFF
    )}]


def test_the_local_finding_is_still_spoken_first_when_a_model_answers(with_credentials):
    from src.application.digest_diff_use_case import DigestDiffUseCase

    client = _Client([(ANSWER, 3.0)])
    adapter = ba.BedrockSynthesisAdapter(client_factory=lambda region: client)

    report = asyncio.run(DigestDiffUseCase(adapter).execute(TAKE4_DIFF))
    spoken = report.to_voice_summary(level=0)

    assert report.synthesis_mode == ba.MODE_BEDROCK
    assert spoken.startswith("In src/auth/permissions.py, an authorization comparison was inverted")


def test_the_real_client_is_built_without_sdk_retries(monkeypatch):
    """The SDK retries a timed-out request twice by default: 3 x 25 s."""
    seen = {}

    class AnthropicBedrockMantle:
        def __init__(self, **kwargs):
            seen.update(kwargs)

    monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(AnthropicBedrockMantle=AnthropicBedrockMantle))
    monkeypatch.setenv("AWS_REGION", "eu-west-1")

    ba.BedrockSynthesisAdapter()._build_client()

    assert seen == {"aws_region": "eu-west-1", "max_retries": 0}


# --- Private telemetry: the answer's shape, never its words. ---


def _telemetry_lines(caplog):
    return [json.loads(r.getMessage()) for r in caplog.records if r.name == "volcan.bedrock"]


def test_one_telemetry_line_per_model_call_with_the_shape_and_no_text(with_credentials, caplog):
    caplog.set_level(logging.INFO, logger="volcan.bedrock")
    client = _Client([(ANSWER, 3.0)])

    _press(client)

    raw = [r.getMessage() for r in caplog.records if r.name == "volcan.bedrock"]
    (line,) = _telemetry_lines(caplog)
    assert line["event"] == "bedrock_model_call"
    assert line["attempt"] == 1
    assert isinstance(line["latency_ms"], int)
    assert line["stop_reason"] == "end_turn"
    assert line["blocks"] == [{"type": "thinking", "chars": 0},
                              {"type": "text", "chars": len(SECRET_WORDS + " Admin check inverted.")}]
    assert line["usage"]["output_tokens"] == 190
    assert line["usage"]["thinking_tokens"] == 120
    for secret in (SECRET_WORDS, "Admin check", SECRET_ID, "anthropic.claude-opus-5", "sig"):
        assert secret not in raw[0]


def test_a_refusal_is_logged_with_its_category_and_without_its_explanation(with_credentials, caplog):
    caplog.set_level(logging.INFO, logger="volcan.bedrock")

    _press(_Client([(REFUSAL, 1.4)]))

    raw = [r.getMessage() for r in caplog.records if r.name == "volcan.bedrock"]
    (line,) = _telemetry_lines(caplog)
    assert line["stop_reason"] == "refusal"
    assert line["refusal_category"] == "cyber"
    assert line["blocks"] == []
    assert line["usage"]["output_tokens"] == 0
    assert SECRET_EXPLANATION not in raw[0]
    assert SECRET_ID not in raw[0]


def test_a_failed_call_logs_the_error_type_and_never_its_message(with_credentials, caplog):
    caplog.set_level(logging.INFO, logger="volcan.bedrock")

    class PermissionDeniedError(Exception):
        pass

    error = PermissionDeniedError(
        "User arn:aws:sts::123456789012:assumed-role/volcan/x is not authorized; request_id=req_private"
    )
    _press(_Client([(error, 0.3)]))

    raw = [r.getMessage() for r in caplog.records if r.name == "volcan.bedrock"]
    (line,) = _telemetry_lines(caplog)
    assert line["outcome"] == "error"
    assert line["error_type"] == "PermissionDeniedError"
    for secret in ("arn:aws", "123456789012", "req_private", "assumed-role"):
        assert secret not in raw[0]


def test_both_attempts_of_a_retried_press_are_logged(with_credentials, caplog):
    caplog.set_level(logging.INFO, logger="volcan.bedrock")

    report = _press(_Client([(THINKING_ONLY, 2.0), (ANSWER, 3.0)]))

    assert report.synthesis_mode == ba.MODE_BEDROCK
    assert [line["attempt"] for line in _telemetry_lines(caplog)] == [1, 2]
