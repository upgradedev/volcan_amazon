"""Shared, explicit latency statistics used by benchmarks and CI gates."""
import math
import statistics

PERCENTILE_METHOD = "linear interpolation at index (n - 1) * q"


def percentile(values: list[float], q: float) -> float:
    """Return a linearly interpolated quantile for ``0 <= q <= 1``."""
    if not values:
        raise ValueError("at least one sample is required")
    if not 0.0 <= q <= 1.0:
        raise ValueError("q must be between zero and one")
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def latency_stats(values_ms: list[float]) -> dict[str, object]:
    ordered = sorted(values_ms)
    return {
        "iterations": len(ordered),
        "percentile_method": PERCENTILE_METHOD,
        "mean_ms": round(statistics.mean(ordered), 3),
        "p50_ms": round(percentile(ordered, 0.50), 3),
        "p95_ms": round(percentile(ordered, 0.95), 3),
        "p99_ms": round(percentile(ordered, 0.99), 3),
        "raw_samples_ms": [round(value, 6) for value in ordered],
    }
