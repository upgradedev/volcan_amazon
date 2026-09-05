"""Guards the security-detection numbers published in the README.

The README quotes recall and false-positive rate over the labelled corpus in
``tests/fixtures/diff_corpus.py``. These tests recompute those figures from the
same corpus with the same production parser, so a regression in either the
parser or the corpus turns the published number red instead of stale.
"""
from scripts.benchmark_suite import measure_security_detection
from src.domain.semantic_diff import ChangeCategory, UnifiedDiffParser
from tests.fixtures.diff_corpus import CORPUS, NEGATIVES, POSITIVES


def test_corpus_is_balanced_and_labelled():
    assert len(CORPUS) == len(POSITIVES) + len(NEGATIVES)
    assert len(POSITIVES) >= 12
    assert len(NEGATIVES) >= 12
    assert all(case.expect_security_flag for case in POSITIVES)
    assert not any(case.expect_security_flag for case in NEGATIVES)
    assert len({case.fixture_id for case in CORPUS}) == len(CORPUS)


def test_every_positive_fixture_raises_a_security_flag():
    missed = []
    for case in POSITIVES:
        sections = UnifiedDiffParser.parse_patch(case.raw_diff)
        if not any(section.security_flags for section in sections):
            missed.append(case.fixture_id)
    assert missed == [], f"Security patches that produced no flag: {missed}"


def test_no_negative_fixture_raises_a_security_flag():
    over_flagged = []
    for case in NEGATIVES:
        sections = UnifiedDiffParser.parse_patch(case.raw_diff)
        if any(section.security_flags for section in sections):
            over_flagged.append(case.fixture_id)
    assert over_flagged == [], f"Benign patches that were flagged: {over_flagged}"


def test_security_sensitive_patches_are_categorised_critical():
    for case in POSITIVES:
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
    assert measured["n_total"] == 24
    assert measured["n_should_flag"] == 12
    assert measured["n_should_not_flag"] == 12
    assert measured["recall_pct"] == 100.0
    assert measured["false_positive_pct"] == 0.0
