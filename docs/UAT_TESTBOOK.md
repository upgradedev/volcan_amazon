# Volcan: User Acceptance Testbook

**Product:** Volcan, an accessible voice-first AI agent forge
**Version:** 0.1.0
**Persona under test:** blind and low-vision software developers

Every scenario below maps to an automated test that exists in this repository and that you
can run. Where a scenario cannot be automated here, it says so and names what is missing,
rather than describing an outcome nobody observed.

No scenario in this document claims an Echo device, physical Braille display, sip-and-puff
switch or target-user result. Those need the corresponding hardware or consenting user. The
automated scenarios test the browser, protocol and API behaviour those surfaces would drive;
the per-request receipt separately records whether Bedrock or the deterministic path answered.

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
| UAT-16 | Results are announced to a screen reader | one voice per answer: by default one polite status line per hero press and the answer spoken finding first by the speech engine, operators named; with **My screen reader speaks the answers** on, the page is silent and the status line (`runStatus`, `reviewStatus`, `govStatus`) carries the whole answer; the dialogue log is not a live region (no `role="alert"`, which read the finding a second time) | `tests/e2e/test_html_structure.py::test_a_hero_result_reaches_a_listener_through_one_channel`, `tests/e2e/test_first_screen.py::test_the_first_screen_shows_the_real_answer_without_speaking_playing_or_announcing` |
| UAT-17 | Reduced motion is honoured | The preference is respected in CSS and in the canvas animation | `tests/e2e/test_html_structure.py::test_reduced_motion_is_honoured` |
| UAT-18 | The companion never claims a connection it did not make | The initial state is `checking`, the state comes from a real `GET /health`, and browser-only results are tagged | `tests/e2e/test_html_structure.py::test_the_page_makes_no_connection_claim_before_a_real_fetch` |
| UAT-19 | The earcon says which verdict the digest reached | A security-sensitive patch and a benign one return different WAV bytes: the falling `SECURITY_FINDING` cue and the rising `DIFF_READY` cue, on the REST, MCP, voice and drill-down paths alike | `tests/unit/test_earcon_encodes_the_verdict.py` |
| UAT-20 | A benign patch does not sound the alarm | The cue stays `DIFF_READY` when there is no critical finding and no `SECURITY_SENSITIVE` section | `tests/unit/test_earcon_encodes_the_verdict.py::test_a_benign_patch_still_gets_the_rising_ready_cue` |
| UAT-21 | The quickstart installs the model path without promising its output | The install line carries the `bedrock` extra, pyproject declares it, the receipt distinguishes a Bedrock answer from fallback, and public provider failures stay bounded | `tests/unit/test_quickstart_reaches_the_model_path.py` |
| UAT-22 | Every preset the demo ships reaches the rule its label promises | Each of the four shipped patches is lifted out of `docs/index.html`, run through the production parser, and produces exactly the rule its chip names; the control produces none; and no rule ships without a preset | `tests/e2e/test_shipped_presets_reach_their_rule.py` |
| UAT-23 | A request missing the protocol version header is refused whether or not it holds a session | Both requests return `-32600` with the same message, neither carries a `result` member, and `GET` and `DELETE` refuse with HTTP 400 | `tests/integration/test_mcp_conformance.py::test_a_valid_session_never_excuses_a_missing_protocol_version` |
| UAT-24 | `/health` never implies a model will answer | The resolved capability is the conjunction of credentials and SDK presence, the ready state promises an attempt rather than an answer, and detecting the SDK does not import it | `tests/unit/test_health_reports_the_resolved_model_path.py` |
| UAT-25 | A blind developer converses about a pull request by injected transcript | `open` reads back and speaks the head commit; `what changed in <file>` focuses the file and names the finding; `read the lines` speaks every numbered line verbatim; `line 14` lands on the new side; `spell that` names `!=` as `bang, equals`; `no, I said previous` undoes the misheard command; an unrecognised transcript reads back what was heard and changes nothing | `tests/unit/test_review_dialogue.py` |
| UAT-26 | A confirmed review is recorded, not sent, and every refusal is named | With neither `VOLCAN_GITHUB_WRITE` nor a token the outcome is `dry_run` with the exact request recorded and no `POST` made; a moved head is `STALE_HEAD`; a missing, tampered, foreign or expired grant, a self-approval and a token without permission are each refused with their code and an audit line | `tests/unit/test_review_dialogue_use_case.py`, `tests/unit/test_github_review_adapter.py` |
| UAT-27 | The whole journey runs over REST and MCP against a scripted GitHub | `POST /api/review/turn` and `tools/call review_dialogue_turn` carry the readback, the answer, the earcon and the outcome; `/health` publishes `github_review_path` without a token value | `tests/integration/test_review_dialogue_api.py` |
| UAT-28 | Braille keeps every code symbol apart, or says what it lost | All 95 printable ASCII characters map to distinct eight-dot cells and decode back; literary fidelity names the collided characters per patch; the README table equals the module's | `tests/unit/test_braille_code_fidelity.py` |
| UAT-29 | The page listens where it can, always keeps a typed path, and labels itself | `SpeechRecognition` with a stated absence, a command box with `Enter`, `stopAudio()` before every post, readback before answer at the returned rate, one voice per turn, a dry run printed as recorded and not sent, and the not-an-Alexa-skill label above the fold | `tests/e2e/test_html_structure.py` |
| UAT-30 | A missing protocol version header is refused for every method | `tools/list`, `tools/call`, `ping`, `resources/list` and an unknown method all answer `-32600` with the same message, with and without a valid session, and never `-32601` | `tests/integration/test_mcp_conformance.py::test_the_version_rule_runs_before_dispatch_for_every_post_initialize_method` |
| UAT-31 | A review survives a Lambda cold start | One worker opens and stages; fresh use-case and grant-issuer instances load the same owner, dialogue and pending action, confirm once, and a third instance cannot repeat it | `tests/unit/test_durable_volcan_state.py::test_review_dialogue_pending_action_nonce_and_audit_survive_cold_starts` |
| UAT-32 | Concurrent workers cannot consume one grant twice | Twenty-four workers present the same valid grant; one conditional nonce write wins and the other twenty-three receive `REPLAYED` | `tests/unit/test_durable_volcan_state.py::test_grant_nonce_has_exactly_one_winner_across_workers` |
| UAT-33 | Concurrent audit appends remain one chain | Thirty-two workers append through fresh repository instances; sequences are contiguous and every hash link verifies | `tests/unit/test_durable_volcan_state.py::test_parallel_audit_appends_form_one_intact_chain` |
| UAT-34 | A state outage never falls back to process memory | A failed DynamoDB write raises `DurableStateError`; no in-memory session is created as a substitute | `tests/unit/test_durable_volcan_state.py::test_storage_outage_raises_and_never_falls_back_to_memory` |
| UAT-35 | Stage has no action/session crash window | A rejected transaction leaves neither an action nor a staged session; a committed transaction whose response is lost returns the exact persisted grant on a fresh-worker retry | `tests/unit/test_durable_volcan_state.py::test_review_stage_transaction_failure_leaves_no_orphan_and_retry_succeeds`, `test_lost_review_stage_response_replays_exact_persisted_grant_after_cold_start`, `test_lost_voice_stage_response_replays_exact_grant_without_duplicate_action` |
| UAT-36 | Terminal action and audit line cannot diverge | An injected finalization failure leaves the durable action `APPROVED`, writes no audit line and prevents a second execution | `tests/unit/test_durable_volcan_state.py::test_finalize_failure_never_persists_terminal_action_without_audit` |
| UAT-37 | Voice and review action ids cannot cross authorities or sessions | Identical caller action ids occupy opaque per-owner/repository/session namespaces; review action ids with the same visible id do not collide across owners; approve and reject refuse an id other than the current session's staged action | `tests/unit/test_durable_volcan_state.py::test_voice_namespaces_prevent_default_id_collision_between_sessions`, `test_voice_session_cannot_approve_or_reject_another_sessions_action`, `test_review_action_ids_are_isolated_by_owner_repository_and_session` |
| UAT-38 | Durable audit read is authenticated and scoped | Anonymous read is 401; each reviewer sees only records derived from their server-side repository roster; partition keys expose no identity or repository | `tests/unit/test_durable_volcan_state.py::test_durable_audit_route_is_authenticated_and_repository_scoped` |
| UAT-39 | Secret and health metadata remain bounded | Durable mode resolves a 32-byte-or-longer SecretString from the configured ARN, refuses direct values and provider failures without echoing them, and health distinguishes reachability without table/ARN/account identifiers | `tests/unit/test_durable_volcan_state.py::test_durable_secret_comes_from_arn_and_never_uses_direct_environment`, `test_secret_failures_are_bounded_and_never_echo_secret`, `test_health_distinguishes_configured_reachable_from_unreachable` |
| UAT-40 | Caller identity cannot own a durable voice action | Durable voice turns require a server-authenticated reviewer, require its repository allowlist, ignore caller `user_id` for ownership and leave the victim action pending after an unauthorized rejection attempt | `tests/unit/test_durable_volcan_state.py::test_durable_voice_uses_server_principal_not_caller_user_id` |

Run them all:

```bash
python -m pytest tests/ -v
```

---

## 2. Manual scenario, run against a live server

**Precondition:** `python -m src.interfaces.mcp_server` is running on `127.0.0.1:8000`.

1. Run `python scripts/mcp_conformance.py`. Expect 22 of 22 checks to pass. On 2026-09-08,
   before the positive comment-only GET vector was added, it printed
   `SUMMARY: 22/22 checks passed, 0 failed`.
2. Open `http://127.0.0.1:8000/`. The status pill in the top bar must read **Online**, and the
   connection banner in **Evidence**, tab **Server and MCP**, must read **Server reached** and quote
   the HTTP status and the round trip it actually measured, plus the resolved model path the
   server reported. On this machine that line reads `unavailable_sdk_not_installed`.
   Before anything is pressed, the stage must already show the server's answer for the loaded
   patch, silently: the waveform in grey with a **Falling** contour, the verdict sentence, the
   Braille cells, and the line **Server's first sentence, not played yet.** No
   sound and no speech until step 4.
3. Press Tab once. The **Skip to main content** link must appear with a visible focus ring.
4. Press **Hear this code review** without changing the patch. The preset loaded on first
   paint is the inverted authorization check, so the falling `SECURITY_FINDING` cue plays and
   the finding reads *an authorization comparison was inverted: user.role == 'admin' became
   user.role != 'admin'*. The synthesis meter names the engine that answered and, when no
   model did, prints the reason beside it.
5. Press **Clean change, no finding**, then **Hear this code review** again. The cue must
   change to the rising `DIFF_READY` and the findings panel must stay empty. That pair is the
   demonstration that the detector can refuse.
6. In **Evidence**, open the **Governed actions** tab and select **Stage an action**. A lease countdown starts and a grant beginning `v1.` appears.
7. Select **Approve with the grant**. The result must say the command was planned and that
   nothing was executed.
8. In **Talk through a real pull request**, paste the URL of a public GitHub pull request, press
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
| Real assistive-technology journey | Playwright drives the primary digest, MCP, earcon and Braille path, but cannot establish real screen-reader or refreshable-display usability | Run the scripted task with a consenting target user and record completion, errors, time and feedback |
| Echo device dialogue | No Alexa skill exists and none was submitted | Build and certify a skill, then test on hardware |
| Refreshable Braille display | No display was available | Verify the U+2800 stream on a Focus 40 or an Orbit Reader |
| Sip-and-puff switch | No switch was available | Feed real pulse timings through `process_switch_pulse` |
| A live `REQUEST_CHANGES` review on GitHub | The write is dry-run by default and the flag has never been set here; sending one needs a token with `pull_requests: write` on a repository the owner controls | Start the server with `VOLCAN_GITHUB_WRITE=1` and `GITHUB_TOKEN`, run scenario 8, and keep the review id the panel prints; the README's Known limitations carries the exact commands |
| A spoken command through a real microphone | `SpeechRecognition` cannot be driven headlessly and no browser runs in the suite; the dialogue is proven with injected transcripts and the browser walk used the typed path | Say the scenario 8 commands aloud in Chrome or Edge and record the dialogue log |
| Repeatable Bedrock quality comparison | The live path and fallback are separately labelled, but one successful call does not compare summary usefulness or latency across representative patches | Run a fixed, disclosed patch corpus through both modes; publish raw latency and blinded usefulness ratings without treating within-system fixtures as user evidence |
