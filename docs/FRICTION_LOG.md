# Friction Log: building an accessibility MCP server for Alexa+

**Project:** Volcan
**Written by:** the engineer who wrote the code in this repository
**Scope rule for this document:** every entry below points at a file in this repository,
a command you can run, or an error that was actually observed while building it. Nothing
here describes hardware, an SDK or a device that this project never exercised. Where a
number appears, the command that printed it appears beside it.

What this project did **not** exercise, and therefore says nothing about: the Alexa Skills
Kit, the Alexa developer console, the Alexa AI CLI, skill or add-on certification, any Echo
device, and Alexa Presentation Language on real hardware. Entry 7 is about Amazon's
Alexa+ documentation as read, not about running Amazon's tools. The public Lambda did reach the Amazon Bedrock
Mantle authorization boundary on 2026-09-23, but its execution role was denied before a
model response. Entry 4 discusses that observed authorization failure. The later answer from
the public endpoint, `synthesis_mode` bedrock after the mantle grant was attached on
2026-09-30, is recorded with its command in [`docs/EVIDENCE.md`](EVIDENCE.md#the-public-deployment),
The public deployment, and is not friction, so this log does not repeat it.

## How each entry is written

Every entry carries the six fields the hackathon rules name for a friction log: the task
attempted, the steps taken, the expected and the actual result, a severity rating, the
workaround used, and an actionable suggestion. Where a field is not known, the entry says so
rather than filling it in.

**Severity scale.** One scale, used for every entry, rated on the impact this project
actually observed:

| Rating | Meaning |
|---|---|
| Blocking | The task could not be completed at all until a workaround was found. |
| Major | The task completed, but a client, a deployment or a reviewer got a wrong or missing result, or a false claim was close to shipping. |
| Minor | The task completed with extra work or a documented judgement call; nobody received a wrong result. |
| Cosmetic | Presentation only; no behaviour changed. |

| Entry | Area | Severity |
|---|---|---|
| 1 | MCP 2025-11-25 status codes | Minor |
| 2 | MCP `GET /mcp` stream with nothing to push | Blocking |
| 3 | MCP audio content block ordering, and our own earcon defect | Minor for the protocol gap, Major for our defect |
| 4 | Amazon Bedrock readiness and fallback | Major |
| 5 | AWS Lambda and API Gateway source revision | Major |
| 6 | MCP sessions behind a horizontally scaled Lambda | Major |
| 7 | Alexa+ MCP client documentation | Major |
| 8 | AWS Lambda bridge and Starlette SSE | Major |

The ratings are drafted from the observed impact written in each entry.

---

## 1. MCP revision 2025-11-25 had to be implemented by hand, and the spec leaves status codes to the implementer

**Task attempted.** Give Volcan a Model Context Protocol server over Streamable HTTP, at
revision 2025-11-25.

**Steps taken.** No MCP SDK was available in the build environment, so the protocol layer was
written from the specification: `src/interfaces/mcp_protocol.py` for the JSON-RPC semantics
and `src/interfaces/mcp_server.py` for the transport. Each failure case was then given an
HTTP status and a JSON-RPC error.

**Expected vs. actual result.** Expected: the specification names the HTTP status a transport
returns for each failure. Actual: the specification is clear about the shape of messages and
much less clear about what HTTP status a transport should return for each failure. Three cases
needed a decision with no single normative answer:

* a request carrying a session id the server never issued
* a request after `initialize` that omits `MCP-Protocol-Version`
* a top-level JSON array, now that batching has been removed

Volcan answers HTTP 404, a JSON-RPC `-32600`, and a JSON-RPC `-32600` respectively. A
different implementer would reasonably choose 400 for the second, and two conforming servers
would then disagree about what a client sees.

**Severity rating.** Minor. The server was built; the cost was a judgement call per case, and
no client was observed receiving a wrong answer because of it.

**Workaround used.** The choice is documented in the module docstring.
`scripts/mcp_conformance.py` in this repository prints a pass or fail line for each of 23
checks, so the choice is at least tested and visible.

**Actionable suggestion.** For the MCP and Alexa+ teams: publish a conformance vector set, a
list of request fixtures with the expected status code and JSON-RPC error code for each. That
single artifact would remove the ambiguity without changing the specification's tone.
`scripts/mcp_conformance.py` is a small version of what that artifact would look like.

---

## 2. A GET stream with nothing to push has no defined way to end

**Task attempted.** Serve the server-to-client SSE stream that the Streamable HTTP transport
opens at `GET /mcp`.

**Steps taken.** Volcan has no unsolicited server-initiated traffic: every result is the reply
to a `tools/call`. The first implementation returned an unbounded generator, which is the
natural reading of "open a stream", and the test suite called `TestClient.get("/mcp")`.

**Expected vs. actual result.** Expected: the request returns once the server has nothing to
send. Actual: `TestClient.get("/mcp")` never returned, and the test run hung until it was
interrupted. The transport was correct by the specification and unusable by any client that
reads to end of stream.

**Severity rating.** Blocking. No client that reads to end of stream could complete the
request, and the test run could not finish, until the workaround below.

**Workaround used.** `GET /mcp` emits one SSE comment frame saying the stream is open and that
this server has no pending messages, then closes. It does not emit an MCP
`notifications/message`, because the server does not advertise or negotiate the logging
capability. `tests/integration/test_mcp_conformance.py::test_get_mcp_opens_a_comment_only_terminating_sse_stream`
asserts the stream starts, contains no protocol message and finishes.

**Actionable suggestion.** State explicitly that a server with no pending server-initiated
messages MAY close the GET stream immediately after opening it, and that clients must tolerate
an immediately closed stream. One sentence prevents a class of hangs.

---

## 3. Audio content blocks exist, but nothing expresses "play this before you read that"

**Task attempted.** Deliver Volcan's earcon through MCP so that it reaches the listener before
the sentence. The earcons are the product, not decoration. A blind reviewer hears a falling
two-tone cue and knows a security finding is coming before any words arrive.

**Steps taken.** The `audio` content block is exactly the right primitive, and `play_earcon`
returns a 16-bit PCM WAV through it, verified by
`tests/integration/test_mcp_conformance.py::test_play_earcon_returns_a_playable_audio_content_block`.
Volcan returns text first, then audio, then a JSON detail block.

**Expected vs. actual result.** Expected: a way to say that the cue precedes its text.
Actual: a tool result is an ordered list of content blocks, but the ordering carries no
semantics a client is obliged to honour. A client is free to render the blocks in any order,
or to render the text and drop the audio. For a sighted user that is a cosmetic difference.
For the user this project exists for, the cue arriving after the sentence removes the reason
the cue exists. This project did not observe a client reordering or dropping the block; the
risk is read from the specification.

**The part that was our own bug, not the protocol's.** The paragraph above was true about the
ordering and false about the cue. Until 2026-09-08 every digest emitted `DIFF_READY`
regardless of what the parser found, so a benign patch and an AST-confirmed
security-sensitive patch returned byte-identical audio and there was no falling two-tone cue
to arrive early or late. A protocol gap is worth reporting; shipping it as cover for a
one-line defect in our own selection code is not.

**Severity rating.** Minor for the protocol gap, because no client in this project's runs
misbehaved and the impact is read from the specification. Major for our own defect, because
the cue that carries the verdict was identical for a benign and a security-sensitive patch
until 2026-09-08.

**Workaround used.** For the protocol gap, none is possible from the server side: Volcan
cannot oblige a client to play the cue first. For our defect, `src/domain/sonification.py`
now chooses the cue from the report, one selector shared by the REST, MCP, voice and CLI
surfaces, and `tests/unit/test_earcon_encodes_the_verdict.py` fails if the two payloads ever
match again.

**Actionable suggestion.** Add an optional hint on a content block, something like a
`priority` or `presentationOrder` field, so a tool can say that a cue is meant to precede its
text. Accessibility is where content ordering stops being cosmetic.

---

## 4. A partial readiness signal hid why the Amazon Bedrock path fell back

**Task attempted.** Answer each digest with Claude on Amazon Bedrock where a model is
available, and say plainly when it is not.

**Steps taken.**

1. **Historical context (2026-09-08).** `src/infrastructure/bedrock_adapter.py` calls Claude
   on Amazon Bedrock through the Anthropic SDK's `AnthropicBedrockMantle` client. The original
   development environment could resolve AWS credentials but did not include the SDK, so only
   the deterministic local path ran.
2. The model id pinned at the time, `anthropic.claude-3-5-sonnet-20241022-v2:0`, was a retired
   snapshot and answered `ResourceNotFoundException`.
3. **Live follow-up (2026-09-23).** The deployed function includes the Bedrock client and
   reaches the provider boundary.

**Expected vs. actual result.** Expected: a Bedrock answer, or a stated reason why there was
none. Actual:

* Digests carried `"synthesis_mode": "heuristic-local"`, but the page did not explain why.
  That made a missing dependency look like a product decision.
* **The part that was worse than the missing credentials.** Until 2026-09-08 the mode field
  was the only thing a reviewer got. `/health` reported `"bedrock_credentials_present": true`
  on the development machine, because boto3 resolves something from the local credential
  chain, and the companion page turned that into "AWS credentials are present, so a digest
  may be answered by Amazon Bedrock". Then every digest came back `heuristic-local` with no
  explanation, which reads as a product decision rather than a failure. The retired model id
  answered `ResourceNotFoundException`, and nothing in the codebase ever showed that string to
  anyone. The adapter had been recording the reason on itself the whole time and no caller
  read it.
* **The second half of the same mistake, corrected on 2026-09-08.** Naming the reason fixed
  the digest and left the health check wrong. `/health` still published
  `"bedrock_credentials_present": true` as a top-level field, and a reviewer reasonably read
  that as "the model path is available here". It was not: credentials resolved and the SDK
  was absent, so no call could be attempted at all, and the two facts were being published one
  at a time.
* On the deployed function on 2026-09-23, the execution role lacked
  `bedrock-mantle:CreateInference` for the account's default project, so the request fell
  back.

The general shape of the error is worth naming: a status endpoint that reports one input to a
decision, rather than the decision, will be read as reporting the decision.

**Severity rating.** Major. Every request still got an answer from the local engine, but no
model answered, the reason was hidden from the reviewer, and the health check invited the
false reading that the model path was available.

**Workaround used.**

* Every response now carries `synthesis_fallback_reason` and the page prints it beside the
  mode. A local environment without the optional dependency reports a fixed, actionable
  category rather than exposing provider internals.
* `/health` now publishes a single `bedrock_model_path.resolved_capability` computed from both
  facts, reading `unavailable_sdk_not_installed` on this machine, with the credential and SDK
  booleans underneath it as the evidence rather than as the headline.
* A labelled mode field in every response payload, so which path ran is visible in the data
  rather than inferred from the code.
* The Terraform policy now names the action and resource the Mantle client actually uses. The
  public response maps provider failures to fixed categories, so account, role, resource ARN
  and request identifiers cannot leak through the anonymous demo. Applying that production IAM
  change was an operator-authorized deployment step; the response receipt remains the proof of
  whichever engine answered a particular request.

**The underlying friction.** Without a local emulator, the only ways to develop against
Bedrock are to hold live credentials or to hand-write a double. Both make it easy to ship a
"Bedrock integration" that has never once called Bedrock, which is a failure mode a reviewer
cannot see from the outside.

**Actionable suggestion.** Ship a local Bedrock emulator, or a documented offline mode of the
SDK that returns fixed responses and is impossible to mistake for the real service. A
first-party emulator would let integrations be tested honestly rather than asserted.

---

## 5. A deployed function gives no way to ask which commit it is running

**Task attempted.** Confirm that the public endpoint runs the code being submitted.

**Steps taken.** Historical context: this project's API Gateway endpoint was probed on
2026-09-05. The recorded result is in `deploy_teardown_receipt.json`: `GET /health` answered
HTTP 200 with `{"status": "HEALTHY", "region": "eu-west-1", "serverless": true}`, and
`GET /mcp` answered HTTP 404 because the deployed bundle predates the MCP endpoint. The
receipt was then compared with the commit the deployer had written down.

**Expected vs. actual result.** Expected: a way to ask the platform which source revision a
deployed bundle was built from. Actual: the only reason that mismatch was catchable is that
the receipt records a commit SHA the deployer wrote down by hand. Nothing in API Gateway or
Lambda exposes the source revision a deployed bundle was built from, so "is the thing running
the thing I am submitting" is a question the platform cannot answer. A reviewer opening a live
URL has no way to tell which commit produced it.

**Severity rating.** Major. The public endpoint served a bundle without the MCP endpoint, and
only a hand-written note revealed it.

**Workaround used.** Resolution on 2026-09-23: the Lambda now receives `SOURCE_REVISION`
during deployment, exposes it through `/health`, and carries the same immutable revision as
an AWS resource tag. The public MCP and REST paths were executed against that revision. The
old receipt remains labelled as a superseded historical probe rather than being rewritten as
current evidence.

**Actionable suggestion.** Let a deployment carry an immutable revision tag that the runtime
can read and expose, so a health endpoint can report the exact source revision without the
deployer having to remember to write it down.

---

## 6. Process-local MCP sessions fail behind a horizontally scaled Lambda endpoint

**Task attempted.** Pass the MCP conformance sweep against the public Lambda endpoint, with
sessions.

**Steps taken.** Observed on 2026-09-23. The first public conformance sweep completed ten
passes, then one request carrying the session id returned by `initialize` reached a different
Lambda execution environment. A standalone rerun followed.

**Expected vs. actual result.** Expected: the session id returned by `initialize` is honoured
on the next request. Actual: that request received HTTP 404. A standalone rerun passed 21 of
21 checks. The intermittent result was therefore routing-sensitive, not a protocol-message
defect.

**Severity rating.** Major. A valid session was refused intermittently on the public endpoint,
and the failure did not reproduce in local tests.

**Workaround used.** MCP 2025-11-25 lets a Streamable HTTP server choose whether to assign a
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
rather than retrying a possible write. Later, `/health` on the public endpoint reported
`durable_state` `configured_reachable` for the DynamoDB table `volcan-state-euw1-prod` in the
2026-09-30 check recorded in [`docs/EVIDENCE.md`](EVIDENCE.md#the-public-deployment); this
log does not record a completed cross-worker journey.

**Actionable suggestion.** Put the stateless deployment pattern beside the
session-management section of the transport guide. A random id plus an in-process set looks
correct in local tests and fails only after a load balancer sends the next request elsewhere.

---

## 7. Amazon documents the Alexa+ MCP client by body, not by header

**Task attempted.** Make sure the Alexa+ MCP client, as Amazon documents it, is served by this
server.

**Steps taken.** On 2026-09-27 the Alexa+ add-on docs were read to find what an integration
for a developer tool consists of. The MCP Toolkit path makes Alexa+ the MCP client of the
server this repository already has, so the useful local test was to replay the client requests
Amazon documents. `python scripts/replay_alexa_plus_envelopes.py` prints both cases side by
side.

**Expected vs. actual result.** Expected: the documentation says which headers the client
sends and which revision it speaks. Actual: the lifecycle page shows the initialize and
`tools/call` bodies and no HTTP headers. Its initialize asks for revision `2025-03-26`, while
the overview says Alexa+ supports `2025-11-25`. Revision 2025-03-26 had no
`MCP-Protocol-Version` header, and until 2026-09-27 this server refused any request after
initialize that lacked it. So the documentation cannot tell a server author whether the real
client sends the header.

The same replay caught a mistake of this server's own, and then a mistake in the first fix for
it. The server listed 2025-03-26 as supported without honouring it (no version header in that
revision, and batches it must accept). Echoing 2025-03-26 back, the first fix, left a client
that speaks both revisions with no header to send, and the replay showed it refused. Removing
2025-03-26 from the supported list, so that such a client is answered 2025-11-25, was the
second fix, and it refused a third kind of client, one that declares 2025-03-26 in its header,
which the server had served before. The replay played two kinds of client and could not show
it; an audit did.

**Severity rating.** Major. Until 2026-09-27 a client shaped like Amazon's documented example
was refused after initialize, and the first two fixes each refused a different kind of client
the replay plays. Whether the real Alexa+ client was ever affected is unknown, because Alexa+ has never
called this server.

**Workaround used.** This server now follows the specification's fallback for a missing header
(the negotiated revision, else 2025-03-26), so the answer no longer decides whether the client
is served. The third fix accepts a header declaring 2025-03-26 without negotiating the
revision, and the replay now plays all three kinds of client. `docs/EVIDENCE.md`, Road to
Alexa+, records each step.

**Actionable suggestion.** One recorded request from the Alexa+ client, headers included, on
the lifecycle page. Separately, the hackathon FAQ says the toolkit and simulator are for
select partners only and that participants cannot get access, so a builder outside that group
can check a manifest against the documented schema and nothing more.

---

## 8. The Lambda bridge answered http.disconnect, and Starlette cancelled the SSE stream

**Task attempted.** Serve the `GET /mcp` SSE stream from the deployed Lambda.

**Steps taken.** `src/interfaces/lambda_handler.py` translates one API Gateway v2 event into
one ASGI request. After delivering Lambda's single buffered body, its `receive` answered
`http.disconnect` on every further call. The deployed endpoint was then checked with
`python scripts/mcp_conformance.py https://qylv1gxor9.execute-api.eu-west-1.amazonaws.com/mcp --expect-mode stateless`.

**Expected vs. actual result.** Expected: the same SSE comment the local server returns.
Actual: Starlette's `StreamingResponse` races `listen_for_disconnect` against the stream, so an
immediate disconnect cancels the body before its first chunk. Locally the race usually
resolved the other way and `GET /mcp` returned its SSE comment; on the deployed dependency set
the disconnect won every time, and the endpoint answered 200 with
`Content-Type: text/event-stream` and zero bytes. The conformance command above printed
`22/23 checks passed, 1 failed` on 2026-09-29 against that deploy.

**Severity rating.** Major. The public endpoint returned an empty stream and failed one
conformance check, while local runs mostly passed.

**Workaround used.** The fix keeps `receive` blocked after the body, exactly like a server
socket with no traffic, and `tests/unit/test_lambda_handler.py` pins the contract instead of
the race outcome. The conformance re-run after the redeploy is recorded in the deployment
evidence for this change.

**Actionable suggestion.** Response streaming from Lambda, so the bridge is a real server with
a real disconnect signal instead of a buffered translation of one event.

---

## 9. What worked well

This section is not a friction entry. It is here so the feedback is not only complaints.

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

The figures the README used to quote, and why they changed, used to sit in this file. They
are a history of the README rather than friction, so they moved to
[`docs/EVIDENCE.md`](EVIDENCE.md#figures-the-readme-used-to-quote-and-why-they-changed).
