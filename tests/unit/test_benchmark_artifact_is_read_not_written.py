"""The benchmark artifact is read by the auditor and the verify commands, never rewritten.

A judge who runs the commands the README names to verify its numbers must not
be left with a dirty checkout to revert. So ``python scripts/benchmark_suite.py``
measures and prints but writes nothing unless told to, and the readiness gate
that backs the recall claim reads the committed ``benchmarks_summary.json`` and
compares it to the recomputation instead of regenerating it.
"""
import hashlib
import importlib.util
import json
import os

import pytest

from scripts import benchmark_suite

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ARTIFACT = os.path.join(REPO_ROOT, "benchmarks_summary.json")


def _sha256(path: str) -> str:
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def _load_readiness():
    spec = importlib.util.spec_from_file_location("readiness", os.path.join(REPO_ROOT, "ci", "readiness.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def fast_benchmarks(monkeypatch):
    """Ten iterations each, so the suite stays quick and no figure here is a claim."""
    fake = {"iterations": 10, "mean_ms": 0.1, "p50_ms": 0.1, "p95_ms": 0.1, "p99_ms": 0.1}
    monkeypatch.setattr(benchmark_suite, "benchmark_semantic_diff_parser", lambda n=1000: dict(fake))
    monkeypatch.setattr(benchmark_suite, "benchmark_earcon_synthesis", lambda n=1000: dict(fake))
    return fake


def test_a_plain_benchmark_run_leaves_the_tracked_artifact_byte_identical(fast_benchmarks, capsys):
    before = _sha256(ARTIFACT)
    results = benchmark_suite.main([])
    assert _sha256(ARTIFACT) == before
    out = capsys.readouterr().out
    assert "Nothing written" in out and "--write" in out
    # The run still measures and still prints the drift against the record.
    assert results["security_detection"]["n_total"] == 40
    assert "Drift against the committed benchmarks_summary.json" in out


def test_out_writes_the_run_elsewhere_and_the_tracked_artifact_stays_put(fast_benchmarks, tmp_path):
    before = _sha256(ARTIFACT)
    target = tmp_path / "run.json"
    benchmark_suite.main(["--out", str(target)])
    assert _sha256(ARTIFACT) == before
    written = json.loads(target.read_text(encoding="utf-8"))
    assert written["ast_diff_engine"]["iterations"] == 10
    assert written["security_detection"]["recall_pct"] == 81.8


def test_the_recall_gate_reads_the_committed_artifact_and_does_not_touch_it():
    readiness = _load_readiness()
    readme = readiness.read_text("README.md")
    before = _sha256(ARTIFACT)
    passed, message = readiness.check_j3(readme)
    assert _sha256(ARTIFACT) == before
    assert passed is True, message
    assert "equal to the committed benchmarks_summary.json" in message


def test_the_recall_gate_turns_red_when_the_record_and_the_corpus_disagree(monkeypatch):
    readiness = _load_readiness()
    readme = readiness.read_text("README.md")
    real_open = open

    def stale_artifact(path, *args, **kwargs):
        handle = real_open(path, *args, **kwargs)
        if os.path.abspath(str(path)) == ARTIFACT and "r" in (args[0] if args else kwargs.get("mode", "r")):
            data = json.load(handle)
            handle.close()
            data["security_detection"]["recall_pct"] = 12.5
            import io
            return io.StringIO(json.dumps(data))
        return handle

    monkeypatch.setattr("builtins.open", stale_artifact)
    passed, message = readiness.check_j3(readme)
    assert passed is False
    assert "recall_pct=12.5" in message and "--write" in message


def test_the_auditor_names_only_files_that_became_dirty_while_it_ran():
    readiness = _load_readiness()
    touched = readiness.files_the_audit_touched({"README.md"}, {"README.md", "benchmarks_summary.json"})
    assert touched == ["benchmarks_summary.json"]
    # Dirt that was there before the audit is the developer's, not the auditor's.
    assert readiness.files_the_audit_touched({"README.md"}, {"README.md"}) == []
    # Without git there is nothing to compare, and the auditor does not guess.
    assert readiness.files_the_audit_touched(None, {"x"}) == []
