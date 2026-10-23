"""The drill-down press shows Claude's answer only when a model answered, and says why otherwise."""
import socket
import subprocess
import sys
import time
from contextlib import closing

import httpx

from tests.fixtures.isolated_environment import isolated_test_environment


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_the_drill_down_press_labels_the_model_answer_and_every_fallback():
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    server_env = isolated_test_environment()
    server_env["VOLCAN_ALLOWED_ORIGINS"] = base_url
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "src.interfaces.mcp_server:app",
         "--host", "127.0.0.1", "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=server_env,
    )
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                if httpx.get(f"{base_url}/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.1)
        else:
            raise AssertionError("Volcan server did not answer /health")

        journey = subprocess.run(
            [sys.executable, "tests/e2e/drill_down_runner.py", base_url],
            capture_output=True, text=True, timeout=120,
            env=server_env,
        )
        assert journey.returncode == 0, journey.stdout + journey.stderr
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)
