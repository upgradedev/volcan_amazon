import pytest

from scripts.latency_statistics import PERCENTILE_METHOD, latency_stats, percentile


def test_percentile_uses_documented_linear_interpolation_instead_of_array_indexing():
    values = [float(value) for value in range(1, 11)]
    assert percentile(values, 0.95) == pytest.approx(9.55)
    result = latency_stats(values)
    assert result["percentile_method"] == PERCENTILE_METHOD
    assert result["p95_ms"] == 9.55
    assert result["raw_samples_ms"] == values


def test_percentile_rejects_empty_or_invalid_input():
    with pytest.raises(ValueError):
        percentile([], 0.95)
    with pytest.raises(ValueError):
        percentile([1.0], 1.1)
