"""The boto3 credential chain is walked once, not on every request.

On a laptop with no AWS credentials the chain ends in the EC2 instance-metadata
probe: on 2026-09-26 the chain alone took 2.054 s and curl timed /health at
2.030, 2.024 and 2.030 s, because the adapter walked the chain on each call. These tests pin the cache: one lookup
serves later calls, a forced refresh looks again, a stale answer is replaced in
the background, and concurrent first calls share one lookup.
"""
import sys
import threading
import time
from types import SimpleNamespace

from fastapi.testclient import TestClient

from src.infrastructure import bedrock_adapter as module
from src.infrastructure.bedrock_adapter import BedrockSynthesisAdapter


def _counting_boto3(monkeypatch, answers, delay=0.0):
    """A boto3 stand-in whose Session counts lookups and returns answers in turn."""
    calls = []

    def session():
        calls.append(time.monotonic())
        if delay:
            time.sleep(delay)
        present = answers[min(len(calls), len(answers)) - 1]
        return SimpleNamespace(get_credentials=lambda: object() if present else None)

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(Session=session))
    return calls


def test_one_lookup_serves_every_later_call(monkeypatch):
    calls = _counting_boto3(monkeypatch, [False])
    adapter = BedrockSynthesisAdapter()
    assert [adapter.credentials_present() for _ in range(5)] == [False] * 5
    assert len(calls) == 1


def test_refresh_looks_the_chain_up_again(monkeypatch):
    calls = _counting_boto3(monkeypatch, [False, True])
    adapter = BedrockSynthesisAdapter()
    assert adapter.credentials_present() is False
    assert adapter.credentials_present(refresh=True) is True
    assert adapter.credentials_present() is True
    assert len(calls) == 2


def test_a_stale_answer_is_served_while_the_background_lookup_replaces_it(monkeypatch):
    calls = _counting_boto3(monkeypatch, [False, True], delay=0.05)
    monkeypatch.setattr(module, "CREDENTIAL_CACHE_SECONDS", 0.0)
    adapter = BedrockSynthesisAdapter()
    assert adapter.credentials_present() is False
    started = time.monotonic()
    assert adapter.credentials_present() is False, "the stale answer is returned at once"
    assert time.monotonic() - started < 0.04, "the caller did not wait for the lookup"
    deadline = time.monotonic() + 2
    while adapter._credentials_cache[0] is not True and time.monotonic() < deadline:
        time.sleep(0.01)
    assert adapter._credentials_cache[0] is True
    assert len(calls) == 2


def test_concurrent_first_calls_share_one_lookup(monkeypatch):
    calls = _counting_boto3(monkeypatch, [True], delay=0.1)
    adapter = BedrockSynthesisAdapter()
    results = []
    threads = [threading.Thread(target=lambda: results.append(adapter.credentials_present()))
               for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results == [True] * 4
    assert len(calls) == 1


def test_health_refresh_forces_a_new_lookup(monkeypatch):
    from src.interfaces import composition
    from src.interfaces.mcp_server import app

    seen = []
    monkeypatch.setattr(composition.bedrock_adapter, "credentials_present",
                        lambda refresh=False: seen.append(refresh) or False)
    client = TestClient(app)
    assert client.get("/health").status_code == 200
    assert client.get("/health?refresh=1").status_code == 200
    assert seen == [False, True]
