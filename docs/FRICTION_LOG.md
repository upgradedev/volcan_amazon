# Friction Log: building an accessibility MCP server for Alexa+

**Project:** Volcan
**Written by:** the engineer who wrote the code in this repository
**Scope rule for this document:** every entry below points at a file in this repository,
a command you can run, or an error that was actually observed while building it. Nothing
here describes hardware, an SDK or a device that this project never exercised. Where a
number appears, the command that printed it appears beside it.

What this project did **not** exercise, and therefore says nothing about: the Alexa Skills
Kit, the Alexa developer console, the Alexa AI CLI, skill or add-on certification, any Echo
device, and Alexa Presentation Language on real hardware. Section 8 is about Amazon's
Alexa+ documentation as read, not about running Amazon's tools. The public Lambda did reach the Amazon Bedrock
Mantle authorization boundary on 2026-09-23, but its execution role was denied before a
model response. The log therefore discusses that observed authorization failure and does
not claim a successful Bedrock generation.

---

## 1. MCP revision 2025-11-25 had to be implemented by hand, and the spec leaves status
codes to the implementer

**Context.** Volcan needed a Model Context Protocol server over Streamable HTTP. No MCP
SDK was available in the build environment, so the protocol layer was written from the
specification: `src/interfaces/mcp_protocol.py` for the JSON-RPC semantics and
`src/interfaces/mcp_server.py` for the transport.

**Observed friction.** The specification is clear about the shape of messages and much
less clear about what HTTP status a transport should return for each failure. Three cases
needed a decision with no single normative answer:

* a request carrying a session id the server never issued
* a request after `initialize` that omits `MCP-Protocol-Version`
* a top-level JSON array, now that batching has been removed

Volcan answers HTTP 404, a JSON-RPC `-32600`, and a JSON-RPC `-32600` respectively, and
documents that choice in the module docstring. A different implementer would reasonably
choose 400 for the second, and two conforming servers would then disagree about what a
client sees.

**Recommendation for the MCP and Alexa+ teams.** Publish a conformance vector set: a list
of request fixtures with the expected status code and JSON-RPC error code for each. That
single artifact would remove the ambiguity without changing the specification's tone.
`scripts/mcp_conformance.py` in this repository is a small version of what that artifact
would look like; running it prints a pass or fail line for each of 22 checks.

---

## 2. A GET stream with nothing to push has no defined way to end

**Context.** The Streamable HTTP transport opens a server-to-client SSE stream at
`GET /mcp`. Volcan has no unsolicited server-initiated traffic: every result is the reply
to a `tools/call`.

**Observed error.** The first implementation returned an unbounded generator, which is the
natural reading of "open a stream". `TestClient.get("/mcp")` then never returned, and the
test run hung until it was interrupted. The transport was correct by the specification and
unusable by any client that reads to end of stream.

**Workaround in this repository.** `GET /mcp` emits one SSE comment frame saying the stream
is open and that this server has no pending messages, then closes. It does not emit an MCP
`notifications/message`, because the server does not advertise or negotiate the logging
capability. `tests/integration/test_mcp_conformance.py::test_get_mcp_opens_a_comment_only_terminating_sse_stream`
asserts the stream starts, contains no protocol message and finishes.

**Recommendation.** State explicitly that a server with no pending server-initiated
messages MAY close the GET stream immediately after opening it, and that clients must
tolerate an immediately closed stream. One sentence prevents a class of hangs.

---

## 3. Audio content blocks exist, but nothing expresses "play this before you read that"

**Context.** Volcan's earcons are the product, not decoration. A blind reviewer hears a
falling two-tone cue and knows a security finding is coming before any words arrive. The
`audio` content block is exactly the right primitive, and `play_earcon` returns a 16-bit
PCM WAV through it, verified by
`tests/integration/test_mcp_conformance.py::test_play_earcon_returns_a_playable_audio_content_block`.

**Observed friction.** A tool result is an ordered list of content blocks, but the ordering
carries no semantics a client is obliged to honour. Volcan returns text first, then audio,
then a JSON detail block, and a client is free to render them in any order, or to render
the text and drop the audio. For a sighted user that is a cosmetic difference. For the user
this project exists for, the cue arriving after the sentence removes the reason the cue
exists.

**Recommendation.** Add an optional hint on a content block, something like a `priority` or
`presentationOrder` field, so a tool can say that a cue is meant to precede its text.
Accessibility is where content ordering stops being cosmetic.

**The part that was our own bug, not the protocol's.** The paragraph above was true about
the ordering and false about the cue. Until 2026-09-08 every digest emitted `DIFF_READY`
regardless of what the parser found, so a benign patch and an AST-confirmed
security-sensitive patch returned byte-identical audio and there was no falling two-tone cue
to arrive early or late. A protocol gap is worth reporting; shipping it as cover for a
one-line defect in our own selection code is not. `src/domain/sonification.py` now chooses
the cue from the report, one selector shared by the REST, MCP, voice and CLI surfaces, and
`tests/unit/test_earcon_encodes_the_verdict.py` fails if the two payloads ever match again.

---

## 4. A partial readiness signal hid why the Amazon Bedrock path fell back

**Historical context (2026-09-08).** `src/infrastructure/bedrock_adapter.py` calls Claude on
Amazon Bedrock through the Anthropic SDK's `AnthropicBedrockMantle` client. The original
development environment could resolve AWS credentials but did not include the SDK, so only
the deterministic local path ran.

**Observed behaviour then.** Digests carried `"synthesis_mode": "heuristic-local"`, but the
page did not explain why. That made a missing dependency look like a product decision.

**The part that was worse than the missing credentials.** Until 2026-09-08 the mode field
was the only thing a reviewer got. `/health` reported `"bedrock_credentials_present": true`
on the development machine, because boto3 resolves something from the local credential
chain, and the companion page turned that into "AWS credentials are present, so a digest may
be answered by Amazon Bedrock". Then every digest came back `heuristic-local` with no
explanation, which reads as a product decision rather than a failure. The model id pinned at
the time, `anthropic.claude-3-5-sonnet-20241022-v2:0`, was a retired snapshot and answered
`ResourceNotFoundException`, and nothing in the codebase ever showed that string to anyone.
The adapter had been recording the reason on itself the whole time and no caller read it.
Every response now carries `synthesis_fallback_reason` and the page prints it beside the
mode. A local environment without the optional dependency reports a fixed, actionable
category rather than exposing provider internals.

**The second half of the same mistake, corrected on 2026-09-08.** Naming the reason fixed the
digest and left the health check wrong. `/health` still published
`"bedrock_credentials_present": true` as a top-level field, and a reviewer reasonably read
that as "the model path is available here". It was not: credentials resolved and the SDK was
absent, so no call could be attempted at all, and the two facts were being published one at a
time. `/health` now publishes a single `bedrock_model_path.resolved_capability` computed from
both, reading `unavailable_sdk_not_installed` on this machine, with the credential and SDK
booleans underneath it as the evidence rather than as the headline. The general shape of the
error is worth naming: a status endpoint that reports one input to a decision, rather than the
decision, will be read as reporting the decision.

**Friction.** Without a local emulator, the only ways to develop against Bedrock are to
hold live credentials or to hand-write a double. Both make it easy to ship a "Bedrock
integration" that has never once called Bedrock, which is a failure mode a reviewer cannot
see from the outside. The mitigation Volcan uses is a labelled mode field in every response
payload, so which path ran is visible in the data rather than inferred from the code.

**Live follow-up (2026-09-23).** The deployed function includes the Bedrock client and reaches
the provider boundary. Its execution role, however, lacks
`bedrock-mantle:CreateInference` for the account's default project, so the request falls back.
The Terraform policy now names the action and resource the Mantle client actually uses. The
public response maps provider failures to fixed categories, so account, role, resource ARN
and request identifiers cannot leak through the anonymous demo. Applying that production IAM
change remains an operator-authorized deployment step; the response receipt remains the proof
of whichever engine answered a particular request.

**Recommendation.** Ship a local Bedrock emulator, or a documented offline mode of the SDK
that returns fixed responses and is impossible to mistake for the real service. A
first-party emulator would let integrations be tested honestly rather than asserted.

---

## 5. A deployed function gives no way to ask which commit it is running

**Historical context.** This project's API Gateway endpoint was probed on 2026-09-05. The recorded
result is in `deploy_teardown_receipt.json`: `GET /health` answered HTTP 200 with
`{"status": "HEALTHY", "region": "eu-west-1", "serverless": true}`, and `GET /mcp` answered
HTTP 404 because the deployed bundle predates the MCP endpoint.

**Observed friction.** The only reason that mismatch was catchable is that the receipt
records a commit SHA the deployer wrote down by hand. Nothing in API Gateway or Lambda
exposes the source revision a deployed bundle was built from, so "is the thing running the
thing I am submitting" is a question the platform cannot answer. A reviewer opening a live
URL has no way to tell which commit produced it.

**Resolution on 2026-09-23.** The Lambda now receives `SOURCE_REVISION` during deployment,
exposes it through `/health`, and carries the same immutable revision as an AWS resource tag.
The public MCP and REST paths were executed against that revision. The old receipt remains
labelled as a superseded historical probe rather than being rewritten as current evidence.

**Recommendation.** Let a deployment carry an immutable revision tag that the runtime can
read and expose, so a health endpoint can report the exact source revision without the
deployer having to remember to write it down.

---

## 6. Process-local MCP sessions fail behind a horizontally scaled Lambda endpoint

**Observed on 2026-09-23.** The first public conformance sweep completed ten passes, then
one request carrying the session id returned by `initialize` reached a different Lambda
execution environment and received HTTP 404. A standalone rerun passed 21 of 21 checks.
The intermittent result was therefore routing-sensitive, not a protocol-message defect.

**Resolution.** MCP 2025-11-25 lets a Streamable HTTP server choose whether to assign a
session id. The public deployment now sets `VOLCAN_MCP_SESSION_MODE=stateless`: initialize
returns no `Mcp-Session-Id`, and request-contained calls carry only the negotiated version.
The single-process default remains stateful so its creation, unknown-id and termination
behaviours stay directly testable. The conformance runner accepts and identifies both
permitted modes rather than silently retrying a 404. This resolves transport affinity only:
dialogue, pending approvals, nonce consumption and audit records remain process-local, and
dialogue loses context if a later request lands elsewhere. Approval confirmation cannot find
or release a pending action in that case and fails closed.

**Application-state follow-up (source candidate, 2026-09-23).** The next failure was ours,
not MCP's: stateless transport did not make the application stateless. The Terraform candidate
now provisions one encrypted, pay-per-request DynamoDB table. Review and voice session keys are
opaque and owner-scoped; durable voice ownership comes from the Bearer roster rather than the
JSON `user_id`; review and voice actions use opaque owner/repository/session namespaces;
staging writes the session and action together; approval claims the
action and nonce together; terminal state and its reviewer/repository-scoped audit record
advance together. Local mode remains in memory and `/health` reports configured/reachable
status without AWS identifiers. Cold-start and concurrent-worker tests exercise the candidate,
but it is not called deployed until an exact source revision reports reachable DynamoDB and
completes the cross-worker journey. A crash after an action is claimed and before GitHub's
response is known deliberately leaves an ambiguous `APPROVED` state for operator reconciliation
rather than retrying a possible write.

**Suggestion.** Put the stateless deployment pattern beside the session-management section
of the transport guide. A random id plus an in-process set looks correct in local tests and
fails only after a load balancer sends the next request elsewhere.

---

## 7. Figures the README used to quote, and why they changed

The README's quickstart now quotes each number once, as measured on the day it was last
edited. The history those paragraphs carried is kept here, word for word, so the reasons
behind the changes are not lost.

**The preset chips.** Until 2026-09-08 a chip label and its rule had separated: the first preset removed a hardcoded secret,
which is a security *improvement*, and the other two produced no finding at all, so the first
press showed the weakest output the product can give.

**Time to first result, as the README stated it until 2026-09-26.**

Step 1 reported
`421 passed, 1 warning in 5.00s` on the run that closed this round; the run before it, with
one more test still red, took 7.00 s, and earlier runs that day with a smaller suite took 8.77
s, 5.06 s, 5.22 s and 4.74 s, so the count is the claim here and the duration is not. The
server in step 2 answered its first `GET /health` with
HTTP 200 **1.4 seconds** after launch, printed by
[`scripts/measure_cold_start.py`](../scripts/measure_cold_start.py). That script launches its
own server, so stop the one from step 2 before running it. It refuses to time a process that
was already warm, and says so rather than printing a figure it cannot stand behind. Step 3
printed
`21/21 checks passed, 0 failed`. The first digest round trip in step 4 was **39.0 ms** in
headless Chromium at 1440x900 on 2026-09-26, read from the page's own meter, with the server
started as in step 2 on port 8743 and no AWS credential file present; three further presses
of the same button on the same page read 30.2 ms, 28.8 ms and 31.9 ms. The first press is the
one quoted, because that is the press a judge makes. Earlier rounds published 117.2 ms
(2026-09-08) and 72.6 ms (2026-09-06). On a machine without AWS credentials those earlier
builds walked the whole boto3 credential chain, ending in the instance-metadata probe, on
every request: on 2026-09-26, before the fix, `curl` timed `GET /health` at 2.030, 2.024 and
2.030 s on this machine with no credential file, and the chain alone took 2.054 s. The server
now resolves the chain once at startup and caches the answer; the same `curl` then read
0.039, 0.003 and 0.005 s. The page measures the
round trip itself with `performance.now()` on every run and takes no figure from this file. The `pip install` step depends on your network
and is not measured here.

The figures that replaced these are in `docs/EVIDENCE.md`, "Quickstart, in full", step 4,
each with its date and the command or page meter that printed it.

**Figures the README carried until round 4 on 2026-09-26, and the contradiction they made.**
The quickstart said `552 passed` and a cold start of **2.0 seconds**, while the Measured numbers
table in the same file said `515 passing; 91.26% statement coverage` (dated 2026-09-24) and a
cold start of **1.4 s**, and the quickstart heading said "Four steps" above five. A scorer
read the pairs as the README contradicting itself, which it was. On 2026-09-26 each was
re-measured once and one value kept: `python -m pytest tests/ -q --cov=src --cov-fail-under=85`
printed 552 passed and 91.52% coverage before the round's four new page tests, and 556
collected after them; `python scripts/measure_cold_start.py` printed 1.7, 1.7 and 1.8 s on
three runs. The README became a one-screen story and the full record moved to
`docs/EVIDENCE.md`.

**Figures and wording until 2026-09-27, before the JavaScript and TypeScript rules and the
Alexa+ add-on package.** The README and `docs/EVIDENCE.md` said `577 passed` and 91.98%
statement coverage; `python -m pytest tests/ -q --cov=src` printed 623 and 92.08% after the
round. The README's security row said the rules read Python only, which was true; the Python
corpus figure, 81.8% recall and 0% false positives over n=40, did not change. The README and
the page said the road to Alexa+ was not built, which was true until the add-on package was
committed.

---

## 8. Amazon documents the Alexa+ MCP client by body, not by header

**Context.** On 2026-09-27 the Alexa+ add-on docs were read to find what an integration for a
developer tool consists of. The MCP Toolkit path makes Alexa+ the MCP client of the server
this repository already has, so the useful local test was to replay the client requests
Amazon documents.

**Observed friction.** The lifecycle page shows the initialize and `tools/call` bodies and no
HTTP headers. Its initialize asks for revision `2025-03-26`, while the overview says Alexa+
supports `2025-11-25`. Revision 2025-03-26 had no `MCP-Protocol-Version` header, and this
server refuses any request after initialize that lacks it. So the documentation cannot tell a
server author whether the real client will be refused. `python scripts/replay_alexa_plus_envelopes.py`
prints both cases side by side. The same replay caught a mistake of this server's own, and
then a mistake in the first fix for it. The server listed 2025-03-26 as supported without
honouring it (no version header in that revision, and batches it must accept). Echoing
2025-03-26 back, the first fix, left a client that speaks both revisions with no header to send,
and the replay showed it refused. Removing 2025-03-26 from the supported list, so that such a
client is answered 2025-11-25, was the second fix, and it refused a third kind of client, one
that declares 2025-03-26 in its header, which the server had served before. The replay played
two kinds of client and could not show it; an audit did. The third fix accepts that header
without negotiating the revision, and the replay now plays all three. `docs/EVIDENCE.md`, Road
to Alexa+, records each step.

**What would remove it.** One recorded request from the Alexa+ client, headers included, on
the lifecycle page. Separately, the hackathon FAQ says the toolkit and simulator are for
select partners only and that participants cannot get access, so a builder outside that group
can check a manifest against the documented schema and nothing more.

---

## 9. What worked well

* The Model Context Protocol is a good fit for assistive tooling. Because tools are
  described by JSON Schema, Volcan generates its whole catalog from the pydantic models
  that parse the arguments, and the published schema cannot drift from the code. That is
  twelve tools with zero hand-written schema.
* The `audio` content block means an accessibility cue is a first-class result rather than
  a side channel, which is the single design decision that made this project possible over
  a text protocol.
* Streamable HTTP over one endpoint kept the transport small enough to write by hand and
  read in one sitting: `src/interfaces/mcp_protocol.py` is 315 lines and has no
  dependencies beyond pydantic.
