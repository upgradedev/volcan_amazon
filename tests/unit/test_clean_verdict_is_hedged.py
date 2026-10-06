"""A clean findings turn says what a clean rule pass means, and no more.

The findings turn used to answer "No security finding in this change." when
no rule matched. That reads as a verdict on the change, while the rules are
measured to miss risks: on the held-out JavaScript half they caught 5 of 8
(``python scripts/benchmark_js_ts_detection.py --split heldout``). The turn
now says that no rule matched and that the rules can miss a risk, and quotes
the figure the benchmark prints. The ready cue is unchanged: the earcon suite
(tests/unit/test_earcon_encodes_the_verdict.py), UAT-20 and the docs all
promise the rising DIFF_READY cue when nothing was flagged.
"""
import asyncio

from scripts.benchmark_js_ts_detection import measure_splits
from src.application.digest_diff_use_case import DigestDiffUseCase
from src.domain.review_dialogue import (
    CLEAN_FINDINGS_TEXT,
    HELD_OUT_JS_CAUGHT,
    HELD_OUT_JS_TOTAL,
    ReviewDialogue,
)
from src.domain.review_grammar import parse_command
from src.domain.semantic_diff import UnifiedDiffParser
from src.domain.sonification import EarconType
from src.infrastructure.bedrock_adapter import BedrockSynthesisAdapter

CLEAN_PATCH = """diff --git a/src/utils/parser.py b/src/utils/parser.py
--- a/src/utils/parser.py
+++ b/src/utils/parser.py
@@ -4,3 +4,5 @@ def normalise(data):
-    return data.strip()
+    if not data:
+        return ""
+    return data.strip()
"""


def _clean_findings_turn():
    report = asyncio.run(DigestDiffUseCase(BedrockSynthesisAdapter()).execute(CLEAN_PATCH, engine="local"))
    assert not report.critical_findings
    dialogue = ReviewDialogue(session_id="hedge")
    dialogue.load(report)
    return dialogue.apply(parse_command("findings"))


def test_the_clean_turn_says_no_rule_matched_and_that_rules_miss_risks():
    turn = _clean_findings_turn()
    assert turn.spoken == CLEAN_FINDINGS_TEXT
    assert turn.spoken.startswith("No security rule matched this change.")
    assert "can miss a risk" in turn.spoken
    assert "No security finding in this change" not in turn.spoken


def test_the_clean_turn_keeps_the_ready_cue():
    assert _clean_findings_turn().earcon_type is EarconType.DIFF_READY


def test_the_spoken_figure_is_the_one_the_benchmark_prints():
    row = measure_splits()["heldout"]["javascript"]
    assert (row["detected"], row["n_should_flag"]) == (HELD_OUT_JS_CAUGHT, HELD_OUT_JS_TOTAL)
    assert f"caught {row['detected']} of {row['n_should_flag']}" in CLEAN_FINDINGS_TEXT


def test_the_parser_alone_finds_nothing_in_the_clean_patch():
    sections = UnifiedDiffParser.parse_patch(CLEAN_PATCH)
    assert sections and not any(s.security_findings or s.security_flags for s in sections)
