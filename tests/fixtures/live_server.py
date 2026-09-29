"""Start a real Volcan server in a child process for browser and script tests.

The child gets its own environment, so a test can run the server in the
stateless MCP transport, or in durable mode against in-memory AWS fakes,
without touching the process the rest of the suite imported.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from contextlib import closing, contextmanager

import httpx


def free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@contextmanager
def running_server(
    env_overrides: dict[str, str] | None = None,
    launcher: list[str] | None = None,
) -> Iterator[str]:
    """Yield the base URL of a server that answered /health, then stop it.

    ``launcher`` replaces the default ``python -m uvicorn ...`` command; it
    receives the port as its last argument.
    """
    port = free_port()
    url = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    env["VOLCAN_ALLOWED_ORIGINS"] = url
    env.update(env_overrides or {})
    command = (
        [*launcher, str(port)] if launcher else
        [sys.executable, "-m", "uvicorn", "src.interfaces.mcp_server:app",
         "--host", "127.0.0.1", "--port", str(port)]
    )
    # A file, not a pipe: a full pipe buffer would stall the server.
    log = tempfile.TemporaryFile()
    server = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, env=env)
    try:
        # Importing the app takes several seconds on a cold Windows machine.
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if server.poll() is not None:
                log.seek(0)
                raise AssertionError(
                    "Volcan server exited before answering /health: "
                    + log.read().decode("utf-8", "replace")[-2000:]
                )
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
        log.close()


def run_script(*args: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *args], capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout,
    )
