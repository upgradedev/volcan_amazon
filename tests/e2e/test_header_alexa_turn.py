"""The header's example Alexa+ turn must be what the product says.

A blind panel on 2026-10-05 found that the first track-fit words a judge read
were "Not an Alexa skill", and that nothing above the fold showed an Alexa+
style turn. The header now leads with the track fit, then shows one static
example turn: the request a user says and the first sentence Volcan answers.

Static text in the header could drift from the product, and a sentence the
server no longer says would be a lie in the shop window. So the turn is
replayed here: the page's own shipped patch is opened through the same
``POST /api/review/turn`` the page's simulated front end uses, the card's
request is sent word for word, and the first sentence of the answer must equal
the card's sentence. The page's on-load preview shows the first sentence of
``POST /api/digest_semantic_diff`` for the same patch, so that is compared too.

The model path is replaced by the local engine for the run, so the test never
starts a billed model call even where AWS credentials resolve. The finding is
the first sentence under either engine (``SemanticDiffReport.to_voice_summary``).
"""
import html as html_lib
import re
import uuid

import pytest
from fastapi.testclient import TestClient

from src.application.digest_diff_use_case import LOCAL_ENGINE_REQUESTED
from src.interfaces import composition
from src.interfaces.mcp_server import app
from tests.e2e.test_shipped_presets_reach_their_rule import read_html, shipped_presets

#: The page's own first-sentence split, from ``previewSentence`` in docs/index.html.
FIRST_SENTENCE = re.compile(r"\.\s+(?=[A-Z0-9])")


def header() -> str:
    return read_html().split("<main", 1)[0]


def text_of(element_id: str) -> str:
    """The visible text of one header element, tags dropped and entities decoded."""
    match = re.search(rf'id="{element_id}"[^>]*>(.*?)</(?:dd|p|figcaption)>', header(), flags=re.S)
    assert match, f"the header has no #{element_id}"
    plain = html_lib.unescape(re.sub(r"<[^>]+>", "", match.group(1)))
    return re.sub(r"\s+", " ", plain).strip()


def unquote(text: str) -> str:
    return text.strip().strip("“”\"").strip()


def first_sentence(text: str) -> str:
    split = FIRST_SENTENCE.search(text)
    return text if split is None else text[: split.start() + 1]


@pytest.fixture
def local_engine(monkeypatch):
    """Answer every digest with the local engine, as the page's preview does."""
    adapter = composition.bedrock_adapter

    async def local(raw_diff, sections):
        return adapter.summarize_locally(raw_diff, sections, LOCAL_ENGINE_REQUESTED)

    monkeypatch.setattr(adapter, "summarize_diff", local)


def test_the_header_turn_is_the_dialogue_answer_for_the_shipped_patch(local_engine):
    client = TestClient(app)
    patch = shipped_presets()[1]
    session = f"header-turn-{uuid.uuid4().hex[:8]}"

    opened = client.post("/api/review/turn", json={
        "session_id": session, "transcript": "open", "raw_diff": patch}).json()
    assert opened["state"] == "OVERVIEW", opened

    ask = unquote(text_of("alexaTurnAsk")).rstrip(".")
    answered = client.post("/api/review/turn", json={
        "session_id": session, "transcript": ask.lower(), "raw_diff": patch}).json()
    assert answered["readback"] == f"Understood: {ask.lower()}.", (
        "the card's request is not a command the dialogue understands")

    assert unquote(text_of("alexaTurnAnswer")) == first_sentence(answered["spoken"]), (
        "the header quotes a sentence the server no longer says first")


def test_the_header_turn_matches_the_first_sentence_the_preview_draws(local_engine):
    client = TestClient(app)
    body = client.post("/api/digest_semantic_diff", json={
        "raw_diff": shipped_presets()[1], "level": 0, "engine": "local"}).json()
    assert unquote(text_of("alexaTurnAnswer")) == first_sentence(body["voice_summary"])


def test_the_track_fit_leads_and_the_disclosure_qualifies_it_above_the_fold():
    head = header()
    fit = text_of("trackFit")
    assert "live MCP server (spec 2025-11-25)" in fit
    assert "simulated Alexa+ front end" in fit
    assert "hackathon FAQ" in fit
    label = text_of("alexaTurnLabel")
    assert "Static example" in label and "simulated Alexa+" in label
    assert "Not an Alexa skill." in text_of("notASkill")
    # Order, not truth: the positive statement first, the qualification after.
    assert head.index('id="trackFit"') < head.index('id="alexaTurn"') < head.index('id="notASkill"')
    assert head.index("<h1") < head.index('id="trackFit"')
    # The example is static markup: nothing announces it or animates it.
    card = head.split('id="alexaTurn"', 1)[1].split("</figure>", 1)[0]
    assert "aria-live" not in card and 'role="status"' not in card


@pytest.mark.parametrize("button_id, visible", [
    ("voiceMode", "My screen reader"),
    ("keymapOpen", "Keyboard map"),
])
def test_the_header_buttons_show_the_start_of_their_accessible_name(button_id, visible):
    """WCAG 2.5.3, label in name: the visible words open the aria-label, so a
    voice-control user can say what a magnifier user reads."""
    match = re.search(rf'<button\b[^>]*\bid="{button_id}"[^>]*>(.*?)</button>', header(), flags=re.S)
    assert match, f"the header has no #{button_id}"
    tag = re.search(rf'<button\b[^>]*\bid="{button_id}"[^>]*>', header(), flags=re.S).group(0)
    label = re.search(r'aria-label="([^"]*)"', tag).group(1)
    shown = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", match.group(1))).strip()
    assert shown == visible
    assert label.startswith(visible), f"'{visible}' is not the start of '{label}'"
