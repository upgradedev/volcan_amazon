"""Security-flag detection over the JavaScript and TypeScript corpus, per split.

The corpus is ``tests/fixtures/diff_corpus_js_ts.py``: 64 self-authored,
synthetic patches, 16 of each language and label. It is split once by the
fixed rule in ``split()`` (seed 20260927) into a training half, which the
JavaScript and TypeScript rules were tuned against, and a held-out half, which
was not looked at case by case while tuning.

Run command:
    python scripts/benchmark_js_ts_detection.py                  # both splits
    python scripts/benchmark_js_ts_detection.py --split train
    python scripts/benchmark_js_ts_detection.py --split heldout --aggregate-only

Nothing is written. Every figure is recomputed from the production parser.

A case counts as detected when any file section of its patch carries a security
flag, the same test ``scripts/benchmark_suite.py`` applies to the Python corpus.
Each detection is also attributed: "structural" when a structural rule fired
(an inverted authorization check, a widened cross-origin policy, a removed
verification call), "keyword" when only the vocabulary pass fired.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.domain.semantic_diff import UnifiedDiffParser  # noqa: E402
from tests.fixtures.diff_corpus_js_ts import CASES, SPLIT_SEED, split  # noqa: E402

STRUCTURAL_RULES = {"authz_comparison_inverted", "permissive_cors_origin", "security_call_removed"}
LANGUAGES = ("javascript", "typescript")


def _flags(raw_diff: str) -> list[str]:
    flags: list[str] = []
    for section in UnifiedDiffParser.parse_patch(raw_diff):
        flags.extend(section.security_flags)
    return flags


def _pct(numerator: int, denominator: int) -> float:
    return round(100.0 * numerator / denominator, 1) if denominator else 0.0


def measure(cases) -> dict[str, dict[str, object]]:
    """Recall, false positives and attribution, per language."""
    report: dict[str, dict[str, object]] = {}
    for language in LANGUAGES:
        subset = [case for case in cases if case.language == language]
        positives = [case for case in subset if case.expect_security_flag]
        negatives = [case for case in subset if not case.expect_security_flag]
        detected, missed, over_flagged = [], [], []
        structural, keyword_only = 0, 0
        for case in positives:
            flags = _flags(case.raw_diff)
            if flags:
                detected.append(case.fixture_id)
                if STRUCTURAL_RULES & set(flags):
                    structural += 1
                else:
                    keyword_only += 1
            else:
                missed.append(case.fixture_id)
        over_flag_structural = 0
        for case in negatives:
            flags = _flags(case.raw_diff)
            if flags:
                over_flagged.append(case.fixture_id)
                if STRUCTURAL_RULES & set(flags):
                    over_flag_structural += 1
        report[language] = {
            "n_should_flag": len(positives),
            "n_should_not_flag": len(negatives),
            "detected": len(detected),
            "recall_pct": _pct(len(detected), len(positives)),
            "detected_by_structural_rule": structural,
            "detected_by_keyword_only": keyword_only,
            "false_positives": len(over_flagged),
            "false_positive_pct": _pct(len(over_flagged), len(negatives)),
            "false_positives_from_structural_rule": over_flag_structural,
            "missed_fixture_ids": missed,
            "false_positive_fixture_ids": over_flagged,
        }
    return report


def measure_splits() -> dict[str, dict[str, dict[str, object]]]:
    halves = split()
    return {name: measure(halves[name]) for name in ("train", "heldout")}


def main(argv: list[str] | None = None) -> dict:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--split", choices=("train", "heldout", "both"), default="both")
    parser.add_argument("--aggregate-only", action="store_true",
                        help="print counts and rates only, never fixture ids")
    args = parser.parse_args(argv)

    halves = split()
    names = ("train", "heldout") if args.split == "both" else (args.split,)
    print(f"JS/TS security detection. Corpus: {len(CASES)} self-authored synthetic patches; "
          f"split seed {SPLIT_SEED}, stratified by language and label, 50/50.")
    results = {}
    for name in names:
        results[name] = measure(halves[name])
        print(f"\n[{name}] {len(halves[name])} cases")
        for language, row in results[name].items():
            print(f"  {language}: recall {row['recall_pct']}% ({row['detected']}/{row['n_should_flag']}; "
                  f"structural {row['detected_by_structural_rule']}, keyword only {row['detected_by_keyword_only']}), "
                  f"false positives {row['false_positive_pct']}% ({row['false_positives']}/{row['n_should_not_flag']}; "
                  f"from a structural rule {row['false_positives_from_structural_rule']})")
            if not args.aggregate_only:
                print(f"    missed: {', '.join(row['missed_fixture_ids']) or 'none'}")
                print(f"    over-flagged: {', '.join(row['false_positive_fixture_ids']) or 'none'}")
    return results


if __name__ == "__main__":
    main()
