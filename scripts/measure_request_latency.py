"""Separate cold-like startup from steady-state HTTP latency and publish samples."""
import argparse
import json
import os
import platform
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient

from scripts.latency_statistics import latency_stats
from src.interfaces.mcp_server import app

WARMUP_REQUESTS = 5
STEADY_SAMPLES = 100
STEADY_P95_LIMIT_MS = 300.0


def timed_health(client: TestClient) -> float:
    start = time.perf_counter()
    response = client.get("/health")
    elapsed = (time.perf_counter() - start) * 1000.0
    if response.status_code != 200:
        raise RuntimeError(f"/health returned {response.status_code}")
    return elapsed


def measure() -> dict[str, object]:
    client = TestClient(app)
    first_request_ms = timed_health(client)
    warmup_ms = [timed_health(client) for _ in range(WARMUP_REQUESTS)]
    steady_ms = [timed_health(client) for _ in range(STEADY_SAMPLES)]
    steady = latency_stats(steady_ms)
    return {
        "scope": "in-process TestClient /health; process cold start is measured separately",
        "python_version": platform.python_version(),
        "first_request_ms": round(first_request_ms, 6),
        "warmup_requests": WARMUP_REQUESTS,
        "warmup_samples_ms": [round(value, 6) for value in warmup_ms],
        "steady_state": steady,
        "steady_p95_limit_ms": STEADY_P95_LIMIT_MS,
        "passed": steady["p95_ms"] < STEADY_P95_LIMIT_MS,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="request_latency_summary.json")
    args = parser.parse_args()
    result = measure()
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
        handle.write("\n")
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
