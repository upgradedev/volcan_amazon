# Volcan: video production plan

**Status: no video has been recorded.** `video/` holds the narration script, the cue sheet,
the subtitle files and the shot list. It holds no rendered footage, and readiness gates E2
and E4 report red for exactly that reason.

---

## 1. Submission constraints

* Under 180 seconds. The script in `narration.json` runs 165 seconds.
* English, on a public link.
* The recording must show software actually running. Every beat is something this repository
  does today, so the recording is a matter of capture, not of building anything further.

## 2. The files and how they relate

| File | Written by | Holds |
|---|---|---|
| `narration.json` | by hand | The five beats, their timings, the words and the intended visual action |
| `SHOT_LIST.md` | by hand | The capture plan: the exact click, the exact command and the result that must appear |
| `cue_sheet.json` | `python scripts/synthesize_video_assets.py` | The same beats with word counts and speaking rates computed from the text |
| `subtitles.vtt`, `subtitles.srt` | the same script | Timed captions generated from the same beats |
| `../video_sync_receipt.json` | the same script | The sync verdict, which reports false while no rendered video exists |

Edit `narration.json` only, then rerun the script. Hand-editing the cue sheet would turn its
measured word counts into numbers somebody typed. Readiness gate E2 compares the beat ids in
the two files and then fails because there is no picture to compare the narration against.

## 3. The five beats

| Beat | Shown running | Surface |
|---|---|---|
| `beat_01_hook` | A screen reader working through a raw patch character by character | Companion page and the operating system screen reader |
| `beat_02_one_button` | **Hear this code review** pressed by keyboard: the earcon plays, the digest and the security finding fill in, the Braille cells render, the meters report the engine and the measured round trip | Companion page |
| `beat_03_mcp_handshake` | **Run a real MCP handshake** rendering the negotiated version, the session id and the eleven tool schemas, then `python scripts/mcp_conformance.py` in a terminal | Companion page, then terminal |
| `beat_04_governance` | Stage, then approve, ending on the line that says nothing was executed and on the audit row that says the same | Companion page, then terminal |
| `beat_05_verification` | `python -m pytest tests/ -q` and `python ci/readiness.py` including the gates that are red | Terminal, then back to the page |

`SHOT_LIST.md` carries the per-beat detail, the values that must appear on screen, and the
list of things that must not be filmed because they do not exist here.

## 4. Narration audio

No narration audio has been generated and no text-to-speech service has been called from this
repository. `narration.json` records that in its `narration_audio` block rather than naming a
voice that has never spoken.
