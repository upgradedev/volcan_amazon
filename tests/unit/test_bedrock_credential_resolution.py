"""The AWS Builder claim depends on a judge's credentials actually being found.

Environment variables are one of several sources boto3 searches. A reviewer running
with a shared credentials file, an SSO profile or an instance role has working
credentials, and the adapter must reach Bedrock for them rather than silently
serving the heuristic fallback and reporting that no credentials exist.
"""
import asyncio
import builtins
import sys
from types import SimpleNamespace

from src.infrastructure.bedrock_adapter import BedrockSynthesisAdapter


class _StubSession:
    def __init__(self, credentials):
        self._credentials = credentials

    def get_credentials(self):
        return self._credentials


def _install_boto3(monkeypatch, session_factory):
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(Session=session_factory))


def test_credentials_resolved_from_a_profile_are_found_without_any_env_var(monkeypatch):
    for name in ("AWS_ACCESS_KEY_ID", "AWS_SESSION_TOKEN", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.delenv(name, raising=False)
    _install_boto3(monkeypatch, lambda: _StubSession(object()))

    assert BedrockSynthesisAdapter().credentials_present() is True


def test_no_resolvable_credentials_reports_absent(monkeypatch):
    for name in ("AWS_ACCESS_KEY_ID", "AWS_SESSION_TOKEN", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.delenv(name, raising=False)
    _install_boto3(monkeypatch, lambda: _StubSession(None))

    assert BedrockSynthesisAdapter().credentials_present() is False


def test_a_broken_credential_chain_reports_absent_rather_than_raising(monkeypatch):
    def _explode():
        raise RuntimeError("profile 'missing' not found")

    _install_boto3(monkeypatch, _explode)

    assert BedrockSynthesisAdapter().credentials_present() is False


def test_without_boto3_installed_the_environment_is_still_consulted(monkeypatch):
    monkeypatch.delitem(sys.modules, "boto3", raising=False)
    real_import = builtins.__import__

    def _refuse_boto3(name, *args, **kwargs):
        if name == "boto3":
            raise ImportError("No module named 'boto3'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _refuse_boto3)
    monkeypatch.delenv("AWS_SESSION_TOKEN", raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAEXAMPLE")

    assert BedrockSynthesisAdapter().credentials_present() is True

    monkeypatch.delenv("AWS_ACCESS_KEY_ID")
    assert BedrockSynthesisAdapter().credentials_present() is False


def test_the_fallback_reason_names_the_credential_chain(monkeypatch):
    for name in ("AWS_ACCESS_KEY_ID", "AWS_SESSION_TOKEN", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.delenv(name, raising=False)
    _install_boto3(monkeypatch, lambda: _StubSession(None))

    adapter = BedrockSynthesisAdapter()
    asyncio.run(adapter.summarize_diff("diff --git a/x b/x\n+1\n", []))

    assert adapter.last_fallback_reason is not None
    assert "credential" in adapter.last_fallback_reason.lower()
