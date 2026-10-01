# Volcan: Devpost submission

## Tagline

Volcan lets blind and low-vision software developers review autonomous coding agents
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
   repository; `docs/EVIDENCE.md` carries the owner command that produces that receipt.

Around those renderings:

* **Security flags come before comprehension, and they say what changed.** Two deterministic
  passes run. A keyword pass catches authentication, cryptographic, database and
  process-execution vocabulary. A structural pass then compares the added and removed lines,
  as parsed Python or, for JavaScript and TypeScript files, as tokens, and reports what the
  change *did*: an authorization comparison inverted, a cross-origin policy widened to any
  origin, a verification call deleted and not replaced.
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
  `GET /mcp`, optional cryptographically random sessions on a single-process host, a stateless
  public Lambda transport for request-contained calls, protocol version negotiation, Origin
  validation, and the full set of JSON-RPC error codes. Transport is stateless on Lambda;
  application state is shared only when `/health.durable_state.backend` reports `dynamodb`.
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
  unauthorized token. The Terraform candidate adds versioned DynamoDB dialogue state,
  atomic session/action staging, atomic action/nonce claims and reviewer/repository-scoped
  audit chains whose terminal action and record advance in one transaction;
  durable voice ownership and action namespaces come from the authenticated server roster,
  or a fixed anonymous owner when no credential is sent, never the caller's `user_id`; the
  anonymous page's audit trail reads one public demo chain with caller-written text withheld;
  cold-start and concurrency tests use independent adapter instances rather than shared Python
  objects.
* **The companion page.** One HTML file with no remote script, served by FastAPI at `/` and `/demo`; it makes no request to another origin, because its two typefaces, Atkinson Hyperlegible and JetBrains Mono, are inlined from `docs/fonts` under the SIL Open Font License.
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
  23 checks. All 23 passed in both stateful and stateless transport modes on 2026-09-27,
  including the ones that are easy to get wrong: HTTP
  404 for a session the server never minted, HTTP 202 with no body for
  `notifications/initialized`, `-32602` rather than a transport error for an unknown tool, a
  405 whose `Allow` header names every method the endpoint really accepts, a request without
  the version header served under the session's negotiated revision or as 2025-03-26 as the
  specification directs, and HTTP 400 for an unsupported version header on every verb.
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
* **86.4% detection recall over n=40 hand-labelled patches** (81.8% until the 2026-09-28 TLS rule
  closed one known miss), twenty-two that must raise a
  security flag and eighteen that must not, with 0% false positives, against a baseline of 0%
  because a screen reader reading raw patch text surfaces no security categorisation at all.
  Printed by `python scripts/benchmark_suite.py`, recomputed by
  `tests/unit/test_security_detection_corpus.py`, measured over the corpus in
  `tests/fixtures/diff_corpus.py`. It measures behaviour on those fixtures and is not a claim
  about any real repository.

  The figure was 100% over n=24 while the corpus contained only patches the rules already
  handled. Four positives were then added *because* nothing here detects them, and
  `docs/EVIDENCE.md` names all four: a deleted authorization guard block, a removed permission
  decorator, `verify=False` added to an outbound call, and an IAM policy widened in JSON.
  Recall fell to 81.8% and became worth reading; one of the four, `verify=False`, was closed on
  2026-09-28 by the TLS rule, a miss known before that rule was written. The four are pinned by fixture id, so a new
  miss fails the build and closing one means deleting its id from the list.
* **JavaScript and TypeScript, on a held-out half.** Rules for the same three structural
  findings were added on 2026-09-27, tuned on a training half of 64 self-authored, synthetic
  patches and measured on the other half (independent of the tuning, not of the author): recall 25.0% to 62.5% for JavaScript (50.0% before the SQL rule) and 37.5% to
  75.0% for TypeScript, 8 patches per language that must flag. False positives stayed at 0.0%
  and 25.0% of 8, all from the unchanged keyword pass on this corpus. The rules read tokens
  without control-flow reasoning: two rounds of eight probes written after them to find where
  that breaks now give 4 of 4 detected with 2 of 4 over-flagged (`--probes`; 0 of 4 and 4 of 4
  before the rule work) and 4 of 4 with 1 of 4 (`--probes2`), all by a structural rule. Printed by
  `python scripts/benchmark_js_ts_detection.py`; the split rule, the seed and every miss are in
  `docs/EVIDENCE.md`.

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
`python scripts/mcp_conformance.py http://127.0.0.1:8000/mcp` to watch 23 of 23 protocol
checks pass. The companion page performs the same `initialize` and `tools/list` handshake in
the browser and renders the negotiated protocol version, the stateful or stateless transport
choice and every published tool schema. The public Lambda chooses stateless transport so an
independent request is not rejected for lacking a process-specific MCP id. The Terraform
candidate also provisions encrypted DynamoDB state for multi-turn dialogue, pending actions,
spent nonces and scoped transactional audit chains. Its Lambda environment carries only a
Secrets Manager ARN, while the signing value is fetched at cold start and never enters
Terraform. Local mode remains in-memory. A running instance proves configured and reachable
state through `/health.durable_state` without AWS identifiers; this text does not treat
committed Terraform as a deployment receipt.

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
been sent from this repository. The owner command that produces one is in `docs/EVIDENCE.md`.

**Real, labelled Amazon Bedrock path.** The adapter calls Claude on Amazon
Bedrock through the Anthropic SDK's `AnthropicBedrockMantle` client, pinned to
`anthropic.claude-opus-5`. Every response states whether `bedrock` or the deterministic local
path answered. When Bedrock fails, `synthesis_fallback_reason` returns one bounded category;
provider account, role and request identifiers are never returned to the anonymous client.
The checked-in infrastructure narrows the intended Lambda grant to
`bedrock-mantle:CreateInference` on its account-scoped default project. A deployment missing
that grant falls back with the bounded permission category.

`/health` used to publish `bedrock_credentials_present: true` here, which was true and
misleading: credentials resolve on this machine while the SDK is absent, so no call could be
attempted at all. It now publishes one resolved capability computed from both facts, reading
`unavailable_sdk_not_installed` on 2026-09-08, with the credential and SDK booleans underneath
it as the evidence. `docs/EVIDENCE.md` carries the exact command that reproduces a per-request receipt.

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
CloudWatch. A live GitHub write remains absent. An Alexa+ add-on deployment is absent because
the add-on tools are partner-only ([hackathon FAQ](https://amazonappdev2026.devpost.com/details/faqs)). No Alexa skill has been
certified and nothing has run on an Echo device; for this track the FAQ says "no physical
device needed".

---

## Who would buy this, and out of which budget

**Measured population, guessed price.** No buyer has been interviewed or contacted, and there
is no revenue projection or conversion rate. Every figure below comes from a source fetched and
read on 2026-09-28; the quotes and links are in `docs/EVIDENCE.md`.

**The user.** The blind or low-vision engineer who reviews agent-written patches by ear. The
US Census Bureau's American Community Survey 2024 microdata puts US civilian employed software
developers with a vision difficulty at 17,933 (90% margin +/- 2,686), 0.775% of 2.31 million;
`python scripts/size_blind_developer_population.py` reproduces it. The question counts anyone
"blind or having serious difficulty seeing, even when wearing glasses", so it is an upper bound
on screen-reader users. Eurostat counts more than 10 million ICT specialists in the EU in 2025;
no EU share with a vision difficulty was found, so no EU user count is given.

**The buyer.** The employer, out of the line that pays for what a disabled employee needs to
work: Directive 2000/78/EC, Article 5, obliges employers to provide reasonable accommodation, and
Section 508 obliges US federal agencies to give disabled employees comparable access to their
technology. The European Accessibility Act, applied from 28 June 2025, covers consumer products
and services and does not oblige anyone to make a developer tool accessible; an earlier version
of this section overstated it.

**Price, an untested hypothesis:** $24 per developer seat per month billed annually, CodeRabbit's
published annual list price for pull request review; GitHub Copilot Business, the agent being
reviewed, lists $19 a seat. If all 17,933 bought, about $5.2 million a year in the US, which is
small; growing past it needs an org-wide price or users beyond blind developers, and neither is
priced or tested. The wedge, who signs first, is a team that has switched on a coding agent,
generally available from GitHub on 25 September 2025 and built to "request a review from you",
and employs a blind developer who is asked to give that review.

**The riskiest assumption** is that reviewing agent pull requests by screen reader hurts enough
to switch. The cheapest test is five timed sessions, own screen reader then Volcan, passing only
if three of five are faster and would use it again.

**The first ten to approach have not been contacted.** Deque Systems, Level Access, TPGi,
Microsoft accessibility engineering, Google central accessibility, GitHub accessibility, the
UK Government Digital Service, European Commission DIGIT, the Royal National Institute of Blind
People and the American Foundation for the Blind. Nothing there is a pipeline or a warm
introduction; it is a target list written from the outside. The full section, including what
does and does not compound, is in `docs/EVIDENCE.md`.

---

## Track and mini challenge

* **Track: Alexa+.** Claimed as a real MCP server that an Alexa+ MCP add-on would call, plus an
  explicitly simulated voice web experience. That is the shape the
  [hackathon FAQ](https://amazonappdev2026.devpost.com/details/faqs) asks for: "build a self-hosted MCP server (or
  Agent Skill) per the Official Rules, and demo it via your own web-based simulator or front
  end." The add-on package in `alexa_plus/` is built and tested locally, not certified or
  deployed, because the FAQ says the add-on tools are "available to select partners only". A replay of Amazon's
  documented Alexa+ client requests, against a local build and not the registered endpoint,
  gets the finding back from all three client shapes it plays: one that follows the protocol's
  version rules, one that declares the revision it asked for, and one that never sends the
  version header. Alexa+ has never called Volcan. The claim is the protocol work, not a
  certified add-on or skill.
* **Mini challenge: AWS Builder.** Claimed as a real Amazon Bedrock adapter whose responses
  state which path produced them. The claim is the labelled integration and safe fallback,
  not a quality benchmark against other models.

---

## What is next

1. **Deploy the Alexa+ add-on, if Amazon grants MCP Toolkit access**, which the hackathon FAQ
   says participants cannot get at present, so the voice experience stops being a simulation.
   The package in `alexa_plus/` passes Amazon's documented schema locally; what remains is that
   access, the owner's hosted privacy page and images, a redeploy of the current commit, the
   header question the replay raised, and a test in Amazon's simulator and on an Echo device.
2. **Send one live review** with `VOLCAN_GITHUB_WRITE=1` and a fine-grained token against a
   repository the owner controls, and record the receipt. The code path exists and is tested
   against a mock; the receipt does not.
3. **Publish a repeatable Bedrock-versus-local benchmark** for latency and summary usefulness;
   one successful live receipt proves the integration, not comparative quality.
4. **Have a Braille transcriber review the two tables.** Code fidelity is proven lossless by
   round trip and literary fidelity names its losses, but neither has been read by a
   transcriber or on a physical display, and contracted Grade 2 is what an experienced reader
   actually wants for prose.
5. **Test with the people this is for.** Nothing here has been through a session with a blind
   or motor-impaired developer, and every design decision about cue ordering, readback
   wording and digest length is currently a hypothesis.
6. **Deploy and fault-test the durable-state candidate.** The cold-start and concurrent-worker
   suite proves the conditional DynamoDB model with an in-process double. The remaining proof
   is an exact-SHA deployment and a cross-container dialogue/approval run. Local tests already
   inject stage/finalization failures and response loss; a post-claim external-write crash still
   requires the documented operator-reconciliation state.
7. **Drive the companion with assistive technology.** Playwright covers the browser journey
   in CI, while a screen-reader journey with a real microphone
   belongs in that gap.

---

## Feedback for the Amazon teams

`docs/FRICTION_LOG.md` holds the detail. In short: publish MCP conformance vectors so two
implementers agree on status codes; state that a server may close the `GET` stream
immediately; add an ordering hint to content blocks so an accessibility cue can be declared
to precede its text; ship a local Bedrock emulator so an integration can be tested rather
than asserted; and let a deployed function expose the source revision it was built from.
