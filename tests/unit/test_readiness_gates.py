"""Tests for the readiness auditor's persona-review predicates.

I1 to I4 read ``docs/PERSONA_REVIEW.md`` and check its substance: procedure steps
with outcomes, three lenses with verdicts and findings, total ownership, and dated
findings whose citations resolve on disk. A gate that cannot fail is not a gate, so
every test below removes exactly one thing from a complete review and asserts which
gate goes red.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT / "ci") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "ci"))

import readiness  # noqa: E402, I001


# A minimal document that satisfies all four gates. Every cited path is a file
# this repository ships, so the citation branch passes against the real tree.
COMPLETE_REVIEW = """# Persona review

Review date: 2026-09-29

| Step | What it asks | Outcome | Evidence |
|---|---|---|---|
| 1 | Does a deployed endpoint answer? | FAIL | `python ci/readiness.py` |
| 2 | What is owner-gated and unmet? | OPEN | `python ci/readiness.py` |
| 3 | Is the track written down? | PASS | `README.md` |
| 4 | Do the surfaces match the code? | PASS | `tests/e2e/test_html_structure.py` |

| Lens | Owner | What it decides | Verdict |
|---|---|---|---|
| Sponsor product owner | maintainer, product row | Is the sponsor product load-bearing? | PARTIAL |
| UX designer | maintainer, interface row | Can a cold visitor use it? | PASS |
| Recruiter | maintainer, engineering bar row | Does it clear an engineering bar? | PASS |

| ID | Lens | Finding | Verdict | Evidence |
|---|---|---|---|---|
| V01-1 | Sponsor product owner | The MCP server answers 23/23 | PASS | `scripts/mcp_conformance.py` |
| V01-2 | Sponsor product owner | The model path never answered | FAIL | `src/infrastructure/bedrock_adapter.py` |
| V06-1 | UX designer | The status moves every turn | PASS | `docs/index.html` |
| V08-1 | Recruiter | 723 tests pass | PASS | `tests/e2e/test_html_structure.py` |
| V08-2 | Recruiter | The narration speaks a stale count | FAIL | `video/narration.json` |
"""


def _exists(path: str) -> bool:
    return (REPO_ROOT / path).is_file()


def _review(text: str = COMPLETE_REVIEW) -> dict[str, tuple[bool, str]]:
    return readiness.evaluate_persona_review_gates(text, _exists)


def test_a_complete_review_passes_all_four_gates():
    outcomes = _review()
    assert [gid for gid, (passed, _) in outcomes.items() if not passed] == []
    assert "2026-09-29" in outcomes["I4"][1]
    assert "Sponsor product owner PARTIAL" in outcomes["I2"][1]


def test_the_gates_read_the_document_this_repository_ships():
    """The gates must point at a file a clone receives, not at a workspace file."""
    assert readiness.PERSONA_REVIEW_DOC == "docs/PERSONA_REVIEW.md"
    assert (REPO_ROOT / readiness.PERSONA_REVIEW_DOC).is_file()


def test_the_audit_reports_all_four_as_passing_from_inside_the_repository():
    """End to end: run the auditor and read I1 to I4 out of its own results."""
    results = {r.gate_id: r for r in readiness.audit_project()}
    for gate_id in ("I1", "I2", "I3", "I4"):
        assert results[gate_id].passed is True, results[gate_id].message
        assert readiness.PERSONA_REVIEW_DOC in results[gate_id].message


def test_a_missing_document_fails_all_four():
    outcomes = _review("")
    assert all(not passed for passed, _ in outcomes.values())
    assert all("is missing" in message for _, message in outcomes.values())


def test_fewer_than_four_procedure_steps_fails_i1():
    trimmed = COMPLETE_REVIEW.replace(
        "| 4 | Do the surfaces match the code? | PASS | `tests/e2e/test_html_structure.py` |\n", "")
    outcomes = _review(trimmed)
    assert outcomes["I1"][0] is False
    assert "3 procedure steps" in outcomes["I1"][1]


def test_a_procedure_step_with_no_outcome_fails_i1():
    outcomes = _review(COMPLETE_REVIEW.replace(
        "| 3 | Is the track written down? | PASS |", "| 3 | Is the track written down? |  |"))
    assert outcomes["I1"][0] is False
    assert "no outcome or no evidence" in outcomes["I1"][1]


def test_an_invented_verdict_is_not_a_verdict():
    outcomes = _review(COMPLETE_REVIEW.replace(
        "| 2 | What is owner-gated and unmet? | OPEN |",
        "| 2 | What is owner-gated and unmet? | LOOKS FINE |"))
    assert outcomes["I1"][0] is False


@pytest.mark.parametrize("lens", readiness.PERSONA_LENSES)
def test_dropping_any_lens_fails_i2(lens):
    outcomes = _review("\n".join(
        line for line in COMPLETE_REVIEW.splitlines() if not line.startswith(f"| {lens} |")))
    assert outcomes["I2"][0] is False, f"{lens} could be deleted without failing I2"
    assert lens in outcomes["I2"][1]


def test_a_lens_with_no_finding_of_its_own_fails_i2():
    """A verdict in the ownership table with nothing behind it is not a review."""
    outcomes = _review("\n".join(
        line for line in COMPLETE_REVIEW.splitlines() if not line.startswith("| V01-1 |")
        and not line.startswith("| V01-2 |")))
    assert outcomes["I2"][0] is False
    assert "Sponsor product owner" in outcomes["I2"][1]


def test_a_finding_attributed_to_a_lens_nobody_owns_fails_i3():
    outcomes = _review(COMPLETE_REVIEW + (
        "| P99-1 | Passing Stranger | Something | PASS | `README.md` |\n"))
    assert outcomes["I3"][0] is False
    assert "Passing Stranger" in outcomes["I3"][1]


def test_an_empty_owner_cell_fails_i3():
    outcomes = _review(COMPLETE_REVIEW.replace("| UX designer | maintainer, interface row |",
                                               "| UX designer |  |"))
    assert outcomes["I3"][0] is False


def test_fewer_than_five_findings_fails_i4():
    outcomes = _review("\n".join(
        line for line in COMPLETE_REVIEW.splitlines() if not line.startswith("| V08-2 |")))
    assert outcomes["I4"][0] is False
    assert "records 4 findings" in outcomes["I4"][1]


def test_an_undated_review_fails_i4():
    outcomes = _review(COMPLETE_REVIEW.replace("Review date: 2026-09-29", ""))
    assert outcomes["I4"][0] is False
    assert "no review date" in outcomes["I4"][1]


def test_a_finding_citing_a_file_that_is_not_there_fails_i4():
    """The citation is a claim about a file. The gate opens the file."""
    outcomes = _review(COMPLETE_REVIEW.replace(
        "`src/infrastructure/bedrock_adapter.py`",
        "`src/infrastructure/bedrock_adapter_missing.py`"))
    assert outcomes["I4"][0] is False
    assert "bedrock_adapter_missing.py" in outcomes["I4"][1]
