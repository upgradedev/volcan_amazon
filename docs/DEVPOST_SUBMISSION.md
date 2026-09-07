# Volcan: Devpost submission

## Tagline

Volcan lets blind and mobility-impaired software developers review autonomous coding agents
by ear and by touch instead of by reading a diff.

**Track:** Alexa+. **Mini challenge:** AWS Builder. Both claims are qualified in
[What is live and what is simulated](#what-is-live-and-what-is-simulated), below.

---

## Inspiration

Autonomous coding agents produce a patch in seconds. A sighted reviewer scans it in seconds
too. A blind reviewer using a screen reader hears every plus sign, minus sign and hunk header
as literal characters, so a 300 line patch becomes minutes of auditory scrubbing through
syntax before any meaning arrives, and the one line that changes an authentication check
sounds exactly like everything around it.

A developer with a repetitive strain injury hits the same wall from the other side. The
review is not hard to understand. It is hard to navigate.

We named the project after Hephaestus, called Vulcan in Rome, the one disabled god of the
classical pantheon, who built machines to work alongside him at the forge.

---

## What it does

One patch goes in, and three things a person can use come out.

1. **A spoken digest**, at three levels of detail, with counts that agree with their nouns,
   because a listener hears "1 files" and a reader skims past it.
2. **An audio earcon**, a 16-bit PCM WAV synthesized in pure Python and delivered over the
   Model Context Protocol as an `audio` content block, so a client plays the sound instead of
   reading a description of it. A falling contour means something is wrong and a rising one
   means something completed, and the cue arrives before the sentence, so the verdict lands
   before the detail. A digest whose patch carries a security finding returns the falling
   two-note `SECURITY_FINDING` cue and a digest whose patch does not returns the rising
   `DIFF_READY` cue, as different audio rather than two labels on one waveform:
   `python -m pytest tests/unit/test_earcon_encodes_the_verdict.py -q -s` prints both
   payloads and fails if they are equal. Each cue also carries a `spoken_fallback` string,
   so a Deaf or hard-of-hearing developer reads what a hearing one heard.
3. **Braille cells**, the same patch rendered as Unicode Braille patterns in the U+2800
   block with tactile add and remove markers, with no sound at all, for quiet hours, open
   offices and deafblind developers.

Around those three renderings:

* **Security flags come before comprehension.** A deterministic pass catches authentication,
  cryptographic, database and process-execution changes, and names them ahead of the line
  detail rather than in line order.
* **High-consequence commands are staged behind a single-use grant.** The grant is bound by
  HMAC-SHA256 to the action id, the command's payload hash and an expiry. An agent cannot
  release its own proposal. Volcan plans the command and never executes it.
* **Adaptive switch input** maps sip, puff, single button and foot pedal pulses to navigation
  actions, and produces haptic cadences with visual captions.

---

## How we built it

Hexagonal architecture with a domain layer that imports no framework and no SDK, which a
readiness gate verifies by parsing every domain module.

* **Interfaces.** A Model Context Protocol server written by hand to revision **2025-11-25**
  over the **Streamable HTTP** transport: JSON-RPC 2.0 at `POST /mcp`, an SSE stream at
  `GET /mcp`, session termination at `DELETE /mcp`, cryptographically random session ids,
  protocol version negotiation, Origin validation, and the full set of JSON-RPC error codes.
  Eleven tools, each with a JSON Schema generated from the pydantic model that parses its
  arguments, so the published schema cannot drift from the code. A separate REST surface at
  `/api` serves the web companion and is never called MCP.
* **Domain.** A unified diff parser, a PCM WAV synthesizer, a Braille translator, an adaptive
  switch state machine, and an approval grant issuer.
* **Infrastructure.** An Amazon Bedrock adapter that labels every response
  `synthesis_mode: bedrock` or `synthesis_mode: heuristic-local`, and carries
  `synthesis_fallback_reason` when no model answered, so nobody has to guess which path ran or
  why. An allowlisted dry-run planner that imports no execution primitive at all.
* **The companion page.** One self-contained HTML file, served by FastAPI at `/` and `/demo`.
  It holds no second implementation of the product: pressing its one primary button posts the
  patch to the running server, plays the WAV the server returned, draws the waveform from
  that WAV's own samples, prints the Braille cells the server produced, and reports the round
  trip it measured with `performance.now()`. When no server answers it says so and prints the
  command that starts one.

---

## Challenges

Writing the protocol by hand meant reading the specification closely enough to notice where
it does not say what a transport should do. Three cases needed a documented decision: an
unknown session id, a request missing the protocol version header, and a top-level JSON array
now that batching has been removed. The first implementation of the `GET /mcp` stream also
hung every client that read to end of stream, because "open a stream" reads naturally as an
unbounded generator. `docs/FRICTION_LOG.md` records both, with the fix.

The harder challenge was resisting the demo. It is easy to write a page that looks alive with
no server running, and we had one: a JavaScript digest, a JavaScript Braille map and a Web
Audio oscillator standing in for the product's own synthesizer, each labelled SIMULATED. The
labels did not help. A reader cannot separate a labelled simulation from a real result in the
seconds they give a page, and we were maintaining a second implementation that no test
covered. We deleted all of it. The page now shows a real result or an honest empty state, and
`tests/e2e/test_html_structure.py` fails the build if any of that code comes back.

---

## Accomplishments we are proud of

* **A spec-compliant MCP server with no SDK.** `python scripts/mcp_conformance.py` runs a
  full client handshake against a running instance and prints a pass or fail line for each of
  18 checks. All 18 pass, including the ones that are easy to get wrong: HTTP 404 for a
  session the server never minted, HTTP 202 with no body for `notifications/initialized`,
  `-32602` rather than a transport error for an unknown tool, and a 405 whose `Allow` header
  names every method the endpoint really accepts.
* **Audio as a first-class protocol result.** The earcons are not decoration described in
  text. They travel as MCP `audio` content blocks, and the conformance script decodes one to
  confirm it is a real WAV.
* **A page that cannot lie.** Every number the companion shows was measured in the browser
  during that session, and a test fails the build on any latency literal anywhere in the
  file.
* **Governance that refuses its own author.** An agent principal presenting a valid grant for
  its own proposal is refused with `AGENT_MAY_NOT_APPROVE`, and each refusal path has its own
  test.
* **100% detection recall over n=24 hand-labelled patches**, twelve that must raise a
  security flag and twelve that must not, with 0% false positives, against a baseline of 0%
  because a screen reader reading raw patch text surfaces no security categorisation at all.
  Printed by `python scripts/benchmark_suite.py`, recomputed by
  `tests/unit/test_security_detection_corpus.py`, measured over the corpus in
  `tests/fixtures/diff_corpus.py`. It measures behaviour on those fixtures and is not a claim
  about any real repository.

---

## What we learned

Ordering matters more than we expected. A content block list is ordered, but the ordering
carries no obligation, and for a sighted user that is cosmetic. For the person this project
exists for, an earcon arriving after the sentence removes the reason the earcon exists.

The second lesson was about accessibility as a claim rather than a feature. Writing tests
that fail when a control loses its keyboard path, when a result stops being announced, or
when an animation ignores a reduced-motion preference changed how the page was built, because
those defects became build failures instead of things to remember.

---

## What is live and what is simulated

**Live, and checkable in one command.** The MCP server. Start it with
`python -m src.interfaces.mcp_server` and run
`python scripts/mcp_conformance.py http://127.0.0.1:8000/mcp` to watch 18 of 18 protocol
checks pass. The companion page performs the same `initialize` and `tools/list` handshake in
the browser and renders the negotiated protocol version, the session id from the response
header and every published tool schema.

**Simulated, and labelled on screen and in the README.** The voice experience is a web
companion, not an Alexa skill. No skill package is submitted, no certification has been
sought, and nothing has been tested on an Echo device. The companion speaks with the
browser's Web Speech API and calls the same API an Alexa+ integration would call. It performs
a real `GET /health` on load and reports what actually answered.

**Real code that has not run here.** Amazon Bedrock. The adapter calls Claude on Amazon
Bedrock through the Anthropic SDK's `AnthropicBedrockMantle` client, pinned to
`anthropic.claude-opus-5`. No model has answered in this environment, so every digest in this
repository came from the local heuristic path, labelled `synthesis_mode: heuristic-local` in
the response and on the page **together with `synthesis_fallback_reason`, which names the
exception, the model id and the message**. The pinned model id has not been confirmed to
answer, because nobody working on this repository has AWS access that could confirm it.

**Never executed.** No file under `src/` imports or calls `subprocess`, `os.system`, `eval`,
`exec` or any process spawn. `tests/unit/test_no_execution_in_source_tree.py` walks every
source module's AST on each run to keep it that way. Volcan plans commands and refuses the
rest.

**Not recorded.** No demonstration video exists yet. `video/SHOT_LIST.md` is a beat sheet in
which every beat is an action this repository can perform today, and readiness gates E2 and
E4 report red until footage exists.

**Stale.** A deployed AWS endpoint answers `GET /health`, but it runs an ancestor commit and
returns 404 for `/mcp`. `deploy_teardown_receipt.json` records that probe, and gates D2 and
G2 are red for it. Run the server locally to exercise the MCP surface.

---

## Track and mini challenge

* **Track: Alexa+.** Claimed as a real MCP server that an Alexa+ integration would call, plus
  an explicitly simulated voice web experience. The claim is the protocol work, not a
  certified skill.
* **Mini challenge: AWS Builder.** Claimed as a real Amazon Bedrock adapter whose responses
  state which path produced them. The claim is the labelled integration, not a Bedrock
  benchmark, because no model has been invoked from this environment.

---

## What is next

1. **Submit an Alexa skill for certification** so the voice experience stops being a
   simulation. The MCP tools already return everything a skill handler needs, and the gap is
   certification and an Echo device, not code.
2. **Run the Bedrock path with real credentials** and publish the same benchmark table for
   `synthesis_mode: bedrock` beside the heuristic figures, so the two paths can be compared
   rather than assumed equivalent.
3. **Have a Braille transcriber review the output.** Today it is computer Braille, mapped one
   character to one cell. Contracted Grade 2 is what an experienced reader actually wants.
4. **Test with the people this is for.** Nothing here has been through a session with a blind
   or motor-impaired developer, and every design decision about cue ordering and digest length
   is currently a hypothesis.
5. **Persist sessions and the audit chain.** Both live in memory, so a restart loses the
   tamper-evident history that makes the governance claim worth anything.
6. **Drive the companion with a real browser in CI.** `tests/e2e` parses the DOM; gate C5 is
   red because no browser driver runs, and a screen-reader journey belongs in that gap.

---

## Feedback for the Amazon teams

`docs/FRICTION_LOG.md` holds the detail. In short: publish MCP conformance vectors so two
implementers agree on status codes; state that a server may close the `GET` stream
immediately; add an ordering hint to content blocks so an accessibility cue can be declared
to precede its text; ship a local Bedrock emulator so an integration can be tested rather
than asserted; and let a deployed function expose the source revision it was built from.
