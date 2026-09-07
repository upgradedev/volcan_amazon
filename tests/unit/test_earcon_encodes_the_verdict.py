"""The earcon has to carry the verdict, or it is decoration.

Four judge-facing documents promise that a falling two-note cue means a
security finding is coming and a rising cue means the digest is merely ready.
Before this suite existed, every digest returned ``DIFF_READY``: the WAV bytes
for a benign patch and for a security-sensitive one were byte-identical, so the
promise was false on the one surface a blind reviewer depends on first.

These tests hold both halves of the claim. The positive half proves the two
payloads differ. The negative half proves a benign patch still gets the rising
cue, because a cue that fires on everything carries no more information than a
cue that fires on nothing.
"""
import asyncio
import base64
import hashlib

from src.application.sonify_event_use_case import SonifyEventUseCase
from src.domain.semantic_diff import UnifiedDiffParser
from src.domain.sonification import (
    EarconType,
    earcon_for_report,
    earcon_for_section,
)
from src.interfaces.dto import DigestRequest, DrillDownRequest
from src.interfaces.operations import op_digest, op_drill_down

BENIGN_PATCH = (
    "diff --git a/src/utils/parser.py b/src/utils/parser.py\n"
    "--- a/src/utils/parser.py\n"
    "+++ b/src/utils/parser.py\n"
    "@@ -4,3 +4,4 @@\n"
    "-    return data.strip()\n"
    "+    if not data:\n"
    '+        return ""\n'
    "+    return data.strip()\n"
)

SECURITY_PATCH = (
    "diff --git a/src/auth/service.py b/src/auth/service.py\n"
    "--- a/src/auth/service.py\n"
    "+++ b/src/auth/service.py\n"
    "@@ -10,4 +10,6 @@\n"
    '-        return token == "hardcoded_secret"\n'
    '+        kms_key = os.environ.get("KMS_KEY_ID")\n'
    "+        return verify_kms_token(token, kms_key)\n"
)


def _digest(patch: str) -> dict:
    return asyncio.run(op_digest(DigestRequest(raw_diff=patch, level=0)))


def _fingerprint(label: str, result: dict) -> str:
    """The measurement the panel used, printed by the test that asserts on it.

    Run with ``-s`` to read it. Documents quoting these bytes cite this command.
    """
    return (
        f"{label:<9}| earcon {result['earcon']['type']:<17}"
        f"| sha256[:16] {hashlib.sha256(result['_wav']).hexdigest()[:16]} "
        f"| {len(result['_wav'])} WAV bytes "
        f"| {len(result['earcon']['wav_base64'])} base64 chars"
    )


def test_a_security_patch_and_a_benign_patch_do_not_return_the_same_audio():
    benign = _digest(BENIGN_PATCH)
    security = _digest(SECURITY_PATCH)

    print()
    print(_fingerprint("benign", benign))
    print(_fingerprint("security", security))

    assert benign["earcon"]["type"] == EarconType.DIFF_READY.value
    assert security["earcon"]["type"] == EarconType.SECURITY_FINDING.value

    # The bytes, not just the label. A label that changes over identical audio
    # would still leave a listener with no way to tell the two apart.
    assert benign["_wav"] != security["_wav"], (
        "the two digests returned byte-identical audio; the earcon carries no verdict"
    )
    assert benign["earcon"]["wav_base64"] != security["earcon"]["wav_base64"]
    assert hashlib.sha256(benign["_wav"]).hexdigest() != hashlib.sha256(security["_wav"]).hexdigest()
    assert len(benign["_wav"]) != len(security["_wav"])


def test_a_benign_patch_still_gets_the_rising_ready_cue():
    """The control refuses to alarm.

    Making every digest fall would 'differ' just as well and would be worse
    than the bug it replaced, because the reviewer would learn to ignore it.
    """
    benign = _digest(BENIGN_PATCH)
    assert benign["critical_findings"] == []
    assert "SECURITY_SENSITIVE" not in benign["category_breakdown"]
    assert benign["earcon"]["type"] == EarconType.DIFF_READY.value
    assert benign["earcon"]["spoken_fallback"] == "Semantic diff digest is ready."


def test_the_security_cue_falls_in_exactly_two_notes():
    """The shape is the published contract, not a taste decision.

    docs/ACCESSIBILITY_AND_PRESENTATION_MATRIX.md and docs/FRICTION_LOG.md both
    promise a falling two-note cue, so a third note or a rising interval would
    make those documents false again.
    """
    cue, _ = SonifyEventUseCase().execute(EarconType.SECURITY_FINDING)
    assert len(cue.tones) == 2, "the documents promise two notes"
    assert cue.tones[1].frequency_hz < cue.tones[0].frequency_hz, "the contour must fall"

    ready, _ = SonifyEventUseCase().execute(EarconType.DIFF_READY)
    assert ready.tones[-1].frequency_hz > ready.tones[0].frequency_hz, "the ready cue rises"


def test_the_security_cue_is_not_the_test_failure_cue():
    """Two different facts must not sound the same.

    Reusing the TEST_FAILED contour would restore the original defect one level
    up: a listener would hear 'a test failed' when the patch touched security.
    """
    sonify = SonifyEventUseCase()
    security_cue, security_wav = sonify.execute(EarconType.SECURITY_FINDING)
    failed_cue, failed_wav = sonify.execute(EarconType.TEST_FAILED)

    assert security_wav != failed_wav
    assert security_cue.spoken_fallback != failed_cue.spoken_fallback
    assert {t.frequency_hz for t in security_cue.tones} & {t.frequency_hz for t in failed_cue.tones} == set()


def test_the_drill_down_keeps_the_verdict_when_the_reviewer_descends():
    flagged = asyncio.run(op_drill_down(DrillDownRequest(raw_diff=SECURITY_PATCH, section_index=0)))
    clean = asyncio.run(op_drill_down(DrillDownRequest(raw_diff=BENIGN_PATCH, section_index=0)))

    assert flagged["earcon"]["type"] == EarconType.SECURITY_FINDING.value
    assert clean["earcon"]["type"] == EarconType.DRILL_DOWN_OPENED.value
    assert flagged["_wav"] != clean["_wav"]


def test_the_selector_reads_the_category_breakdown_when_no_finding_was_worded():
    """A category alone is enough.

    ``critical_findings`` is prose built for the ear and can be empty while the
    parser has still categorised a section as SECURITY_SENSITIVE. Either signal
    must reach the cue.
    """
    class _Report:
        critical_findings: list = []
        category_breakdown = {"SECURITY_SENSITIVE": 1}

    class _Quiet:
        critical_findings: list = []
        category_breakdown = {"BUSINESS_LOGIC": 2}

    assert earcon_for_report(_Report()) is EarconType.SECURITY_FINDING
    assert earcon_for_report(_Quiet()) is EarconType.DIFF_READY


def test_a_raw_keyword_flag_is_enough_for_a_section_to_sound_the_alarm():
    sections = UnifiedDiffParser.parse_patch(SECURITY_PATCH)
    assert sections[0].security_flags or sections[0].security_findings
    assert earcon_for_section(sections[0]) is EarconType.SECURITY_FINDING

    quiet = UnifiedDiffParser.parse_patch(BENIGN_PATCH)
    assert not quiet[0].security_flags and not quiet[0].security_findings
    assert earcon_for_section(quiet[0]) is EarconType.DRILL_DOWN_OPENED


def test_the_earcon_is_playable_audio_on_both_branches():
    """Differing bytes are not enough; both branches must still be a WAV."""
    for patch in (BENIGN_PATCH, SECURITY_PATCH):
        result = _digest(patch)
        wav = base64.b64decode(result["earcon"]["wav_base64"])
        assert wav == result["_wav"]
        assert wav.startswith(b"RIFF") and b"WAVE" in wav[:12]
        assert len(wav) > 44
