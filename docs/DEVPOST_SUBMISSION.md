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

**Read this paragraph first if the question in your head is "is this an MCP wrapper around an
existing API".** What Volcan's MCP surface returns is not available from any API it sits in
front of. It returns `audio` content blocks carrying an earcon whose contour encodes the
verdict, so a listener knows a patch touches security before the sentence arrives. It returns
Braille cells with their fidelity and their loss declared, so a finger knows whether `(`, `)`
and `=` are three cells or one. It returns a review dialogue whose every turn reads back what
it understood before it acts, and it returns a governed action: a `REQUEST_CHANGES` review
bound by a single-use HMAC grant to the head commit that was actually reviewed, re-checked
live, and dry-run by default so the exact request is recorded and not sent until the owner
enables the write. GitHub returns none of those. Bedrock returns none of those. That is the
product; the protocol is how it reaches a client.

One pull request goes in, three things a person can use come out, and one governed action
goes back.

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
   offices and deafblind developers. The default is eight-dot code fidelity, one cell per
   printable character and lossless by round trip; six-dot literary Braille is offered for
   prose, and when it is used for code the response names the characters that collided.
4. **A spoken review that ends in a governed action.** A blind developer opens a real pull
   request by URL (a live, unauthenticated GitHub read), asks what changed in a file, hears the
   exact numbered source lines, spells one out symbol by symbol so `!=` cannot pass for `==`,
   says "no, I said previous" and is understood, then says "request changes" and "confirm".
   The review is bound to the head commit, re-checked live, and **dry-run by default**: the
   server records the exact request it would send and sends nothing unless it runs with
   `VOLCAN_GITHUB_WRITE=1` and a `GITHUB_TOKEN`. No live review has been sent from this
   repository; the README carries the owner command that produces that receipt.

Around those renderings:

* **Security flags come before comprehension, and they say what changed.** Two deterministic
  passes run. A keyword pass catches authentication, cryptographic, database and
  process-execution vocabulary. A syntax-tree pass then compares the added and removed lines
  as parsed Python and reports what the change *did*: an authorization comparison inverted, a
  cross-origin policy widened to any origin, a verification call deleted and not replaced.
  The second pass exists because `user.role == "admin"` and `user.role != "admin"` contain
  identical words, so no keyword matcher can tell them apart, and the finding is spoken ahead
  of the line detail rather than in line order.
* **The demo's own buttons reach those rules.** The companion page ships four preset patches:
  one per syntax-tree rule, plus a labelled clean control where the right answer is no finding
  and the rising cue. Each chip's label quotes the sentence the server will say back, and
  `tests/e2e/test_shipped_presets_reach_their_rule.py` runs every shipped preset through the
  production parser and fails the build if a label and its rule separate, or if a rule ships
  with no preset to demonstrate it. Until 2026-09-08 the presets triggered no syntax-tree rule
  at all, so the first press showed the weakest output the product can give.
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
  Twelve tools, each with a JSON Schema generated from the pydantic model that parses its
  arguments, so the published schema cannot drift from the code. A separate REST surface at
  `/api` serves the web companion and is never called MCP.
* **Domain.** A unified diff parser that numbers every line of every hunk, a PCM WAV
  synthesizer, a Braille translator with two fidelities, an adaptive switch state machine, an
  approval grant issuer, and the review dialogue: a state machine over transcripts that reads
  back before it acts and undoes a misheard command when corrected, with no speech engine, no
  HTTP and no GitHub in it, so it is driven in tests by injected text.
* **Infrastructure.** An Amazon Bedrock adapter that labels every response
  `synthesis_mode: bedrock` or `synthesis_mode: heuristic-local`, and carries
  `synthesis_fallback_reason` when no model answered, so nobody has to guess which path ran or
  why. An allowlisted dry-run planner that imports no execution primitive at all. A GitHub
  adapter over `httpx` whose read is live and whose write is dry-run by default, tested against
  a mock transport for the accepted review, the moved head, the missing token and the
  unauthorized token.
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

* **A hand-written MCP server with no SDK.** `python scripts/mcp_conformance.py` runs a
  full client handshake against a running instance and prints a pass or fail line for each of
  21 checks. All 21 passed on 2026-09-08, including the ones that are easy to get wrong: HTTP
  404 for a session the server never minted, HTTP 202 with no body for
  `notifications/initialized`, `-32602` rather than a transport error for an unknown tool, a
  405 whose `Allow` header names every method the endpoint really accepts, and `-32600` for a
  missing version header on every method, session or no session.
* **A review journey that reads back before it acts, and refuses when it should.** The
  dialogue is driven by injected transcripts in `tests/unit/test_review_dialogue.py`, the
  grant and the GitHub port in `tests/unit/test_review_dialogue_use_case.py`, and the whole
  journey over REST and MCP in `tests/integration/test_review_dialogue_api.py`. A head that
  moved after the review was prepared is refused as `STALE_HEAD` before anything is recorded;
  a confirm without the grant, a tampered grant, a grant for a different review, an elapsed
  lease, a self-approval and a token without permission each have a test that asserts the
  refusal and the audit line it leaves.
* **Audio as a first-class protocol result.** The earcons are not decoration described in
  text. They travel as MCP `audio` content blocks, and the conformance script decodes one to
  confirm it is a real WAV.
* **A page that cannot lie.** Every number the companion shows was measured in the browser
  during that session, and a test fails the build on any latency literal anywhere in the
  file.
* **Governance that refuses its own author.** An agent principal presenting a valid grant for
  its own proposal is refused with `AGENT_MAY_NOT_APPROVE`, and each refusal path has its own
  test.
* **81.8% detection recall over n=40 hand-labelled patches**, twenty-two that must raise a
  security flag and eighteen that must not, with 0% false positives, against a baseline of 0%
  because a screen reader reading raw patch text surfaces no security categorisation at all.
  Printed by `python scripts/benchmark_suite.py`, recomputed by
  `tests/unit/test_security_detection_corpus.py`, measured over the corpus in
  `tests/fixtures/diff_corpus.py`. It measures behaviour on those fixtures and is not a claim
  about any real repository.

  The figure was 100% over n=24 while the corpus contained only patches the rules already
  handled. Four positives were then added *because* nothing here detects them, and the
  README names all four: a deleted authorization guard block, a removed permission
  decorator, `verify=False` added to an outbound call, and an IAM policy widened in JSON.
  Recall fell to 81.8% and became worth reading. The four are pinned by fixture id, so a new
  miss fails the build and closing one means deleting its id from the list.

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
`python scripts/mcp_conformance.py http://127.0.0.1:8000/mcp` to watch 21 of 21 protocol
checks pass. The companion page performs the same `initialize` and `tools/list` handshake in
the browser and renders the negotiated protocol version, the session id from the response
header and every published tool schema.

**Simulated, and labelled on screen and in the README.** The voice experience is a web
companion, not an Alexa skill. No skill package is submitted, no certification has been
sought, and nothing has been tested on an Echo device. The companion listens with the
browser's `SpeechRecognition` where the browser has one, speaks with `speechSynthesis`, keeps
a typed twin for every command, and calls the same server an Alexa+ integration would call.
The label sits in the page header above the fold and a test holds it there. It performs a
real `GET /health` on load and reports what actually answered.

**Live read, dry-run write.** Opening a pull request is a live unauthenticated GitHub read;
on 2026-09-08 the page opened `python/cpython#1` and printed its head commit `02a87ce`.
Submitting the review is dry-run by default: on `confirm` the page printed `Dry run. Nothing
was sent to GitHub.` beside the exact `POST .../reviews` body it recorded. No live review has
been sent from this repository. The owner command that produces one is in the README.

**Real code that has not run here.** Amazon Bedrock. The adapter calls Claude on Amazon
Bedrock through the Anthropic SDK's `AnthropicBedrockMantle` client, pinned to
`anthropic.claude-opus-5`. The path is implemented and shape-tested against a stub, and it
has never executed: no model has answered in this environment, so every digest in this
repository came from the local heuristic path, labelled `synthesis_mode: heuristic-local` in
the response and on the page **together with `synthesis_fallback_reason`, which names the
exception, the model id and the message**. The pinned model id has not been confirmed to
answer, because nobody working on this repository has AWS access that could confirm it, and
installing the SDK on a machine whose credentials resolve would fire a real billed call
against an account without its owner's say-so.

`/health` used to publish `bedrock_credentials_present: true` here, which was true and
misleading: credentials resolve on this machine while the SDK is absent, so no call could be
attempted at all. It now publishes one resolved capability computed from both facts, reading
`unavailable_sdk_not_installed` on 2026-09-08, with the credential and SDK booleans underneath
it as the evidence. The README carries the exact command an owner can run to produce a Bedrock
receipt themselves.

**Never executed.** No file under `src/` imports or calls `subprocess`, `os.system`, `eval`,
`exec` or any process spawn. `tests/unit/test_no_execution_in_source_tree.py` walks every
source module's AST on each run to keep it that way. Volcan plans commands and refuses the
rest.

**Not recorded.** No demonstration video exists yet. `video/SHOT_LIST.md` is a beat sheet in
which every beat is an action this repository can perform today, and readiness gates E2 and
E4 report red until footage exists.

**Deployed.** On 2026-09-23 the public endpoint served `GET /health`, the current companion,
the REST digest and MCP initialize/tool calls. Health exposes the immutable source revision.
A governed action remained a dry-run and its bounded EMF records were read back from
CloudWatch. Alexa skill certification, Echo testing and a live GitHub write remain absent.

---

## Who would buy this, and out of which budget

**A commercial hypothesis, not a finding.** No market size, no price, no revenue projection
and no conversion rate appears here, because none has been measured.

**The user is not the buyer.** The user is the blind or mobility-impaired engineer who reviews
agent-written patches by ear. The budget holder is the **enterprise accessibility compliance
owner**: the accessibility programme manager or director of accessibility engineering who
already signs off remediation work, answers procurement questionnaires and owns the line that
pays for what disabled employees need in order to work.

**The budget line already exists.** Accessibility remediation and conformance spend, the money
set aside against ADA / WCAG 2.1 AA, Section 508 and EN 301 549, together with the assistive
technology and workplace adjustment provision beside it. **Where that is weakest:** remediation
budgets pay to fix the accessibility of the product being shipped, and Volcan makes the work of
building it accessible instead. It produces no Accessibility Conformance Report and closes no
audit finding, so the sale needs the buyer to treat employing blind engineers as part of the
same programme as conforming. The fallback is the workplace adjustment line, which is smaller.

**The willingness-to-pay basis** is what these organisations already pay for the closest
comparables, each of which the vendor publishes publicly: Freedom Scientific's pricing for the
JAWS screen reader, refreshable Braille display pricing from HumanWare and Freedom Scientific,
and Deque's pricing for axe DevTools. No figure from any of those pages is restated here and
none has been used to derive anything.

**The first ten to approach have not been contacted.** Deque Systems, Level Access, TPGi,
Microsoft accessibility engineering, Google central accessibility, GitHub accessibility, the
UK Government Digital Service, European Commission DIGIT, the Royal National Institute of Blind
People and the American Foundation for the Blind. Nothing there is a pipeline or a warm
introduction; it is a target list written from the outside. The full section, including what
does and does not compound, is in the README.

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
   simulation. The `review_dialogue_turn` tool already takes a transcript and returns the
   readback, the answer and the cue a skill handler needs, and the gap is certification and an
   Echo device, not code.
2. **Send one live review** with `VOLCAN_GITHUB_WRITE=1` and a fine-grained token against a
   repository the owner controls, and record the receipt. The code path exists and is tested
   against a mock; the receipt does not.
3. **Run the Bedrock path with real credentials** and publish the same benchmark table for
   `synthesis_mode: bedrock` beside the heuristic figures, so the two paths can be compared
   rather than assumed equivalent.
4. **Have a Braille transcriber review the two tables.** Code fidelity is proven lossless by
   round trip and literary fidelity names its losses, but neither has been read by a
   transcriber or on a physical display, and contracted Grade 2 is what an experienced reader
   actually wants for prose.
5. **Test with the people this is for.** Nothing here has been through a session with a blind
   or motor-impaired developer, and every design decision about cue ordering, readback
   wording and digest length is currently a hypothesis.
6. **Persist sessions and the audit chain.** Both live in memory, so a restart loses the
   tamper-evident history that makes the governance claim worth anything.
7. **Drive the companion with a real browser in CI.** `tests/e2e` parses the DOM; gate C5 is
   red because no browser driver runs, and a screen-reader journey with a real microphone
   belongs in that gap.

---

## Feedback for the Amazon teams

`docs/FRICTION_LOG.md` holds the detail. In short: publish MCP conformance vectors so two
implementers agree on status codes; state that a server may close the `GET` stream
immediately; add an ordering hint to content blocks so an accessibility cue can be declared
to precede its text; ship a local Bedrock emulator so an integration can be tested rather
than asserted; and let a deployed function expose the source revision it was built from.
