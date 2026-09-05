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
| UAT-13 | Every advertised MCP tool can actually be called | All eleven tools return content blocks and none returns a transport error | `tests/integration/test_mcp_conformance.py::test_every_advertised_tool_can_be_called_and_returns_content_blocks` |
| UAT-14 | The earcon arrives as playable audio, not a description | The `audio` block decodes to a RIFF WAVE file | `tests/integration/test_mcp_conformance.py::test_play_earcon_returns_a_playable_audio_content_block` |
| UAT-15 | The companion is reachable by keyboard alone | No click handler on a non-interactive element, every control a real button, a visible focus ring, a documented keyboard map | `tests/e2e/test_html_structure.py` |
| UAT-16 | Results are announced to a screen reader | `aria-live` regions for digests and lease state, `role="alert"` for security findings | `tests/e2e/test_html_structure.py::test_results_are_announced_through_live_regions` |
| UAT-17 | Reduced motion is honoured | The preference is respected in CSS and in the canvas animation | `tests/e2e/test_html_structure.py::test_reduced_motion_is_honoured_in_css_and_in_script` |
| UAT-18 | The companion never claims a connection it did not make | The initial state is `checking`, the state comes from a real `GET /health`, and browser-only results are tagged | `tests/e2e/test_html_structure.py::test_the_page_makes_no_connection_claim_before_a_real_fetch` |

Run them all:

```bash
python -m pytest tests/ -v
```

---

## 2. Manual scenario, run against a live server

**Precondition:** `python -m src.interfaces.mcp_server` is running on `127.0.0.1:8000`.

1. Run `python scripts/mcp_conformance.py`. Expect 18 of 18 checks to pass.
2. Open `http://127.0.0.1:8000/`. The banner must read **LIVE SERVER** and quote the HTTP
   status it actually received.
3. Press Tab once. The **Skip to main content** link must appear with a visible focus ring.
4. Tab to **Speak level 0 digest** and press Enter. A chime plays, the digest is spoken,
   and the digest panel names the synthesis mode that produced it.
5. Select **Stage action**. A lease countdown starts and a grant beginning `v1.` appears.
6. Select **Approve with grant**. The result must say the command was planned and that
   nothing was executed.
7. Stop the server and reload the page. The banner must change to **SIMULATED** and every
   result must carry the SIMULATED tag.

---

## 3. Not covered here, and why

| Gap | Why it is not covered | What would close it |
|---|---|---|
| Real browser journey | No browser driver is vendored in this environment | Add playwright and a scripted walk of the companion |
| Echo device dialogue | No Alexa skill exists and none was submitted | Build and certify a skill, then test on hardware |
| Refreshable Braille display | No display was available | Verify the U+2800 stream on a Focus 40 or an Orbit Reader |
| Sip-and-puff switch | No switch was available | Feed real pulse timings through `process_switch_pulse` |
| Amazon Bedrock synthesis | No AWS credentials in this environment | Set credentials, rerun, confirm `synthesis_mode` reads `bedrock` |
