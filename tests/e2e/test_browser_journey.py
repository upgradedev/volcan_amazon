"""A real Chromium walks the primary judge journey against the running app."""
import socket
import subprocess
import sys
import time
from contextlib import closing

import httpx


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_browser_walks_the_primary_digest_sound_and_braille_journey():
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "src.interfaces.mcp_server:app",
         "--host", "127.0.0.1", "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                if httpx.get(f"{base_url}/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.1)
        else:
            raise AssertionError("Volcan server did not answer /health")

        journey = subprocess.run(
            [sys.executable, "tests/e2e/browser_journey_runner.py", base_url],
            capture_output=True, text=True, timeout=30,
        )
        assert journey.returncode == 0, journey.stdout + journey.stderr
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)
