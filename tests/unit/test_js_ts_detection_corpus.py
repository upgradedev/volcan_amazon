"""Pins the JavaScript and TypeScript detection figures quoted in the docs.

The figures come from ``python scripts/benchmark_js_ts_detection.py`` over the
self-authored, synthetic corpus in ``tests/fixtures/diff_corpus_js_ts.py``.
The held-out misses below were measured once, after the rules were frozen on
the training half, and are recorded rather than fixed: fixing them would tune
the rules on the held-out half and make its figure meaningless.

One exception, stated. On 2026-09-28 a string-built SQL rule was added for a
separate reason (an independent review heard a concatenated query as clean),
and it detects ``js-pos-16``, a held-out case this file already named as a
miss for exactly that reason. The rule is measured on its own held-out set
(``tests/fixtures/diff_corpus_classic.py``), but its author had seen
``js-pos-16`` here, so the held-out JavaScript rise from 50.0% to 62.5% is not
a blind measurement for that case.
"""
from scripts.benchmark_js_ts_detection import measure_splits
from tests.fixtures.diff_corpus_js_ts import CASES, SPLIT_SEED, split

KNOWN_MISSES = {
    "train": {
        "javascript": {"js-pos-11"},  # innerHTML sink; no rule reads DOM sinks
        "typescript": {"ts-pos-10", "ts-pos-11"},  # new Function; MD5; no rule for either
    },
    "heldout": {
        # accessLevel is not an authorization word; !includes is a negation,
        # not a flipped operator; cookie flags have no rule. js-pos-16 (SQL
        # interpolation) left this set on 2026-09-28: see the module docstring
        "javascript": {"js-pos-12", "js-pos-13", "js-pos-15"},
        # a middleware no longer mounted is not a removed call; assertCanEdit
        # names no security object
        "typescript": {"ts-pos-08", "ts-pos-15"},
    },
}

#: Every one of these is the keyword pass, which this work did not change.
KNOWN_OVER_FLAGS = {
    "train": {"javascript": {"js-neg-03", "js-neg-04", "js-neg-05"}, "typescript": {"ts-neg-01"}},
    "heldout": {"javascript": set(), "typescript": {"ts-neg-02", "ts-neg-13"}},
}


def test_the_split_is_the_published_one():
    halves = split()
    assert SPLIT_SEED == 20260927
    assert len(CASES) == 64
    assert len(halves["train"]) == len(halves["heldout"]) == 32
    assert not {c.fixture_id for c in halves["train"]} & {c.fixture_id for c in halves["heldout"]}


def test_misses_and_over_flags_are_exactly_the_recorded_ones():
    measured = measure_splits()
    for name, languages in measured.items():
        for language, row in languages.items():
            assert set(row["missed_fixture_ids"]) == KNOWN_MISSES[name][language], (name, language)
            assert set(row["false_positive_fixture_ids"]) == KNOWN_OVER_FLAGS[name][language], (name, language)


def test_no_structural_rule_raises_a_false_alarm_on_either_half():
    for languages in measure_splits().values():
        for row in languages.values():
            assert row["false_positives_from_structural_rule"] == 0


def test_published_figures():
    measured = measure_splits()
    assert measured["train"]["javascript"]["recall_pct"] == 87.5
    assert measured["train"]["typescript"]["recall_pct"] == 75.0
    assert measured["heldout"]["javascript"]["recall_pct"] == 62.5  # 50.0 before the SQL rule
    assert measured["heldout"]["javascript"]["false_positive_pct"] == 0.0
    assert measured["heldout"]["typescript"]["recall_pct"] == 75.0
    assert measured["heldout"]["typescript"]["false_positive_pct"] == 25.0


def test_the_probes_written_after_the_rules_break_them_as_recorded():
    """Eight probes written after the rules, to find where line-at-a-time
    reading breaks (tests/fixtures/diff_corpus_js_ts_probes.py). Measured on
    2026-09-27 as 0 of 4 detected and 4 of 4 over-flagged; the 2026-09-30 rule
    work (logical-line joining, negation cancellation, test-source scope, the
    guard-call rule) moved the record to 4 of 4 detected and 2 of 4
    over-flagged. Both over-flags are the JavaScript must-not-flag probes, so
    the JavaScript false-alarm figure for this round is 2 of 2: probe-01
    (early-return refactor) and probe-03 (local-only wildcard) are false
    alarms. docs/EVIDENCE.md says why the token rules cannot clear them.
    Closing one means changing its expected outcome here and in the docs."""
    from scripts.benchmark_js_ts_detection import measure
    from tests.fixtures.diff_corpus_js_ts_probes import PROBES

    assert len(PROBES) == 8
    rows = measure(PROBES)
    assert set(rows["javascript"]["missed_fixture_ids"]) == set()
    assert set(rows["typescript"]["missed_fixture_ids"]) == set()
    assert set(rows["javascript"]["false_positive_fixture_ids"]) == {"probe-01", "probe-03"}
    assert set(rows["typescript"]["false_positive_fixture_ids"]) == set()
    assert rows["javascript"]["false_positives_from_structural_rule"] == 2
    assert rows["typescript"]["false_positives_from_structural_rule"] == 0


def test_the_second_round_probes_measure_unseen_shapes():
    """Eight new probes against the current rules\u2019 documented scope, labels decided
    from meaning before the rules ran (tests/fixtures/diff_corpus_js_ts_probes_round2.py).
    Measured 2026-10-01: 4 of 4 detected, 1 of 4 over-flagged, but only after
    commit f1c35a1, the same commit that added these probes, exempted test
    files from the CORS rule. Before that exemption the round was 2 of 4
    over-flagged (the next test pins why). The one left, probe2-01, is the
    documented control-flow-equivalence limit in a new shape: an if/else
    rewritten as a guard clause reads as a flipped comparison to token rules.
    """
    from scripts.benchmark_js_ts_detection import measure
    from tests.fixtures.diff_corpus_js_ts_probes_round2 import PROBES_ROUND2

    assert len(PROBES_ROUND2) == 8
    rows = measure(PROBES_ROUND2)
    assert set(rows["javascript"]["missed_fixture_ids"]) == set()
    assert set(rows["typescript"]["missed_fixture_ids"]) == set()
    assert set(rows["javascript"]["false_positive_fixture_ids"]) == {"probe2-01"}
    assert set(rows["typescript"]["false_positive_fixture_ids"]) == set()


def test_the_second_round_figure_before_the_cors_test_file_exemption():
    """The round-2 figure is not untuned. Commit f1c35a1 added these probes
    together with a test-file exemption to the CORS rule, and probe2-02 is a
    wildcard origin in a test fixture. Called as it was before that commit,
    with no file path, the CORS rule flags probe2-02, so the round was 2 of 4
    over-flagged before the exemption (probe2-01 and probe2-02) and 1 of 4
    after it.
    """
    from src.domain.js_security_rules import _find_permissive_cors
    from tests.fixtures.diff_corpus_js_ts_probes_round2 import PROBES_ROUND2

    probe = next(case for case in PROBES_ROUND2 if case.fixture_id == "probe2-02")
    added = [line[1:] for line in probe.raw_diff.splitlines()
             if line.startswith("+") and not line.startswith("+++")]
    assert "test/cors.test.js" in probe.raw_diff
    assert _find_permissive_cors(added), "the pre-f1c35a1 call shape must flag the fixture"
    assert _find_permissive_cors(added, "test/cors.test.js") == []
