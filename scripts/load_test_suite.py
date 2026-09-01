"""In-Process Concurrency & Thread Pool Stress Test Runner for Volcan.

Executes:
- 1,000 in-process AST diff parsing iterations
- 500 PCM 22.05kHz audio waveform syntheses
- 500 in-process governance lease creations
- Measures in-process function execution latency percentiles (P50, P90, P99)

Usage:
    python scripts/load_test_suite.py
"""
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.domain.governed_action import GovernedAction
from src.domain.semantic_diff import UnifiedDiffParser
from src.domain.sonification import AudioTone, WaveformSynthesizer


def run_load_stress_suite():
    print("================================================================")
    print("   VOLCAN IN-PROCESS CONCURRENCY & LATENCY BENCHMARK            ")
    print("================================================================")

    # 1. AST Diff Throughput
    num_diffs = 1000
    sample_diff = """diff --git a/src/auth.py b/src/auth.py
+ kms_key = os.environ.get("KMS_KEY_ID")
+ return verify_kms_token(token, kms_key)"""

    print(f"[*] Firing {num_diffs} concurrent AST diff requests (16 worker threads)...")
    latencies = []
    t_start = time.perf_counter()

    def diff_worker():
        t0 = time.perf_counter()
        UnifiedDiffParser.parse_patch(sample_diff)
        t1 = time.perf_counter()
        latencies.append((t1 - t0) * 1000.0)

    with ThreadPoolExecutor(max_workers=16) as executor:
        list(executor.map(lambda _: diff_worker(), range(num_diffs)))

    total_time = time.perf_counter() - t_start
    rps = num_diffs / total_time
    sorted_lats = sorted(latencies)
    p50 = sorted_lats[int(num_diffs * 0.50)]
    p90 = sorted_lats[int(num_diffs * 0.90)]
    p99 = sorted_lats[int(num_diffs * 0.99)]

    print(f"  -> Completed in {total_time:.3f}s | Throughput: {rps:.1f} req/sec")
    print(f"  -> Latency Percentiles: P50: {p50:.3f} ms | P90: {p90:.3f} ms | P99: {p99:.3f} ms")

    # 2. Audio Synthesis Throughput
    num_audio = 500
    sample_tones = [AudioTone(frequency_hz=440.0, duration_ms=120, volume=0.5)]
    print(f"\n[*] Firing {num_audio} concurrent PCM audio syntheses (16 worker threads)...")
    audio_lats = []
    t_audio_start = time.perf_counter()

    def audio_worker():
        t0 = time.perf_counter()
        WaveformSynthesizer.generate_wav_bytes(sample_tones)
        t1 = time.perf_counter()
        audio_lats.append((t1 - t0) * 1000.0)

    with ThreadPoolExecutor(max_workers=16) as executor:
        list(executor.map(lambda _: audio_worker(), range(num_audio)))

    audio_total = time.perf_counter() - t_audio_start
    audio_rps = num_audio / audio_total
    sorted_audio = sorted(audio_lats)
    a_p50 = sorted_audio[int(num_audio * 0.50)]
    a_p90 = sorted_audio[int(num_audio * 0.90)]
    a_p99 = sorted_audio[int(num_audio * 0.99)]

    print(f"  -> Completed in {audio_total:.3f}s | Throughput: {audio_rps:.1f} audio/sec")
    print(f"  -> Latency Percentiles: P50: {a_p50:.3f} ms | P90: {a_p90:.3f} ms | P99: {a_p99:.3f} ms")

    # 3. Governance Leases
    num_leases = 500
    print(f"\n[*] Firing {num_leases} concurrent governance lease creations...")
    t_lease_start = time.perf_counter()

    def lease_worker(i):
        return GovernedAction.create(
            action_id=f"act_load_{i:04d}",
            action_type="DEPLOY",
            command_or_path=f"aws ecs update-service --cluster prod-{i}",
            summary_spoken=f"Deploy cluster {i}"
        )

    with ThreadPoolExecutor(max_workers=16) as executor:
        leases = list(executor.map(lease_worker, range(num_leases)))

    lease_total = time.perf_counter() - t_lease_start
    lease_rps = num_leases / lease_total
    print(f"  -> Completed in {lease_total:.3f}s | Throughput: {lease_rps:.1f} leases/sec")
    assert len(leases) == num_leases

    print("\n----------------------------------------------------------------")
    print("[*] Load Test Result: 100% SUCCESS | Zero errors, zero deadlocks")
    print("================================================================")


if __name__ == "__main__":
    run_load_stress_suite()
