# Volcan: video production plan

**Status: no video has been recorded.** `video/` holds the narration script, the cue
sheet and the subtitle files. It holds no rendered footage, and readiness gates E2 and E4
report red for exactly that reason.

---

## 1. Submission constraints

* Under 180 seconds. The scripted narration in `narration.json` targets 165 seconds.
* English, on a public link.
* The demonstration must show software actually running. Every beat in the script is
  something this repository can do today, so the recording is a matter of capture, not of
  building anything further.

## 2. Beat structure

`narration.json` partitions the script into five beats, each with a `beat_id`, a start and
end timestamp, the narration text and the intended visual action. `cue_sheet.json` mirrors
the same `beat_id` list with per-beat word counts and speaking rates, so a single beat can
be re-recorded without re-cutting the rest.

Readiness gate E2 checks that the two files agree beat for beat, and then fails because no
rendered video exists to compare the narration against.

## 3. What each beat should capture

| Beat | Show this running |
|---|---|
| 1, the problem | A screen reader working through a raw patch character by character |
| 2, what Volcan is | `python scripts/mcp_conformance.py` printing its 18 pass lines |
| 3, sonification and Braille | A digest of a patch that changes an authentication function, with the alert cue arriving before the sentence, then the same patch as a Braille cell stream |
| 4, hands-free controls | `process_switch_pulse` resolving a puff to approve, and a haptic cadence with its caption |
| 5, governance | The agent refused, the human release, and the planner reporting that nothing was executed |
| 6, verification | `python -m pytest tests/ -q` and `python ci/readiness.py`, including the gates that are red |

## 4. Narration audio

The script names a voice id for a text-to-speech service in `narration.json`. No audio has
been generated, and no such service has been called from this repository.
