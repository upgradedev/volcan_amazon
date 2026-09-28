"""Detection of three classic vulnerability families, per language, on a held-out set.

The set is ``tests/fixtures/diff_corpus_classic.py``: 72 self-authored,
synthetic patches, written and committed before any rule for these families
existed. For each of Python, JavaScript and TypeScript and each family
(string-built SQL, TLS certificate checks turned off, a shell command built
from input) it holds four patches that must flag and four that must not.

Run command:
    python scripts/benchmark_classic_families.py
    python scripts/benchmark_classic_families.py --aggregate-only

Nothing is written. Every figure is recomputed from the production parser.

Two recall figures are printed for each language, because the defect this set
was written for is not only a missing flag:

* "any flag": the case carries at least one security flag of any kind, the
  test ``scripts/benchmark_suite.py`` applies to the Python corpus. The keyword
  pass counts here, so ``shell=True`` is "detected" by the word alone.
* "named": the case carries the rule written for its own family, so the first
  thing a listener hears names what happened (``sql_built_from_strings``,
  ``tls_verification_disabled``, ``shell_command_from_input``).

False positives are split the same way: any flag on a patch that must not
flag, and how many of those came from one of the three family rules rather
than the keyword pass.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.domain.semantic_diff import UnifiedDiffParser  # noqa: E402
from tests.fixtures.diff_corpus_classic import CASES, FAMILIES, LANGUAGES  # noqa: E402

#: The rule each family is named by when it fires.
FAMILY_RULES = {
    "sql": "sql_built_from_strings",
    "tls": "tls_verification_disabled",
    "shell": "shell_command_from_input",
}


def _flags(raw_diff: str) -> list[str]:
    flags: list[str] = []
    for section in UnifiedDiffParser.parse_patch(raw_diff):
        flags.extend(section.security_flags)
    return flags


def _pct(numerator: int, denominator: int) -> float:
    return round(100.0 * numerator / denominator, 1) if denominator else 0.0


def measure(cases=CASES) -> dict[str, dict[str, object]]:
    """Per language: recall (any flag, named), false positives, and per family."""
    family_rules = set(FAMILY_RULES.values())
    report: dict[str, dict[str, object]] = {}
    for language in LANGUAGES:
        subset = [case for case in cases if case.language == language]
        positives = [case for case in subset if case.expect_security_flag]
        negatives = [case for case in subset if not case.expect_security_flag]
        detected, named, missed, over_flagged, over_flagged_by_rule = [], [], [], [], []
        per_family: dict[str, dict[str, int]] = {
            family: {"should_flag": 0, "detected": 0, "named": 0, "should_not_flag": 0, "false_positives": 0}
            for family in FAMILIES
        }
        for case in positives:
            flags = set(_flags(case.raw_diff))
            row = per_family[case.family]
            row["should_flag"] += 1
            if flags:
                detected.append(case.fixture_id)
                row["detected"] += 1
            else:
                missed.append(case.fixture_id)
            if FAMILY_RULES[case.family] in flags:
                named.append(case.fixture_id)
                row["named"] += 1
        for case in negatives:
            flags = set(_flags(case.raw_diff))
            per_family[case.family]["should_not_flag"] += 1
            if flags:
                over_flagged.append(case.fixture_id)
                per_family[case.family]["false_positives"] += 1
                if flags & family_rules:
                    over_flagged_by_rule.append(case.fixture_id)
        report[language] = {
            "n_should_flag": len(positives),
            "n_should_not_flag": len(negatives),
            "detected": len(detected),
            "recall_pct": _pct(len(detected), len(positives)),
            "named": len(named),
            "named_recall_pct": _pct(len(named), len(positives)),
            "false_positives": len(over_flagged),
            "false_positive_pct": _pct(len(over_flagged), len(negatives)),
            "false_positives_from_family_rule": len(over_flagged_by_rule),
            "missed_fixture_ids": missed,
            "not_named_fixture_ids": [c.fixture_id for c in positives if c.fixture_id not in named],
            "false_positive_fixture_ids": over_flagged,
            "false_positive_by_family_rule_fixture_ids": over_flagged_by_rule,
            "per_family": per_family,
        }
    return report


def main(argv: list[str] | None = None) -> dict:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--aggregate-only", action="store_true",
                        help="print counts and rates only, never fixture ids")
    args = parser.parse_args(argv)

    results = measure()
    print(f"Classic families (string-built SQL, TLS checks off, shell from input). Held-out set: "
          f"{len(CASES)} self-authored synthetic patches written before the rules; "
          "4 must flag and 4 must not per language and family.")
    for language, row in results.items():
        print(f"\n  {language}: recall {row['recall_pct']}% any flag ({row['detected']}/{row['n_should_flag']}), "
              f"{row['named_recall_pct']}% named by the family's rule ({row['named']}/{row['n_should_flag']}); "
              f"false positives {row['false_positive_pct']}% ({row['false_positives']}/{row['n_should_not_flag']}; "
              f"from a family rule {row['false_positives_from_family_rule']})")
        for family, counts in row["per_family"].items():
            print(f"    {family}: flagged {counts['detected']}/{counts['should_flag']}, "
                  f"named {counts['named']}/{counts['should_flag']}, "
                  f"false positives {counts['false_positives']}/{counts['should_not_flag']}")
        if not args.aggregate_only:
            print(f"    missed: {', '.join(row['missed_fixture_ids']) or 'none'}")
            print(f"    not named: {', '.join(row['not_named_fixture_ids']) or 'none'}")
            print(f"    over-flagged: {', '.join(row['false_positive_fixture_ids']) or 'none'}")
            print(f"    over-flagged by a family rule: "
                  f"{', '.join(row['false_positive_by_family_rule_fixture_ids']) or 'none'}")
    return results


if __name__ == "__main__":
    main()
