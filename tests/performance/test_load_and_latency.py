"""Load and Latency QA Benchmark for Amazon Developer Hackathon 2026."""
from scripts.measure_request_latency import STEADY_P95_LIMIT_MS, measure


def test_concurrent_load_and_latency_benchmark():
    result = measure()
    steady = result["steady_state"]
    assert steady["iterations"] == 100
    assert len(steady["raw_samples_ms"]) == 100
    assert result["first_request_ms"] >= 0
    assert steady["p95_ms"] < STEADY_P95_LIMIT_MS, (
        f"steady-state p95 {steady['p95_ms']:.2f}ms exceeded {STEADY_P95_LIMIT_MS:.0f}ms; "
        f"raw samples: {steady['raw_samples_ms']}"
    )
