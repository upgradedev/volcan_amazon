# Volcan: User Acceptance Testbook

**Product:** Volcan, an accessible voice-first AI agent forge
**Version:** 0.1.0
**Persona under test:** blind and mobility-impaired software developers

Every scenario below maps to an automated test that exists in this repository and that you
can run. Where a scenario cannot be automated here, it says so and names what is missing,
rather than describing an outcome nobody observed.

No scenario in this document involves an Echo device, a physical Braille display, a
sip-and-puff switch or an Amazon Bedrock call, because none of those were available while
this was built. The behaviour those devices would drive is tested through the API they
would call.

---

## 1. Automated scenarios

| ID | Scenario | What must happen | Automated test |
|---|---|---|---|
| UAT-01 | A patch is turned into a spoken digest with an earcon | The digest names files and lines with agreeing plurals, and the response carries `synthesis_mode` | `tests/integration/test_rest_endpoints.py::test_digest_reports_which_synthesis_path_ran` |
| UAT-02 | A security-sensitive patch is flagged before anything else is said | Every one of the 12 patches labelled `expect_security_flag` raises a flag, and none of the 12 benign patches does | `tests/unit/test_security_detection_corpus.py` |
| UAT-03 | A high-consequence command is staged behind a lease | The action is `PENDING_APPROVAL`, a grant is issued, the command is planned and `executed` is false | `tests/integration/test_rest_endpoints.py::test_stage_then_confirm_then_audit` |
| UAT-04 | An expired lease cannot be released | The action moves to `EXPIRED` and the planner is never called | `tests/unit/test_governance.py::test_expired_lease_cannot_be_approved` |
| UAT-05 | A forged grant is refused | Refusal code `BAD_SIGNATURE`, and the planner is never called | `tests/unit/test_governance.py::test_forged_grant_is_refused` |
| UAT-06 | A grant cannot be used twice | Refusal code `REPLAYED` on the second use | `tests/unit/test_governance.py::test_replayed_grant_is_refused_on_second_use` |
| UAT-07 | An agent cannot approve its own proposal | Refusal code `AGENT_MAY_NOT_APPROVE` | `tests/unit/test_governance.py::test_an_agent_may_not_approve_its_own_proposal` |
| UAT-08 | A command outside the allowlist is refused with a reason | `allowed` is false, `executed` is false, and the reason names the allowlist | `tests/unit/test_dry_run_executor.py` |
| UAT-09 | Nothing executes a shell command | The planner module imports and calls no execution primitive, asserted by parsing its AST | `tests/unit/test_dry_run_executor.py::test_the_module_imports_no_execution_primitive` |
| UAT-10 | A patch renders as Unicode Braille | Output falls in the U+2800 block and preserves line structure | `tests/unit/test_braille_translator.py`, `tests/integration/test_braille_api.py` |
| UAT-11 | A switch pulse resolves to a navigation action | Sip, puff, single button and foot pedal each map to a defined action | `tests/unit/test_adaptive_switch.py`, `tests/integration/test_accessibility_api.py` |
| UAT-12 | An MCP client can complete the full handshake | initialize, initialized, tools/list, tools/call all succeed with the documented shapes | `tests/integration/test_mcp_conformance.py` |
| UAT-13 | Every advertised MCP tool can actually be called | All twelve tools return content blocks and none returns a transport error | `tests/integration/test_mcp_conformance.py::test_every_advertised_tool_can_be_called_and_returns_content_blocks` |
| UAT-14 | The earcon arrives as playable audio, not a description | The `audio` block decodes to a RIFF WAVE file | `tests/integration/test_mcp_conformance.py::test_play_earcon_returns_a_playable_audio_content_block` |
| UAT-15 | The companion is reachable by keyboard alone | No click handler on a non-interactive element, every control a real button, a visible focus ring, a documented keyboard map | `tests/e2e/test_html_structure.py` |
| UAT-16 | Results are announced to a screen reader | `aria-live` regions for digests and lease state, `role="alert"` for security findings | `tests/e2e/test_html_structure.py::test_results_are_announced_through_live_regions` |
| UAT-17 | Reduced motion is honoured | The preference is respected in CSS and in the canvas animation | `tests/e2e/test_html_structure.py::test_reduced_motion_is_honoured` |
| UAT-18 | The companion never claims a connection it did not make | The initial state is `checking`, the state comes from a real `GET /health`, and browser-only results are tagged | `tests/e2e/test_html_structure.py::test_the_page_makes_no_connection_claim_before_a_real_fetch` |
| UAT-19 | The earcon says which verdict the digest reached | A security-sensitive patch and a benign one return different WAV bytes: the falling `SECURITY_FINDING` cue and the rising `DIFF_READY` cue, on the REST, MCP, voice and drill-down paths alike | `tests/unit/test_earcon_encodes_the_verdict.py` |
| UAT-20 | A benign patch does not sound the alarm | The cue stays `DIFF_READY` when there is no critical finding and no `SECURITY_SENSITIVE` section | `tests/unit/test_earcon_encodes_the_verdict.py::test_a_benign_patch_still_gets_the_rising_ready_cue` |
| UAT-21 | The quickstart installs the model path without promising its output | The install line carries the `bedrock` extra, pyproject declares it, and the README keeps saying no model has answered here | `tests/unit/test_quickstart_reaches_the_model_path.py` |
| UAT-22 | Every preset the demo ships reaches the rule its label promises | Each of the four shipped patches is lifted out of `docs/index.html`, run through the production parser, and produces exactly the rule its chip names; the control produces none; and no rule ships without a preset | `tests/e2e/test_shipped_presets_reach_their_rule.py` |
| UAT-23 | A request missing the protocol version header is refused whether or not it holds a session | Both requests return `-32600` with the same message, neither carries a `result` member, and `GET` and `DELETE` refuse with HTTP 400 | `tests/integration/test_mcp_conformance.py::test_a_valid_session_never_excuses_a_missing_protocol_version` |
| UAT-24 | `/health` never implies a model will answer | The resolved capability is the conjunction of credentials and SDK presence, the ready state promises an attempt rather than an answer, and detecting the SDK does not import it | `tests/unit/test_health_reports_the_resolved_model_path.py` |
| UAT-25 | A blind developer converses about a pull request by injected transcript | `open` reads back and speaks the head commit; `what changed in <file>` focuses the file and names the finding; `read the lines` speaks every numbered line verbatim; `line 14` lands on the new side; `spell that` names `!=` as `bang, equals`; `no, I said previous` undoes the misheard command; an unrecognised transcript reads back what was heard and changes nothing | `tests/unit/test_review_dialogue.py` |
| UAT-26 | A confirmed review is recorded, not sent, and every refusal is named | With neither `VOLCAN_GITHUB_WRITE` nor a token the outcome is `dry_run` with the exact request recorded and no `POST` made; a moved head is `STALE_HEAD`; a missing, tampered, foreign or expired grant, a self-approval and a token without permission are each refused with their code and an audit line | `tests/unit/test_review_dialogue_use_case.py`, `tests/unit/test_github_review_adapter.py` |
| UAT-27 | The whole journey runs over REST and MCP against a scripted GitHub | `POST /api/review/turn` and `tools/call review_dialogue_turn` carry the readback, the answer, the earcon and the outcome; `/health` publishes `github_review_path` without a token value | `tests/integration/test_review_dialogue_api.py` |
| UAT-28 | Braille keeps every code symbol apart, or says what it lost | All 95 printable ASCII characters map to distinct eight-dot cells and decode back; literary fidelity names the collided characters per patch; the README table equals the module's | `tests/unit/test_braille_code_fidelity.py` |
| UAT-29 | The page listens where it can, always keeps a typed path, and labels itself | `SpeechRecognition` with a stated absence, a command box with `Enter`, `stopAudio()` before every post, readback before answer at the returned rate, every state in a live region, a dry run printed as recorded and not sent, and the not-an-Alexa-skill label above the fold | `tests/e2e/test_html_structure.py` |
| UAT-30 | A missing protocol version header is refused for every method | `tools/list`, `tools/call`, `ping`, `resources/list` and an unknown method all answer `-32600` with the same message, with and without a valid session, and never `-32601` | `tests/integration/test_mcp_conformance.py::test_the_version_rule_runs_before_dispatch_for_every_post_initialize_method` |

Run them all:

```bash
python -m pytest tests/ -v
```

---

## 2. Manual scenario, run against a live server

**Precondition:** `python -m src.interfaces.mcp_server` is running on `127.0.0.1:8000`.

1. Run `python scripts/mcp_conformance.py`. Expect 21 of 21 checks to pass. On 2026-09-08 it
   printed `SUMMARY: 21/21 checks passed, 0 failed`.
2. Open `http://127.0.0.1:8000/`. The connection banner must read **Server reached** and quote
   the HTTP status and the round trip it actually measured, plus the resolved model path the
   server reported. On this machine that line reads `unavailable_sdk_not_installed`.
3. Press Tab once. The **Skip to main content** link must appear with a visible focus ring.
4. Press **Hear this code review** without changing the patch. The preset loaded on first
   paint is the inverted authorization check, so the falling `SECURITY_FINDING` cue plays and
   the finding reads *an authorization comparison was inverted: user.role == 'admin' became
   user.role != 'admin'*. The synthesis meter names the engine that answered and, when no
   model did, prints the reason beside it.
5. Press **Clean change, no finding**, then **Hear this code review** again. The cue must
   change to the rising `DIFF_READY` and the findings panel must stay empty. That pair is the
   demonstration that the detector can refuse.
6. Select **Stage an action**. A lease countdown starts and a grant beginning `v1.` appears.
7. Select **Approve with the grant**. The result must say the command was planned and that
   nothing was executed.
8. In **Converse about a pull request**, paste the URL of a public GitHub pull request, press
   <kbd>Alt</kbd>+<kbd>4</kbd>, type `open` and press Enter. The log must show `Typed: open`,
   then `Understood: open the pull request.`, then the overview naming the head commit. Type
   `file 1`, `read the lines`, `next`, `no, I said previous`, `spell that`, then
   `request changes: <a comment>` and `confirm`. The review panel must read
   `recorded and not sent` beside the exact `POST` body, never `submitted`, because the
   server was started without `VOLCAN_GITHUB_WRITE=1`. Performed in Chrome on 2026-09-08
   against `https://github.com/python/cpython/pull/1`: the overview read
   `head commit 02a87ce` and the confirm turn read `Dry run. Nothing was sent to GitHub.`
9. Press **Start listening**. In Chrome or Edge the button reads **Stop listening** and the
   side label reads `listening`; in Firefox the log states that the browser exposes no
   `SpeechRecognition` API and focus moves to the typed box. Nobody has yet spoken a command
   into a microphone on this page and recorded the result; that is an owner action.
10. Stop the server and reload the page. The banner must change to **No server**, and every
    panel must print the command that starts one rather than a result. Nothing on this page
    falls back to a browser reimplementation, so no result appears at all until a server
    answers.

---

## 3. Not covered here, and why

| Gap | Why it is not covered | What would close it |
|---|---|---|
| Real browser journey | No browser driver is vendored in this environment | Add playwright and a scripted walk of the companion |
| Echo device dialogue | No Alexa skill exists and none was submitted | Build and certify a skill, then test on hardware |
| Refreshable Braille display | No display was available | Verify the U+2800 stream on a Focus 40 or an Orbit Reader |
| Sip-and-puff switch | No switch was available | Feed real pulse timings through `process_switch_pulse` |
| A live `REQUEST_CHANGES` review on GitHub | The write is dry-run by default and the flag has never been set here; sending one needs a token with `pull_requests: write` on a repository the owner controls | Start the server with `VOLCAN_GITHUB_WRITE=1` and `GITHUB_TOKEN`, run scenario 8, and keep the review id the panel prints; the README's Known limitations carries the exact commands |
| A spoken command through a real microphone | `SpeechRecognition` cannot be driven headlessly and no browser runs in the suite; the dialogue is proven with injected transcripts and the browser walk used the typed path | Say the scenario 8 commands aloud in Chrome or Edge and record the dialogue log |
| Amazon Bedrock synthesis | The path is implemented and shape-tested against a stub, and has never executed. The quickstart installs the client with `pip install -e ".[dev,bedrock]"`, but nobody working on this repository has AWS access that can confirm the pinned model id, and installing the SDK where credentials resolve would fire a real billed call against an account without its owner's say-so. `/health` reports the resolved capability, `unavailable_sdk_not_installed` here, and every digest says why in `synthesis_fallback_reason` | Run the quickstart install with working credentials, rerun one digest, confirm `synthesis_mode` reads `bedrock` and the reason is null. The exact command is in the README's Known limitations |
