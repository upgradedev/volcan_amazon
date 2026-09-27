"""Pins the JavaScript and TypeScript detection figures quoted in the docs.

The figures come from ``python scripts/benchmark_js_ts_detection.py`` over the
self-authored, synthetic corpus in ``tests/fixtures/diff_corpus_js_ts.py``.
The held-out misses below were measured once, after the rules were frozen on
the training half, and are recorded rather than fixed: fixing them would tune
the rules on the held-out half and make its figure meaningless.
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
        # not a flipped operator; cookie flags and SQL interpolation have no rule
        "javascript": {"js-pos-12", "js-pos-13", "js-pos-15", "js-pos-16"},
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
    assert measured["heldout"]["javascript"]["recall_pct"] == 50.0
    assert measured["heldout"]["javascript"]["false_positive_pct"] == 0.0
    assert measured["heldout"]["typescript"]["recall_pct"] == 75.0
    assert measured["heldout"]["typescript"]["false_positive_pct"] == 25.0
