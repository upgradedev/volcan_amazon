"""A real Chromium checks the first screen: no outside request, a silent preview,
one announcement channel, a working MCP handshake and a skip link that lands."""
import os
import socket
import subprocess
import sys
import time
from contextlib import closing

import httpx
import pytest

RUNNER = "tests/e2e/first_screen_runner.py"


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture(scope="module")
def base_url():
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    env["VOLCAN_ALLOWED_ORIGINS"] = url
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "src.interfaces.mcp_server:app",
         "--host", "127.0.0.1", "--port", str(port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env,
    )
    try:
        # Importing the app takes several seconds on a cold Windows machine.
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                if httpx.get(f"{url}/health", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.2)
        else:
            raise AssertionError("Volcan server did not answer /health")
        yield url
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)


def _run(mode: str, url: str) -> None:
    result = subprocess.run([sys.executable, RUNNER, mode, url],
                            capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_page_renders_its_typefaces_with_every_outside_request_refused(base_url):
    _run("offline", base_url)


def test_the_first_screen_shows_the_real_answer_without_speaking_playing_or_announcing(base_url):
    _run("silent", base_url)


def test_the_mcp_handshake_works_on_the_serving_origin_and_prints_a_refusal(base_url):
    _run("handshake", base_url)


def test_the_skip_link_moves_focus_into_main(base_url):
    _run("skip", base_url)


def test_a_patch_changed_after_a_press_never_sits_beside_the_old_answer(base_url):
    _run("stale", base_url)
