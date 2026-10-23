"""Check actual launch sites without starting a server, browser or model."""
import importlib
import os
import socket
from types import SimpleNamespace

import botocore.session
import pytest

from tests.fixtures.isolated_environment import isolated_test_environment
from tests.fixtures.live_server import run_script, running_server

PARENT_ENV = {
    "PATH": "preserved-test-path",
    "SystemRoot": "preserved-system-root",
    "AWS_ACCESS_KEY_ID": "test-parent-access-key",
    "AWS_SECRET_ACCESS_KEY": "test-parent-secret",
    "AWS_SESSION_TOKEN": "test-parent-session",
    "AWS_SECURITY_TOKEN": "test-legacy-session",
    "AWS_PROFILE": "test-parent-profile",
    "AWS_DEFAULT_PROFILE": "test-default-profile",
    "AWS_SHARED_CREDENTIALS_FILE": "parent-credentials",
    "AWS_CONFIG_FILE": "parent-config",
    "AWS_WEB_IDENTITY_TOKEN_FILE": "parent-web-identity",
    "AWS_ROLE_ARN": "test-role",
    "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI": "/test-credentials",
    "AWS_CONTAINER_CREDENTIALS_FULL_URI": "http://127.0.0.1/test-credentials",
    "AWS_CONTAINER_AUTHORIZATION_TOKEN": "test-container-token",
    "AWS_EC2_METADATA_SERVICE_ENDPOINT": "http://127.0.0.1/metadata",
    "AWS_EC2_METADATA_DISABLED": "false",
    "BOTO_CONFIG": "parent-boto-config",
    "VOLCAN_STATE_TABLE": "parent-live-table",
    "VOLCAN_APPROVAL_SECRET_ARN": "parent-live-secret",
    "VOLCAN_GITHUB_WRITE": "1",
    "GITHUB_TOKEN": "test-parent-github-token",
    "GH_TOKEN": "test-parent-gh-token",
}


@pytest.fixture
def poisoned_parent(monkeypatch):
    parent = PARENT_ENV.copy()
    monkeypatch.setattr(os, "environ", parent)
    return parent


def assert_isolated(env):
    assert env is not None
    for name, value in PARENT_ENV.items():
        if name not in ("PATH", "SystemRoot"):
            assert env.get(name) != value, name
    assert env["AWS_SHARED_CREDENTIALS_FILE"] == os.devnull
    assert env["AWS_CONFIG_FILE"] == os.devnull
    assert env["BOTO_CONFIG"] == os.devnull
    assert env["AWS_EC2_METADATA_DISABLED"] == "true"
    assert env["PATH"] == PARENT_ENV["PATH"]
    assert env["SystemRoot"] == PARENT_ENV["SystemRoot"]


def test_isolation_preserves_parent_and_os_settings_but_not_deploy_access(poisoned_parent):
    before = poisoned_parent.copy()
    env = isolated_test_environment()
    assert_isolated(env)
    assert poisoned_parent == before


def test_only_explicit_fake_app_configuration_is_retained(poisoned_parent):
    env = isolated_test_environment({
        "VOLCAN_STATE_TABLE": "explicit-fake-table",
        "VOLCAN_FAKE_SECRET_STRING": "explicit-fake-secret",
        "AWS_REGION": "eu-west-1",
        "AWS_ACCESS_KEY_ID": "forbidden-override",
        "AWS_CONFIG_FILE": "forbidden-profile",
        "AWS_CONTAINER_CREDENTIALS_FULL_URI": "http://127.0.0.1/forbidden",
        "BOTO_CONFIG": "forbidden-boto",
    })
    assert_isolated(env)
    assert env["VOLCAN_STATE_TABLE"] == "explicit-fake-table"
    assert env["VOLCAN_FAKE_SECRET_STRING"] == "explicit-fake-secret"
    assert env["AWS_REGION"] == "eu-west-1"
    assert "AWS_ACCESS_KEY_ID" not in env
    assert "AWS_CONTAINER_CREDENTIALS_FULL_URI" not in env


def test_botocore_resolves_no_credentials_without_network_or_profile_process(
    poisoned_parent, monkeypatch, tmp_path,
):
    # A real legacy credential file catches the less obvious fallback after
    # shared files, profiles, containers and instance metadata are disabled.
    boto_config = tmp_path / "boto"
    boto_config.write_text(
        "[Credentials]\naws_access_key_id = test-file-key\naws_secret_access_key = test-file-secret\n",
        encoding="utf-8",
    )
    poisoned_parent["BOTO_CONFIG"] = str(boto_config)
    env = isolated_test_environment()

    def no_network(*args, **kwargs):
        raise AssertionError("credential resolution tried to open a network connection")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(os, "environ", env)
    assert botocore.session.Session().get_credentials() is None


class FakeServer:
    def poll(self):
        return None

    def terminate(self):
        pass

    def wait(self, timeout):
        return 0


@pytest.fixture
def captured_launches(poisoned_parent, monkeypatch):
    import subprocess

    import httpx

    launches = []

    def popen(command, **kwargs):
        launches.append(("server", kwargs.get("env")))
        return FakeServer()

    def run(command, **kwargs):
        launches.append(("runner", kwargs.get("env")))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "Popen", popen)
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: SimpleNamespace(status_code=200))
    return launches


@pytest.mark.parametrize(("module_name", "test_name"), [
    ("test_browser_journey", "test_browser_walks_the_primary_digest_sound_and_braille_journey"),
    ("test_drill_down_display", "test_the_drill_down_press_labels_the_model_answer_and_every_fallback"),
    ("test_model_coverage_display", "test_the_page_shows_model_coverage_and_full_prose_from_the_response"),
    ("test_first_screen", None),
])
def test_browser_launchers_isolate_both_server_and_browser(
    module_name, test_name, captured_launches, monkeypatch,
):
    module = importlib.import_module("tests.e2e." + module_name)
    monkeypatch.setattr(module, "_free_port", lambda: 8765)
    if test_name is None:
        fixture = module.base_url.__wrapped__()
        url = next(fixture)
        try:
            module._run("offline", url)
        finally:
            fixture.close()
    else:
        getattr(module, test_name)()
    assert [kind for kind, env in captured_launches] == ["server", "runner"]
    for kind, env in captured_launches:
        assert_isolated(env)


def test_shared_server_fixture_and_script_runner_also_isolate_their_children(
    captured_launches, monkeypatch,
):
    monkeypatch.setattr("tests.fixtures.live_server.free_port", lambda: 8765)
    with running_server({"VOLCAN_STATE_TABLE": "explicit-fake-table"}) as url:
        assert url == "http://127.0.0.1:8765"
        run_script("tests/e2e/browser_journey_runner.py", url)
    assert [kind for kind, env in captured_launches] == ["server", "runner"]
    for kind, env in captured_launches:
        assert_isolated(env)
    assert captured_launches[0][1]["VOLCAN_STATE_TABLE"] == "explicit-fake-table"
