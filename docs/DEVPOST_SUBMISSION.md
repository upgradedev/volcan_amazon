# Volcan: Devpost submission text

## Tagline

Volcan lets blind and mobility-impaired software developers review autonomous coding
agents by ear and by touch instead of by reading a diff.

---

## Inspiration

Autonomous coding agents produce a patch in seconds. A sighted reviewer scans it in
seconds too. A blind reviewer using a screen reader hears every plus sign, minus sign and
hunk header as literal characters, so a 300 line patch becomes minutes of auditory
scrubbing through syntax before any meaning arrives, and the one line that changes an
authentication check sounds exactly like everything around it.

A developer with a repetitive strain injury hits the same wall from the other side. The
review is not hard to understand. It is hard to navigate.

We named the project after Hephaestus, called Vulcan in Rome, the one disabled god of the
classical pantheon, who built machines to work alongside him at the forge.

---

## What it does

1. **Turns a patch into a spoken digest** at three levels of detail, with counts that agree
   with their nouns, because a listener hears "1 files" and a reader skims past it.
2. **Flags security-sensitive changes first.** A deterministic pass catches authentication,
   cryptographic, database and process-execution changes, and names them before the line
   detail rather than in line order.
3. **Returns audio cues as first-class results.** A pure-Python PCM WAV synthesizer
   produces distinct earcons, delivered over the Model Context Protocol as `audio` content
   blocks, so a client plays the sound instead of reading a description of it. Falling
   contour means something is wrong; rising means something completed.
4. **Renders the same patch as Unicode Braille** in the U+2800 block, with no sound at all,
   for quiet hours, open offices and deafblind developers.
5. **Stages high-consequence commands behind a single-use grant.** The grant is bound by
   HMAC-SHA256 to the action id, the command's payload hash and an expiry. An agent cannot
   release its own proposal. Volcan plans the command and never executes it.
6. **Accepts adaptive switch input**, mapping sip, puff, single button and foot pedal
   pulses to navigation actions, and produces haptic cadences with visual captions for Deaf
   and hard-of-hearing developers.

---

## How we built it

Hexagonal architecture with a domain layer that imports no framework and no SDK, which a
readiness gate verifies by parsing every domain module.

* **Interfaces.** A Model Context Protocol server written by hand to revision **2025-11-25**
  over the **Streamable HTTP** transport: JSON-RPC 2.0 at `POST /mcp`, an SSE stream at
  `GET /mcp`, session termination at `DELETE /mcp`, cryptographically random session ids,
  protocol version negotiation, Origin validation, and the full set of JSON-RPC error
  codes. Eleven tools, each with a JSON Schema generated from the pydantic model that
  parses its arguments, so the published schema cannot drift from the code. A separate
  REST surface at `/api` serves the web companion and is not called MCP.
* **Domain.** A unified diff parser, a PCM WAV synthesizer, a Braille translator, an
  adaptive switch state machine, and an approval grant issuer.
* **Infrastructure.** An Amazon Bedrock adapter that is real boto3 code and that labels
  every response `synthesis_mode: bedrock` or `synthesis_mode: heuristic-local` so nobody
  has to guess which path ran. An allowlisted dry-run planner that imports no execution
  primitive at all.

---

## Challenges

Writing the protocol by hand meant reading the specification closely enough to notice
where it does not say what a transport should do. Three cases needed a documented decision:
an unknown session id, a request missing the protocol version header, and a top-level JSON
array now that batching has been removed. The first implementation of the `GET /mcp` stream
also hung every client that read to end of stream, because "open a stream" reads naturally
as an unbounded generator. `docs/FRICTION_LOG.md` records both, with the fix.

---

## What we learned

Ordering matters more than we expected. A content block list is ordered but the ordering
carries no obligation, and for a sighted user that is cosmetic. For the person this project
exists for, an earcon arriving after the sentence removes the reason the earcon exists.

---

## Headline result

**100% detection recall over n=24 hand-labelled patches**, twelve that must raise a
security flag and twelve that must not, with 0% false positives, against a baseline of 0%
because a screen reader reading raw patch text surfaces no security categorisation at all.
Printed by `python scripts/benchmark_suite.py`, recomputed by
`tests/unit/test_security_detection_corpus.py`, and measured over the corpus in
`tests/fixtures/diff_corpus.py`. It measures behaviour on those fixtures and is not a claim
about any real repository.

---

## What is real and what is simulated

**Real:** the MCP server. Run `python scripts/mcp_conformance.py` against a running
instance and watch 18 of 18 protocol checks pass.

**Simulated, and labelled on screen:** the voice experience is a web companion, not an
Alexa skill. No skill package is submitted, no certification has been sought, and nothing
has been tested on an Echo device. The companion performs a real `GET /health` on load and
shows LIVE or SIMULATED according to what actually answered.

**Not run here:** Amazon Bedrock. There are no AWS credentials in this environment, so
every digest in the repository came from the local path and says so.

---

## Track and mini challenge

* **Track:** Alexa+, claimed as a real MCP server plus an explicitly simulated voice web
  experience.
* **Mini challenge:** AWS Builder, claimed as a real Amazon Bedrock adapter whose responses
  state which path produced them.

---

## Feedback for the Amazon teams

`docs/FRICTION_LOG.md` holds the detail. In short: publish MCP conformance vectors so two
implementers agree on status codes; state that a server may close the `GET` stream
immediately; add an ordering hint to content blocks so an accessibility cue can be declared
to precede its text; ship a local Bedrock emulator so an integration can be tested rather
than asserted; and let a deployed function expose the source revision it was built from.
