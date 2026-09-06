# Volcan: accessibility matrix and presentation guide

> **Reading rule for this document.** The matrix separates what Volcan implements from the
> hardware that implementation is designed for. No device in the right-hand column was
> connected while this was built. Where a row says "not exercised", that is a statement of
> fact, not a hedge.

---

## 1. The problem this addresses

An autonomous coding agent streams thousands of tokens, produces side-by-side visual
diffs, and expects a click to confirm. Each of those assumptions excludes somebody:

* A **blind developer** hears every plus sign, minus sign and hunk header as literal
  characters before any meaning arrives.
* A **deafblind developer** is excluded from a voice-only interface entirely.
* A **quadriplegic or severely RSI-limited developer** is blocked by the click, not by the
  content.
* A **Deaf or hard-of-hearing developer** cannot hear an audio alert at all.
* Anyone working in **shared or quiet space** cannot use an audio-only workflow.

---

## 2. Accessibility matrix

| Need | Input Volcan accepts | Output Volcan produces | Implemented in | Target hardware, and whether it was exercised |
|---|---|---|---|---|
| Blind developers | Typed or spoken command through the companion, or an MCP `tools/call` | Spoken digest plus a 22.05 kHz PCM earcon returned as an MCP `audio` block | `DigestDiffUseCase`, `SonifyEventUseCase`, `src/domain/sonification.py` | Echo or any MCP client. **Not exercised on an Echo device.** |
| Quiet hours and shared offices | Same as above | Silent Unicode Braille in the U+2800 block | `src/domain/braille_translator.py`, `BrailleDiffUseCase` | Refreshable Braille display. **Not exercised on a physical display.** |
| Deafblind developers | Braille keyboard through the companion's text fields | Tactile Braille stream from `/api/braille/diff_digest` | Same as above | Multi-line Braille terminal. **Not exercised.** |
| Hands-free operation, quadriplegia, ALS, severe RSI | Switch pulses submitted to `process_switch_pulse`: sip, puff, single button, foot pedal | The resolved navigation action, with a spoken description | `src/domain/adaptive_switch.py` | Sip-and-puff straw, foot pedal. **Not exercised with a physical switch; the pulse contract is tested.** |
| Deaf and hard-of-hearing developers | Keyboard or switch | Haptic vibration cadence plus a visual caption for every audio cue | `src/domain/haptic_feedback.py` | Wearable or phone haptics. **Not exercised on a device.** |
| Keyboard-only operation | Tab, Enter, Space, Alt+1, Alt+2, Alt+3, Escape | Every control reachable, a visible focus ring, results announced through `aria-live` | `docs/index.html`, asserted by `tests/e2e/test_html_structure.py` | A browser. **Not exercised by an automated browser driver.** `tests/e2e/test_html_structure.py` asserts the tab order, the focus ring, the landmarks and the live regions by parsing the document; no driver walks the page, and gate C5 records that as a failure. |

---

## 3. The developer journey

1. **Ask.** The developer asks for a digest of the working patch, by typing or speaking in
   the companion, or by an MCP client calling `digest_semantic_diff`.
2. **Hear the shape before the words.** A rising three-note cue means the digest is ready;
   a falling two-note cue means a security finding is coming. The cue arrives first.
3. **Read by ear or by touch.** Level 0 is one sentence. Level 1 breaks down by file.
   Level 2 drills into lines. The same content renders as a Braille cell stream for a
   refreshable display, with no sound at all.
4. **Stage, do not execute.** A high-consequence command is staged behind a single-use
   authorization grant with a lease. Volcan plans the command and shows exactly what it
   would run.
5. **Release deliberately.** A human presents the grant. An agent presenting the same grant
   is refused. The audit trail records who staged and who approved.

---

## 4. Presentation beats

Each beat below is a claim the repository can back. The command that backs it is named.

**Beat 1, the problem (0:00 to 0:30).** An autonomous agent produces a patch in seconds and
a screen reader takes minutes to get through the syntax. Show a raw patch being read aloud
character by character.

**Beat 2, what Volcan is (0:30 to 1:00).** A Model Context Protocol server, revision
2025-11-25 over Streamable HTTP, plus a companion that simulates the voice experience. Run
`python scripts/mcp_conformance.py` on camera and let the 18 pass lines print.

**Beat 3, sonification and Braille (1:00 to 1:40).** Call `digest_semantic_diff` on a patch
that changes an authentication function. The alert cue plays before the sentence. Show the
same patch rendered as a Braille cell stream.

**Beat 4, hands-free and Deaf or HOH controls (1:40 to 2:15).** Call `process_switch_pulse`
with a puff and show it resolve to approve. Call `get_haptic_profile` for a security flag
and show the cadence and its visual caption.

**Beat 5, governance (2:15 to 2:45).** Stage a command, show the grant, present it as the
agent and watch it be refused, then present it as the human and watch Volcan report the
plan it would run and that nothing was executed.

**Beat 6, verification (2:45 to 3:00).** Run `python -m pytest tests/ -q` and
`python ci/readiness.py` on camera, including the gates that are red and why.

---

## 5. Reproducing the evidence

```bash
python -m pytest tests/ -q
python scripts/benchmark_suite.py
python scripts/braille_terminal_simulator.py
python ci/readiness.py
```

The readiness auditor reports gates that fail, with the reason for each. That output is
part of the evidence, not something to hide.
