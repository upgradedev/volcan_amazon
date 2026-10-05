"""What a speech engine is handed names every code operator, and no enum.

A review heard the product's own answers carry raw symbols and identifiers:
"user.role == 'admin' became user.role != 'admin'", "Category: BUSINESS_LOGIC.
Significance is LOW.", "(+3, -1)" and "removed 1 lines". The display text keeps
the literal code; the string handed to a synthesiser names the operators, and
every count agrees with its noun.
"""
from fastapi.testclient import TestClient

from src.domain.spoken_form import speakable
from src.interfaces.mcp_server import app

INVERTED = """diff --git a/src/auth/permissions.py b/src/auth/permissions.py
--- a/src/auth/permissions.py
+++ b/src/auth/permissions.py
@@ -10,3 +10,3 @@ def can_delete_workspace(user, workspace):
-    return user.role == "admin"
+    return user.role != "admin"
"""

CLEAN = """diff --git a/src/utils/parser.py b/src/utils/parser.py
--- a/src/utils/parser.py
+++ b/src/utils/parser.py
@@ -4,3 +4,5 @@ def normalise(data):
-    return data.strip()
+    if not data:
+        return ""
+    return data.strip()
"""


def test_operators_are_named_longest_first():
    assert speakable("a != b") == "a not equals b"
    assert speakable("a == b") == "a equals equals b"
    assert speakable("a !== b and c === d") == "a not triple equals b and c triple equals d"
    assert speakable("x<=1 || y>=2 && z") == "x less than or equal to 1 logical or y greater than or equal to 2 logical and z"
    assert speakable("allow_origins = ['*']") == "allow_origins = ['star']"
    assert speakable("No code here.") == "No code here."


def test_the_digest_returns_a_spoken_form_beside_the_literal_text():
    body = TestClient(app).post(
        "/api/digest_semantic_diff", json={"raw_diff": INVERTED, "level": 0, "engine": "local"},
    ).json()
    assert "user.role != 'admin'" in body["voice_summary"]
    spoken = body["voice_summary_for_speech"]
    assert "user.role not equals 'admin'" in spoken and "equals equals 'admin'" in spoken
    assert "!=" not in spoken and "==" not in spoken


def test_level_one_and_the_drill_down_speak_words_not_enums():
    client = TestClient(app)
    level1 = client.post(
        "/api/digest_semantic_diff", json={"raw_diff": CLEAN, "level": 1, "engine": "local"},
    ).json()["voice_summary"]
    assert "business logic, 3 lines added, 1 removed." in level1, level1
    assert "BUSINESS_LOGIC" not in level1 and "(+" not in level1

    drill = client.post("/api/drill_down_section", json={"raw_diff": CLEAN, "section_index": 0}).json()
    text = drill["spoken_text"]
    assert text == "Inspecting src/utils/parser.py: business logic, low significance. 3 lines added, 1 removed.", text
    assert "1 lines" not in text and "Category:" not in text
    # The raw values stay machine-readable in their own fields.
    assert drill["category"] == "BUSINESS_LOGIC" and drill["significance"] == "LOW"
    assert drill["spoken_text_for_speech"] == text


def test_a_review_turn_hands_the_speech_engine_named_operators():
    client = TestClient(app)
    payload = {"session_id": "spoken-form", "user_id": "dev", "raw_diff": INVERTED}
    client.post("/api/review/turn", json={**payload, "transcript": "open"})
    turn = client.post("/api/review/turn", json={**payload, "transcript": "summary"}).json()
    assert "!=" in turn["spoken"]
    assert "not equals" in turn["spoken_for_speech"] and "!=" not in turn["spoken_for_speech"]
    assert turn["readback_for_speech"] == turn["readback"]


def test_model_markdown_is_stripped_for_speech():
    """A live Bedrock answer reached a speech engine as "**Spoken summary:**"
    and "*not*". Stars are read aloud or drop the word; the spoken form
    keeps the words and loses the markup.
    """
    assert speakable("**Spoken summary:** In permissions dot py, the user *not* be an admin.") == (
        "Spoken summary: In permissions dot py, the user not be an admin."
    )
    assert speakable("***urgent*** review") == "urgent review"
    assert speakable("run `make test` now") == "run make test now"
    assert speakable("see [the rule](https://example.invalid/r)") == "see the rule"
    assert speakable("# Findings\n- one\n- two") == "Findings\none\ntwo"


def test_stars_shaped_like_code_survive_the_strip():
    """The strip must not eat the code the spoken form exists to protect."""
    assert speakable("a*b*c") == "a*b*c"
    assert speakable("2 * 3 * x") == "2 * 3 * x"
    assert speakable("2**10") == "2**10"
    assert speakable("a**b**c here") == "a**b**c here"
    assert speakable("**2** to the **10**") == "**2** to the **10**"
    assert speakable("allow_origins = ['*']") == "allow_origins = ['star']"
    assert speakable("a != b") == "a not equals b"


def test_underscore_multi_word_and_blockquote_markup_is_stripped_for_speech():
    """Models also write _emphasis_, __bold__, *several words* and '>' quotes.
    Each reached the ear as underscores, stars or "greater than"."""
    assert speakable("the user *does not* need to be an admin") == "the user does not need to be an admin"
    assert speakable("*very* *important*") == "very important"
    assert speakable("see *the rule.*") == "see the rule."
    assert speakable("_not_ an admin") == "not an admin"
    assert speakable("__Note:__ read this") == "Note: read this"
    assert speakable("> quoted line\n> > nested") == "quoted line\nnested"
    assert speakable("> - bullet in a quote") == "bullet in a quote"
    assert speakable("> **Finding:** user.role != 'admin'") == "Finding: user.role not equals 'admin'"


def test_underscores_and_angle_brackets_shaped_like_code_survive_the_strip():
    """The new patterns keep the guards the star patterns have."""
    assert speakable("__init__ runs first") == "__init__ runs first"
    assert speakable("the `__main__` module") == "the __main__ module"
    assert speakable("user_role_id stays") == "user_role_id stays"
    assert speakable("a_b and c_d") == "a_b and c_d"
    assert speakable("src/_internal_/x.py") == "src/_internal_/x.py"
    assert speakable("call _private() then") == "call _private() then"
    assert speakable("def f(*args, **kwargs)") == "def f(*args, **kwargs)"
    assert speakable("*.py and *.js") == "*.py and *.js"
    assert speakable(">>> print(x)") == ">>> print(x)"
    assert speakable("x >= 3 here") == "x greater than or equal to 3 here"
