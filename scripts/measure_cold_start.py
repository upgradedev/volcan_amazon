"""Measures the seconds from launching the server to its first HTTP 200 on /health.

This exists so the cold start figure in README.md carries a command anyone can
run, rather than a number somebody typed. It starts the server as a child
process, polls until the health route answers, prints the elapsed seconds and
stops the child again.

Run command:
    python scripts/measure_cold_start.py
"""
import subprocess
import sys
import time
import urllib.error
import urllib.request

URL = "http://127.0.0.1:8000/health"
TIMEOUT_SEC = 60.0


def already_listening() -> bool:
    try:
        with urllib.request.urlopen(URL, timeout=1):
            return True
    except Exception:
        return False


def main() -> int:
    if already_listening():
        print(f"Something already answers {URL}. Stop it first, or this would time a")
        print("process that was already warm, which is not a cold start.")
        return 2

    started = time.perf_counter()
    server = subprocess.Popen(
        [sys.executable, "-m", "src.interfaces.mcp_server"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        elapsed = None
        while time.perf_counter() - started < TIMEOUT_SEC:
            if server.poll() is not None:
                print("The server process exited before answering. Run it in the")
                print("foreground to see why: python -m src.interfaces.mcp_server")
                return 1
            try:
                with urllib.request.urlopen(URL, timeout=1) as response:
                    if response.status == 200:
                        elapsed = time.perf_counter() - started
                        break
            except Exception:
                time.sleep(0.05)

        if elapsed is None:
            print(f"No HTTP 200 on {URL} within {TIMEOUT_SEC:.0f} seconds.")
            return 1

        print(f"Cold start to the first HTTP 200 on /health: {elapsed:.1f} s")
        print(f"Measured on {sys.platform}, Python {sys.version.split()[0]}.")
        return 0
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == "__main__":
    raise SystemExit(main())
