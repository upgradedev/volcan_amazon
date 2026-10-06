"""The video pipeline renders the re-take planned in video/SHOT_LIST.md.

video/capture-local.py must accept the plan's beat ids and refuse any other journey,
press nothing billed unless the owner passes its flag, keep its refusals, and run a
free rehearsal only against a local server that cannot reach Amazon Bedrock.
video/build-video.py must play a title card, then the cold-open footage when
narration.json says so, keep the closing card short enough for the sync gate to read
it as a card, and never build a rehearsal as the shipped video.
Neither script is run here: no browser, no ffmpeg, no request.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import wave

import pytest

from src.domain.review_dialogue import CLEAN_FINDINGS_TEXT

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
# The closing card the plan had before this change: 9 rows with the system-voice line,
# and an edge mean of 7.59, which the sync gate reads as content (video/README.md).
NINE_ROW_OUTRO = [
    "Volcan: code review by ear, by touch and by voice.",
    "Live build: https://qylv1gxor9.execute-api.eu-west-1.amazonaws.com",
    "Source: https://github.com/upgradedev/volcan_amazon",
    "Recorded on the live build at commit {sha7}. Simulated Alexa+ front end, not an Alexa skill. "
    "GitHub review: a dry run, recorded and not sent.",
    "Narration: synthetic ElevenLabs voice. Product voice: the page's own speech.",
]
SYSTEM_VOICE = [{"kind": "speech", "renderedWith": "Windows System.Speech, voice Microsoft David Desktop, rate 0"}]


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, VIDEO / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


capture = load("volcan_video_capture", "capture-local.py")
build = load("volcan_video_build", "build-video.py")
narration = load("volcan_video_narration", "generate-narration.py")


def plan_beats() -> list[str]:
    return [beat["beat_id"] for beat in PLAN["beats"]]


# --- the plan ----------------------------------------------------------------

def test_the_plan_opens_on_a_short_title_card_then_the_cold_open():
    assert PLAN["cards"]["title_seconds"] == 2.0
    assert PLAN["cards"]["title_slot"].startswith("card_then_cold_open")
    lead = PLAN["cards"]["title_seconds"] + PLAN["cold_open"]["seconds"]
    assert narration.lead_seconds(PLAN) == lead
    assert PLAN["beats"][0]["timestamp_start"] == lead
    for before, after in zip(PLAN["beats"], PLAN["beats"][1:]):
        assert before["timestamp_end"] == after["timestamp_start"]
    assert PLAN["target_duration_seconds"] == round(PLAN["beats"][-1]["timestamp_end"]
                                                    + PLAN["cards"]["outro_seconds"], 3)
    assert PLAN["target_duration_seconds"] < 175


# --- the capture -------------------------------------------------------------

def test_the_capture_accepts_the_planned_beats():
    capture.check_beats(plan_beats())
    assert capture.EXPECTED_BEATS == plan_beats()


@pytest.mark.parametrize("beats", [OLD_BEATS, list(reversed(plan_beats())), plan_beats()[:-1]])
def test_the_capture_refuses_any_other_journey(beats):
    with pytest.raises(SystemExit, match="differ"):
        capture.check_beats(beats)


def test_the_capture_takes_the_card_and_cold_open_lengths_from_the_plan():
    assert capture.check_title_slot(PLAN) == (PLAN["cards"]["title_seconds"], PLAN["cold_open"]["seconds"])
    with pytest.raises(SystemExit, match="title_slot"):
        capture.check_title_slot({"cards": {"title_seconds": 3.0}})
    with pytest.raises(SystemExit, match="title_slot"):
        capture.check_title_slot({**PLAN, "cards": {**PLAN["cards"], "title_slot": "cold_open: footage"}})
    with pytest.raises(SystemExit, match="title_seconds"):
        capture.check_title_slot({**PLAN, "cards": {**PLAN["cards"], "title_seconds": 12.0}})


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
    # Seconds from the cold open's first frame, after the plan's 2.0 s title card: the
    # first sound by 2.0 s of the cold open, the first word by 5.0 s of the video.
    [(0.9, 2.4, True), (2.0, 3.0, True), (2.4, 2.0, False), (0.9, 3.4, False), (None, None, False)],
)
def test_the_cold_open_must_sound_after_the_card_and_speak_by_5_s_of_video(sound, word, passes):
    title = PLAN["cards"]["title_seconds"]
    if passes:
        capture.cold_open_gate(sound, word, title)
    else:
        with pytest.raises(SystemExit, match="Record again"):
            capture.cold_open_gate(sound, word, title)


def test_the_capture_knows_the_page_s_clean_findings_answer():
    assert CLEAN_FINDINGS_TEXT.startswith(capture.NO_FINDING_PREFIX)
    assert capture.no_finding(CLEAN_FINDINGS_TEXT)
    assert not capture.no_finding("1 finding. In config.py, a cross-origin policy was widened to accept any origin.")


def test_the_pull_request_check_uses_the_chosen_url():
    assert capture.pull_request_label("https://github.com/octocat/Hello-World/pull/1") == \
        "octocat/Hello-World pull request 1"
    with pytest.raises(SystemExit, match="VOLCAN_PR_URL"):
        capture.pull_request_label("https://example.com/o/r/pull/1")
    assert capture.cold_open_command(None)[1] == "Findings"
    assert capture.cold_open_command("files")[1] == "File by file"
    with pytest.raises(SystemExit):
        capture.cold_open_command("summary")


# --- the free rehearsal ---------------------------------------------------------

def test_a_rehearsal_is_off_by_default_and_never_bills():
    assert capture.rehearsal_requested([]) is False
    assert capture.rehearsal_requested([capture.REHEARSAL_FLAG]) is True
    with pytest.raises(SystemExit, match="cannot be used together"):
        capture.rehearsal_requested([capture.REHEARSAL_FLAG, capture.BILLED_FLAG])


@pytest.mark.parametrize("url", ["http://127.0.0.1:8801/", "http://localhost:8801", "http://[::1]:8801/"])
def test_a_rehearsal_runs_against_a_local_server(url):
    capture.check_local_url(url)


@pytest.mark.parametrize("url", [
    LIVE + "/",
    "http://localhost@evil.example:8801/",
    "http://127.0.0.1.evil.example/",
    "http://user:secret@127.0.0.1:8801/",
    "http://10.0.0.5:8801/",
    "file:///C:/page.html",
    "not a url",
])
def test_a_rehearsal_refuses_any_other_url(url):
    with pytest.raises(SystemExit, match="only against a local server"):
        capture.check_local_url(url)


def local_health(**change) -> dict[str, object]:
    return {
        "source_revision": SHA,
        "bedrock_model_path": {"resolved_capability": "no_credentials"},
        "durable_state": {"resolved_capability": "process_memory"},
        "github_review_path": {"resolved_capability": "dry_run_no_token"},
        **change,
    }


def test_a_rehearsal_lists_what_the_local_server_cannot_show():
    notes = capture.check_rehearsal_health(local_health(), SHA)
    assert {note["check"] for note in notes} == {"bedrock_model_path", "durable_state"}
    assert all(note["take"] != note["rehearsal"] for note in notes)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"bedrock_model_path": {"resolved_capability": "ready_to_attempt"}}, "could bill"),
        ({"github_review_path": {"resolved_capability": "dry_run_with_token"}}, "dry_run_no_token"),
        ({"source_revision": "0" * 40}, "different commit"),
    ],
)
def test_a_rehearsal_refuses_a_server_that_could_bill_or_post(change, message):
    with pytest.raises(SystemExit, match=message):
        capture.check_rehearsal_health(local_health(**change), SHA)


def test_the_silent_timing_stub_follows_the_plan_windows(tmp_path):
    timing = capture.silent_timing_stub(PLAN)
    assert timing["stub"] is True and "ESTIMATE" in timing["basis"]
    assert [scene["id"] for scene in timing["scenes"]] == plan_beats()
    lead = narration.lead_seconds(PLAN)
    for scene, beat in zip(timing["scenes"], PLAN["beats"]):
        assert round(lead + scene["startSeconds"], 3) == beat["timestamp_start"]
        assert scene["holdSeconds"] == round(beat["timestamp_end"] - beat["timestamp_start"], 3)
        assert scene["sentences"] and scene["sentences"][-1]["end"] == pytest.approx(scene["durationSeconds"], abs=0.002)
    assert round(lead + timing["totalSeconds"], 3) == PLAN["beats"][-1]["timestamp_end"]
    capture.write_silent_stub(timing, tmp_path)
    first = timing["scenes"][0]
    with wave.open(str(tmp_path / first["audio"])) as audio:
        assert audio.getnframes() / audio.getframerate() == pytest.approx(first["durationSeconds"], abs=0.001)
        assert set(audio.readframes(1600)) == {0}
    assert json.loads((tmp_path / "timing.json").read_text(encoding="utf-8")) == timing
    assert "That was Volcan, live" in (tmp_path / "captions.en.srt").read_text(encoding="utf-8")


# --- the composer ------------------------------------------------------------

STRINGS = {
    "captions": "captions.burn.srt", "style": "FontSize=11", "tag": "tag.txt",
    "unrecorded_label": "unrecorded.txt", "muted": "0",
    "title_card": "color=c=0x07111f:s=1920x1080:r=25:d=2.0",
    "outro_card": "color=c=0x07111f:s=1920x1080:r=25:d=4.5",
}


def test_the_plan_plays_the_cold_open_after_a_title_card():
    assert build.title_slot_shape(PLAN["cards"]) == build.TITLE_SLOT_CARD_THEN_COLD_OPEN
    assert build.title_slot_shape({"title_seconds": 3.0}) == build.TITLE_SLOT_CARD


@pytest.mark.parametrize("slot", ["cold_open: the title slot carries the cold-open footage", "something else"])
def test_the_composer_refuses_a_title_slot_the_gate_cannot_read_as_a_card(slot):
    with pytest.raises(SystemExit, match="title_slot|title segment"):
        build.title_slot_shape({"title_seconds": 12.0, "title_slot": slot})


def test_the_cold_open_footage_follows_the_title_card():
    graph = build.video_graph(
        cold_open=True, cold_seconds=12.0, total=140.0, trim_lead=60.0, cold_trim_lead=48.0,
        video_per_page=1.0, cold_band="cold-open-band.txt", **STRINGS)
    content, title, outro, concat = graph
    assert content.startswith("[0:v]trim=start=48.0:end=200.2,")
    assert "trim=end=152.0," in content
    assert "textfile='cold-open-band.txt'" in content and "enable='lt(t,12.000)'" in content
    assert "textfile='tag.txt'" in content and "enable='gte(t,12.000)'" in content
    assert "color=c=" not in content
    assert title.startswith("color=c=0x07111f") and title.endswith("[title]")
    assert outro.endswith("[outro]")
    assert concat == "[title][content][outro]concat=n=3:v=1:a=0[v]"


def test_a_take_without_a_cold_open_keeps_its_title_card():
    graph = build.video_graph(
        cold_open=False, cold_seconds=0.0, total=156.0, trim_lead=6.0, cold_trim_lead=None,
        video_per_page=1.0, cold_band=None, **STRINGS)
    content, title, _, concat = graph
    assert content.startswith("[0:v]trim=start=6.0:end=162.2,")
    assert "trim=end=156.0," in content and "cold-open-band" not in content
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
        build.check_cold_open(False, 0.0, 6.0, 1.0, receipt)
    with pytest.raises(SystemExit, match="bounded contract"):
        build.check_cold_open(False, 0.0, 45.0, 1.0, {})
    assert build.check_cold_open(False, 0.0, 6.0, 1.0, {}) is None


def test_the_seam_counts_the_page_s_own_speech_before_the_web_beat():
    scenes = [
        {"startSeconds": 0.0, "durationSeconds": 8.0, "holdSeconds": 30.0},
        {"startSeconds": 30.0, "durationSeconds": 10.0, "holdSeconds": 30.0},
        {"startSeconds": 60.0, "durationSeconds": 10.0, "holdSeconds": 12.0},
    ]
    assert build.screencast_sound_end(scenes, []) == 40.0
    speech = [{"timelineSeconds": 42.0, "seconds": 14.5}, {"timelineSeconds": -10.0, "seconds": 3.0},
              {"timelineSeconds": 61.0, "seconds": 9.0}]
    assert build.screencast_sound_end(scenes, speech) == 56.5


def test_the_band_tag_names_the_build_the_capture_recorded():
    assert build.band_tag(LIVE + "/", "9b2bcb9") == \
        "Live build at qylv1gxor9.execute-api.eu-west-1.amazonaws.com, commit 9b2bcb9."
    assert build.band_tag("http://127.0.0.1:8871/", "9b2bcb9").startswith("Local run of commit 9b2bcb9.")


def test_the_closing_card_names_a_system_voice_when_one_was_used():
    lines = build.outro_lines_for(PLAN["cards"]["outro_lines"], "9b2bcb9", SYSTEM_VOICE)
    assert not any(build.PAGE_OWN_SPEECH in line for line in lines)
    assert any("Microsoft David Desktop" in line for line in lines)
    assert any("Commit 9b2bcb9." in line for line in lines)
    untouched = build.outro_lines_for(PLAN["cards"]["outro_lines"], "9b2bcb9", [])
    assert any(build.PAGE_OWN_SPEECH in line for line in untouched)


@pytest.mark.parametrize("voice", [SYSTEM_VOICE, []])
def test_the_closing_card_stays_a_card_for_the_sync_gate(voice):
    lines = build.outro_lines_for(PLAN["cards"]["outro_lines"], "9b2bcb9", voice)
    assert build.check_outro_rows(lines) <= build.OUTRO_ROWS_MEASURED_AS_CARD == 5


def test_the_composer_refuses_the_nine_row_closing_card():
    lines = build.outro_lines_for(NINE_ROW_OUTRO, "9b2bcb9", SYSTEM_VOICE)
    # 8 rows here: the build's system-voice line is shorter than the one that made it 9.
    with pytest.raises(SystemExit, match="closing card is 8 rows"):
        build.check_outro_rows(lines)


def test_long_card_lines_wrap_inside_the_frame():
    for lines in (PLAN["cards"]["outro_lines"], PLAN["cards"]["title_lines"], NINE_ROW_OUTRO):
        rows = build.card_rows(lines)
        for row, headline in rows:
            assert len(row) <= (build.CARD_HEADLINE_CHARACTERS if headline else build.CARD_LINE_CHARACTERS)
        assert " ".join(row for row, headline in rows if headline) == lines[0]
    assert build.card_rows(["Volcan", "Narration: synthetic ElevenLabs voice."]) == [
        ("Volcan", True), ("Narration: synthetic ElevenLabs voice.", False)]


def test_a_rehearsal_is_never_built_as_the_shipped_video():
    rehearsal = {"mode": "rehearsal", "shippable": False, "narrationDir": "rehearsal/narration-stub"}
    assert build.check_rehearsal_receipt(rehearsal, True) == build.ROOT / "rehearsal" / "narration-stub"
    assert build.check_rehearsal_receipt({**rehearsal, "narrationDir": "narration"}, True) == build.ROOT / "narration"
    with pytest.raises(SystemExit, match="not shippable"):
        build.check_rehearsal_receipt(rehearsal, False)
    with pytest.raises(SystemExit, match="marked as a rehearsal"):
        build.check_rehearsal_receipt({"mode": "take", "shippable": True}, True)
    with pytest.raises(SystemExit, match="narration folder"):
        build.check_rehearsal_receipt({**rehearsal, "narrationDir": "../elsewhere"}, True)
    assert build.check_rehearsal_receipt({"mode": "take", "shippable": True}, False) == build.NARRATION
