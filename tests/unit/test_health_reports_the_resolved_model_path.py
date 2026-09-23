"""``/health`` must not imply a model will answer when no call can be made.

The field it published before was ``bedrock_credentials_present``, and on the
development machine it read ``true`` while the companion page correctly said
"No model answered, because: the Anthropic SDK is not installed". Both
statements were accurate and together they misled: credentials resolving says
nothing about whether a call can even be attempted, because without the SDK
nothing leaves the process at all.

The health check now reports one resolved capability computed from both facts,
and keeps the two facts beside it as the evidence. These tests drive all four
combinations, because a conclusion that is only ever exercised in one
environment is a conclusion nobody has checked.
"""
import sys
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.infrastructure import bedrock_adapter as adapter_module
from src.infrastructure.bedrock_adapter import (
    CAPABILITY_NEITHER,
    CAPABILITY_NO_CREDENTIALS,
    CAPABILITY_NO_SDK,
    CAPABILITY_READY,
    BedrockSynthesisAdapter,
)
from src.interfaces.mcp_server import app

client = TestClient(app)


def _adapter(monkeypatch, *, credentials: bool, sdk: bool) -> BedrockSynthesisAdapter:
    monkeypatch.setitem(
        sys.modules, "boto3",
        SimpleNamespace(Session=lambda: SimpleNamespace(
            get_credentials=lambda: object() if credentials else None
        )),
    )
    monkeypatch.setattr(BedrockSynthesisAdapter, "sdk_present", staticmethod(lambda: sdk))
    return BedrockSynthesisAdapter()


@pytest.mark.parametrize(
    ("credentials", "sdk", "expected"),
    [
        (True, True, CAPABILITY_READY),
        (True, False, CAPABILITY_NO_SDK),
        (False, True, CAPABILITY_NO_CREDENTIALS),
        (False, False, CAPABILITY_NEITHER),
    ],
)
def test_the_capability_is_the_conjunction_of_both_facts(monkeypatch, credentials, sdk, expected):
    capability = _adapter(monkeypatch, credentials=credentials, sdk=sdk).model_path_capability()
    assert capability["resolved_capability"] == expected
    assert capability["credentials_present"] is credentials
    assert capability["sdk_installed"] is sdk


def test_credentials_without_the_sdk_never_report_ready(monkeypatch):
    """This is the exact state of the development machine, and the old defect."""
    capability = _adapter(monkeypatch, credentials=True, sdk=False).model_path_capability()
    assert capability["resolved_capability"] != CAPABILITY_READY
    assert "not importable" in capability["detail"]
    assert "anthropic[bedrock]" in capability["detail"], (
        "a reviewer told the path is unavailable must be told what would enable it"
    )


def test_even_ready_is_a_statement_about_the_attempt_not_the_answer(monkeypatch):
    capability = _adapter(monkeypatch, credentials=True, sdk=True).model_path_capability()
    assert capability["resolved_capability"] == CAPABILITY_READY
    detail = capability["detail"]
    assert "attempted" in detail, "the ready state must promise an attempt, not an answer"
    assert "synthesis_mode" in detail, "it must point at the field that reports the outcome"
    for forbidden in ("will answer", "a model answers", "answered by"):
        assert forbidden not in detail, f"the health check predicts a model answer: {forbidden!r}"


def test_detecting_the_sdk_never_imports_it(monkeypatch):
    """A health probe must not pull a client library into the process."""
    monkeypatch.delitem(sys.modules, adapter_module.SDK_MODULE, raising=False)
    BedrockSynthesisAdapter.sdk_present()
    assert adapter_module.SDK_MODULE not in sys.modules


def test_a_broken_module_finder_reports_absent_rather_than_raising(monkeypatch):
    def _explode(_name):
        raise ValueError("__spec__ is not set")

    monkeypatch.setattr(adapter_module.importlib.util, "find_spec", _explode)
    assert BedrockSynthesisAdapter.sdk_present() is False


# --- what the endpoint actually serves --------------------------------------

def test_health_publishes_the_resolved_capability_and_its_evidence():
    body = client.get("/health").json()
    path = body["bedrock_model_path"]
    assert path["resolved_capability"] in {
        CAPABILITY_READY, CAPABILITY_NO_SDK, CAPABILITY_NO_CREDENTIALS, CAPABILITY_NEITHER,
    }
    assert isinstance(path["credentials_present"], bool)
    assert isinstance(path["sdk_installed"], bool)
    assert path["model_id"] and path["region"]
    assert path["detail"]


def test_health_no_longer_publishes_a_bare_credential_boolean():
    """The half-fact that was read as a promise must not be a top-level field."""
    body = client.get("/health").json()
    assert "bedrock_credentials_present" not in body, (
        "a top-level credential boolean is the field that misled; the evidence "
        "belongs under bedrock_model_path, subordinate to the conclusion"
    )


def test_the_ready_state_is_reachable_only_when_both_facts_hold():
    """Guards the endpoint itself, not just the adapter method.

    If the two ever disagree, the health check would be publishing a conclusion
    that its own evidence contradicts.
    """
    path = client.get("/health").json()["bedrock_model_path"]
    ready = path["resolved_capability"] == CAPABILITY_READY
    assert ready == (path["credentials_present"] and path["sdk_installed"])
