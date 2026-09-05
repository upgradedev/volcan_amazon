"""Reproducible benchmark suite for the Volcan AST diff and sonification engines.

Everything printed here is measured during the run. Nothing is hardcoded.

Measures:
- AST diff parser latency (mean, p50, p95, p99) over N iterations
- Earcon synthesis latency (mean, p50, p95, p99) over N iterations
- Security-flag detection recall and false-positive rate over the hand-labelled
  corpus in ``tests/fixtures/diff_corpus.py``

Run command:
    python scripts/benchmark_suite.py
"""
import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.domain.semantic_diff import UnifiedDiffParser  # noqa: E402
from src.domain.sonification import AudioTone, WaveformSynthesizer  # noqa: E402
from tests.fixtures.diff_corpus import CORPUS, NEGATIVES, POSITIVES  # noqa: E402

SAMPLE_DIFF = POSITIVES[0].raw_diff


def _latency_stats(latencies_ms: list[float], iterations: int) -> dict[str, float]:
    ordered = sorted(latencies_ms)
    return {
        "iterations": iterations,
        "mean_ms": round(statistics.mean(ordered), 3),
        "p50_ms": round(statistics.median(ordered), 3),
        "p95_ms": round(ordered[min(int(0.95 * len(ordered)), len(ordered) - 1)], 3),
        "p99_ms": round(ordered[min(int(0.99 * len(ordered)), len(ordered) - 1)], 3),
    }


def benchmark_semantic_diff_parser(iterations: int = 1000) -> dict[str, float]:
    latencies_ms: list[float] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        UnifiedDiffParser.parse_patch(SAMPLE_DIFF)
        latencies_ms.append((time.perf_counter() - t0) * 1000.0)
    return _latency_stats(latencies_ms, iterations)


def benchmark_earcon_synthesis(iterations: int = 1000) -> dict[str, float]:
    tones = [
        AudioTone(frequency_hz=440.0, duration_ms=50),
        AudioTone(frequency_hz=880.0, duration_ms=80),
    ]
    latencies_ms: list[float] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        WaveformSynthesizer.generate_wav_bytes(tones)
        latencies_ms.append((time.perf_counter() - t0) * 1000.0)
    return _latency_stats(latencies_ms, iterations)


def measure_security_detection() -> dict[str, object]:
    """Runs the real parser over the labelled corpus and counts real outcomes."""
    true_positive = 0
    false_negative_ids: list[str] = []
    false_positive_ids: list[str] = []

    for case in CORPUS:
        sections = UnifiedDiffParser.parse_patch(case.raw_diff)
        flagged = any(section.security_flags for section in sections)
        if case.expect_security_flag and flagged:
            true_positive += 1
        elif case.expect_security_flag and not flagged:
            false_negative_ids.append(case.fixture_id)
        elif not case.expect_security_flag and flagged:
            false_positive_ids.append(case.fixture_id)

    positives = len(POSITIVES)
    negatives = len(NEGATIVES)
    return {
        "corpus_file": "tests/fixtures/diff_corpus.py",
        "n_total": len(CORPUS),
        "n_should_flag": positives,
        "n_should_not_flag": negatives,
        "detected": true_positive,
        "recall_pct": round(100.0 * true_positive / positives, 1),
        "false_positive_pct": round(100.0 * len(false_positive_ids) / negatives, 1),
        "missed_fixture_ids": false_negative_ids,
        "false_positive_fixture_ids": false_positive_ids,
    }


def main() -> None:
    print("================================================================")
    print("       VOLCAN REPRODUCIBLE BENCHMARK SUITE                       ")
    print("================================================================")

    diff_bench = benchmark_semantic_diff_parser(1000)
    audio_bench = benchmark_earcon_synthesis(1000)
    security = measure_security_detection()

    print("\n[1] AST diff parser (1,000 iterations):")
    for key in ("mean_ms", "p50_ms", "p95_ms", "p99_ms"):
        print(f"    - {key}: {diff_bench[key]} ms")

    print("\n[2] Earcon synthesizer (1,000 iterations):")
    for key in ("mean_ms", "p50_ms", "p95_ms", "p99_ms"):
        print(f"    - {key}: {audio_bench[key]} ms")

    print("\n[3] Security-flag detection over the labelled corpus:")
    print(f"    - Corpus size:        n={security['n_total']}"
          f" ({security['n_should_flag']} should flag, {security['n_should_not_flag']} should not)")
    print(f"    - Recall:             {security['recall_pct']}%"
          f" ({security['detected']}/{security['n_should_flag']})")
    print(f"    - False positives:    {security['false_positive_pct']}%")
    if security["missed_fixture_ids"]:
        print(f"    - Missed fixtures:    {', '.join(security['missed_fixture_ids'])}")
    if security["false_positive_fixture_ids"]:
        print(f"    - Over-flagged:       {', '.join(security['false_positive_fixture_ids'])}")

    results = {
        "generated_by": "python scripts/benchmark_suite.py",
        "python_version": sys.version.split()[0],
        "ast_diff_engine": diff_bench,
        "earcon_synthesizer": audio_bench,
        "security_detection": security,
    }

    out_path = os.path.join(os.path.dirname(__file__), "..", "benchmarks_summary.json")
    with open(os.path.abspath(out_path), "w", encoding="utf-8") as handle:
        json.dump(results, handle, indent=2)
        handle.write("\n")

    print("\n================================================================")
    print("  Results written to benchmarks_summary.json")
    print("================================================================")


if __name__ == "__main__":
    main()
