"""Guards the security-detection numbers published in the README.

The README quotes recall and false-positive rate over the labelled corpus in
``tests/fixtures/diff_corpus.py``. These tests recompute those figures from the
same corpus with the same production parser, so a regression in either the
parser or the corpus turns the published number red instead of stale.
"""
from scripts.benchmark_suite import measure_security_detection
from src.domain.semantic_diff import ChangeCategory, UnifiedDiffParser
from tests.fixtures.diff_corpus import CORPUS, NEGATIVES, POSITIVES

#: Positives this parser does not detect today, recorded rather than removed.
#: Asserting an empty set here would make the corpus unable to hold a case the
#: product has not solved, which is how a detection figure becomes decorative.
#: A regression that misses anything else still fails these tests, and closing a
#: gap means deleting its id from this list.
KNOWN_MISSES = {
    "pos-19",  # an authorization guard block deleted; no rule reads deleted blocks
    "pos-20",  # a permission decorator removed; a bare decorator line does not parse
    "pos-21",  # verify=False added to an outbound call; no rule reads argument values
    "pos-22",  # an IAM policy widened in JSON; no structural rule reads JSON
}

#: Negatives this parser over-flags today. Empty, and it has to stay a set the
#: tests print rather than an assumption, so a new over-flag is named.
KNOWN_OVER_FLAGS: set[str] = set()


def test_corpus_is_balanced_and_labelled():
    assert len(CORPUS) == len(POSITIVES) + len(NEGATIVES)
    assert len(POSITIVES) >= 12
    assert len(NEGATIVES) >= 12
    assert all(case.expect_security_flag for case in POSITIVES)
    assert not any(case.expect_security_flag for case in NEGATIVES)
    assert len({case.fixture_id for case in CORPUS}) == len(CORPUS)


def test_positive_fixtures_flag_except_the_recorded_misses():
    missed = set()
    for case in POSITIVES:
        sections = UnifiedDiffParser.parse_patch(case.raw_diff)
        if not any(section.security_flags for section in sections):
            missed.add(case.fixture_id)
    assert missed == KNOWN_MISSES, (
        f"newly missed: {sorted(missed - KNOWN_MISSES)}; "
        f"now detected, delete from KNOWN_MISSES: {sorted(KNOWN_MISSES - missed)}"
    )


def test_no_negative_fixture_raises_a_security_flag():
    over_flagged = set()
    for case in NEGATIVES:
        sections = UnifiedDiffParser.parse_patch(case.raw_diff)
        if any(section.security_flags for section in sections):
            over_flagged.add(case.fixture_id)
    assert over_flagged == KNOWN_OVER_FLAGS, (
        f"benign patches newly flagged: {sorted(over_flagged - KNOWN_OVER_FLAGS)}"
    )


def test_security_sensitive_patches_are_categorised_critical():
    for case in POSITIVES:
        if case.fixture_id in KNOWN_MISSES:
            continue
        sections = UnifiedDiffParser.parse_patch(case.raw_diff)
        flagged = [s for s in sections if s.security_flags]
        assert flagged, case.fixture_id
        # Test and documentation paths are categorised by path first by design.
        for section in flagged:
            if section.category is ChangeCategory.SECURITY_SENSITIVE:
                assert section.significance.value == "CRITICAL"


def test_published_detection_numbers_match_the_benchmark_script():
    """The README quotes these exact values; the benchmark script produces them."""
    measured = measure_security_detection()
    assert measured["n_total"] == 40
    assert measured["n_should_flag"] == 22
    assert measured["n_should_not_flag"] == 18
    assert measured["recall_pct"] == 81.8
    assert measured["false_positive_pct"] == 0.0
    assert set(measured["missed_fixture_ids"]) == KNOWN_MISSES
