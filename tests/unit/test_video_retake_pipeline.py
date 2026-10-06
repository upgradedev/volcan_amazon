"""The video pipeline renders the re-take planned in video/SHOT_LIST.md.

video/capture-local.py must accept the plan's beat ids and refuse any other journey,
press nothing billed unless the owner passes its flag, and keep its refusals.
video/build-video.py must put the cold-open footage in the title slot when
narration.json says so, and keep the title card for a take that asks for one.
Neither script is run here: no browser, no ffmpeg, no request.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib

import pytest

VIDEO = pathlib.Path(__file__).resolve().parents[2] / "video"
PLAN = json.loads((VIDEO / "narration.json").read_text(encoding="utf-8"))
SHA = "9b2bcb9ad4c3ad0f38d150fbc546d7b30a56e062"
LIVE = "https://qylv1gxor9.execute-api.eu-west-1.amazonaws.com"
OLD_BEATS = [
    "beat_01_press",
    "beat_02_what_you_heard",
    "beat_03_open_pull_request",
    "beat_04_request_changes",
    "beat_05_mcp_handshake",
    "beat_06_verification",
]


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, VIDEO / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


capture = load("volcan_video_capture", "capture-local.py")
build = load("volcan_video_build", "build-video.py")


def plan_beats() -> list[str]:
    return [beat["beat_id"] for beat in PLAN["beats"]]


# --- the capture -------------------------------------------------------------

def test_the_capture_accepts_the_planned_beats():
    capture.check_beats(plan_beats())
    assert capture.EXPECTED_BEATS == plan_beats()


@pytest.mark.parametrize("beats", [OLD_BEATS, list(reversed(plan_beats())), plan_beats()[:-1]])
def test_the_capture_refuses_any_other_journey(beats):
    with pytest.raises(SystemExit, match="differ"):
        capture.check_beats(beats)


def test_the_capture_takes_the_cold_open_length_from_the_plan():
    assert capture.check_title_slot(PLAN["cards"]) == PLAN["cold_open"]["seconds"]
    with pytest.raises(SystemExit, match="title_slot"):
        capture.check_title_slot({"title_seconds": 3.0})


def test_billed_presses_are_off_unless_the_owner_passes_the_flag():
    assert capture.billed_presses_allowed([]) is False
    assert capture.billed_presses_allowed(["--something-else"]) is False
    assert capture.billed_presses_allowed([capture.BILLED_FLAG]) is True
    plan = capture.billed_plan()
    assert "2 Amazon Bedrock calls" in plan and capture.BILLED_FLAG in plan
    assert "Nothing was pressed" in plan


@pytest.mark.parametrize(
    ("url", "method", "body", "kind"),
    [
        (f"{LIVE}/api/digest_semantic_diff", "POST", '{"raw_diff":"x","level":0,"engine":"local"}', None),
        (f"{LIVE}/api/digest_semantic_diff", "POST", '{"raw_diff":"x","level":0}', "digest"),
        (f"{LIVE}/api/review/turn", "POST",
         '{"transcript":"open","pr_url":"https://github.com/o/r/pull/2"}', "open_pull_request"),
        (f"{LIVE}/api/review/turn", "POST",
         '{"transcript":"findings","pr_url":"https://github.com/o/r/pull/2"}', None),
        (f"{LIVE}/api/review/turn", "POST", '{"transcript":"confirm","pr_url":null}', None),
        (f"{LIVE}/mcp", "POST", '{"jsonrpc":"2.0","method":"tools/call","id":"1"}', "mcp_tools_call"),
        (f"{LIVE}/mcp", "POST", '{"jsonrpc":"2.0","method":"initialize","id":"1"}', None),
        (f"{LIVE}/api/braille/diff_digest", "POST", '{"raw_diff":"x"}', None),
        (f"{LIVE}/health", "GET", None, None),
    ],
)
def test_the_request_guard_knows_which_requests_bill_a_model_call(url, method, body, kind):
    assert capture.billed_kind(url, method, body) == kind


def healthy() -> dict[str, object]:
    return {
        "source_revision": SHA,
        "bedrock_model_path": {"resolved_capability": "ready_to_attempt"},
        "durable_state": {"resolved_capability": "configured_reachable"},
        "github_review_path": {"resolved_capability": "dry_run_no_token"},
    }


def test_the_capture_accepts_the_live_build_it_was_told_about():
    capture.check_health(healthy(), SHA)
    with pytest.raises(SystemExit, match="configured_reachable"):
        capture.check_health({**healthy(), "durable_state": {"resolved_capability": "process_memory"}}, SHA)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"source_revision": "0" * 40}, "different commit"),
        ({"bedrock_model_path": {"resolved_capability": "no_credentials"}}, "ready_to_attempt"),
        ({"github_review_path": {"resolved_capability": "dry_run_with_token"}}, "dry_run_no_token"),
    ],
)
def test_the_capture_refuses_a_server_the_beats_would_misdescribe(change, message):
    with pytest.raises(SystemExit, match=message):
        capture.check_health({**healthy(), **change}, SHA)


@pytest.mark.parametrize(
    ("sound", "word", "passes"),
    [(0.9, 3.4, True), (2.0, 5.0, True), (2.4, 3.4, False), (0.9, 5.6, False), (None, None, False)],
)
def test_the_cold_open_must_sound_by_2_s_and_speak_by_5_s(sound, word, passes):
    if passes:
        capture.cold_open_gate(sound, word)
    else:
        with pytest.raises(SystemExit, match="Record again"):
            capture.cold_open_gate(sound, word)


def test_the_pull_request_check_uses_the_chosen_url():
    assert capture.pull_request_label("https://github.com/octocat/Hello-World/pull/1") == \
        "octocat/Hello-World pull request 1"
    with pytest.raises(SystemExit, match="VOLCAN_PR_URL"):
        capture.pull_request_label("https://example.com/o/r/pull/1")
    assert capture.cold_open_command(None)[1] == "Findings"
    assert capture.cold_open_command("files")[1] == "File by file"
    with pytest.raises(SystemExit):
        capture.cold_open_command("summary")


# --- the composer ------------------------------------------------------------

STRINGS = {
    "captions": "captions.burn.srt", "style": "FontSize=11", "tag": "tag.txt",
    "unrecorded_label": "unrecorded.txt", "muted": "0",
    "outro_card": "color=c=0x07111f:s=1920x1080:r=25:d=4.5",
}


def test_the_plan_puts_the_cold_open_in_the_title_slot():
    assert build.title_slot_is_cold_open(PLAN["cards"]) is True
    assert build.title_slot_is_cold_open({"title_seconds": 3.0}) is False


def test_the_cold_open_footage_fills_the_title_slot():
    graph = build.video_graph(
        cold_open=True, title_seconds=12.0, total=140.0, trim_lead=60.0, cold_trim_lead=48.0,
        video_per_page=1.0, title_band="title-band.txt", title_card=None, **STRINGS)
    content, outro, concat = graph
    assert content.startswith("[0:v]trim=start=48.0:end=200.2,")
    assert "trim=end=152.0," in content
    assert "textfile='title-band.txt'" in content and "enable='lt(t,12.000)'" in content
    assert "textfile='tag.txt'" in content and "enable='gte(t,12.000)'" in content
    assert "color=c=" not in content and "[title]" not in "".join(graph)
    assert outro.endswith("[outro]")
    assert concat == "[content][outro]concat=n=2:v=1:a=0[v]"


def test_a_take_with_a_title_card_keeps_it():
    graph = build.video_graph(
        cold_open=False, title_seconds=3.0, total=156.0, trim_lead=6.0, cold_trim_lead=None,
        video_per_page=1.0, title_band=None, title_card="color=c=0x07111f:s=1920x1080:r=25:d=3.0",
        **STRINGS)
    content, title, _, concat = graph
    assert content.startswith("[0:v]trim=start=6.0:end=162.2,")
    assert "trim=end=156.0," in content and "title-band" not in content
    assert title.endswith("[title]")
    assert concat == "[title][content][outro]concat=n=3:v=1:a=0[v]"


def test_the_composer_and_the_capture_must_agree_on_the_cold_open():
    receipt = {"coldOpen": {"seconds": 12.0, "trimLeadSeconds": 48.0}}
    assert build.check_cold_open(True, 12.0, 60.0, 1.0, receipt) == 48.0
    with pytest.raises(SystemExit, match="must match"):
        build.check_cold_open(True, 10.0, 58.0, 1.0, receipt)
    with pytest.raises(SystemExit, match="no coldOpen block"):
        build.check_cold_open(True, 12.0, 60.0, 1.0, {})
    with pytest.raises(SystemExit, match="not 12.0 s of page time apart"):
        build.check_cold_open(True, 12.0, 70.0, 1.0, receipt)
    with pytest.raises(SystemExit, match="would be dropped"):
        build.check_cold_open(False, 3.0, 6.0, 1.0, receipt)
    with pytest.raises(SystemExit, match="bounded contract"):
        build.check_cold_open(False, 3.0, 45.0, 1.0, {})
    assert build.check_cold_open(False, 3.0, 6.0, 1.0, {}) is None


def test_the_band_tag_names_the_build_the_capture_recorded():
    assert build.band_tag(LIVE + "/", "9b2bcb9") == \
        "Live build at qylv1gxor9.execute-api.eu-west-1.amazonaws.com, commit 9b2bcb9."
    assert build.band_tag("http://127.0.0.1:8871/", "9b2bcb9").startswith("Local run of commit 9b2bcb9.")


def test_the_closing_card_names_a_system_voice_when_one_was_used():
    rendered = [{"kind": "speech", "renderedWith": "Windows System.Speech, voice Microsoft David Desktop, rate 0"}]
    lines = build.outro_lines_for(PLAN["cards"]["outro_lines"], "9b2bcb9", rendered)
    assert not any(build.PAGE_OWN_SPEECH in line for line in lines)
    assert any("Microsoft David Desktop system voice" in line for line in lines)
    assert any("commit 9b2bcb9." in line for line in lines)
    untouched = build.outro_lines_for(PLAN["cards"]["outro_lines"], "9b2bcb9", [])
    assert any(build.PAGE_OWN_SPEECH in line for line in untouched)


def test_long_card_lines_wrap_inside_the_frame():
    rows = build.card_rows(PLAN["cards"]["outro_lines"])
    for row, headline in rows:
        assert len(row) <= (build.CARD_HEADLINE_CHARACTERS if headline else build.CARD_LINE_CHARACTERS)
    assert " ".join(row for row, headline in rows if headline) == PLAN["cards"]["outro_lines"][0]
    assert build.card_rows(["Volcan", "Narration: synthetic ElevenLabs voice."]) == [
        ("Volcan", True), ("Narration: synthetic ElevenLabs voice.", False)]
