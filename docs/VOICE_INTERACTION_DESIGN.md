# Volcan: voice interaction design

> **This is a design document, not a skill.** No Alexa skill package is submitted with this
> project, no skill has been through certification, and nothing here has run on an Echo
> device. What follows is the dialogue design the web companion implements and that an
> Alexa+ integration would map onto, together with the API each turn calls.

The companion at `docs/index.html` implements the same turns using the browser's Web Speech
API. It labels itself SIMULATED whenever no Volcan server answers.

---

## 1. Turns the product actually implements

Each turn below is handled by `voice_turn` on both surfaces: `POST /api/voice_turn` on the
REST surface and `tools/call` with `name: "voice_turn"` on the MCP surface. The `intent`
field carries the turn.

### Summarize the workspace patch
* **Spoken form the companion accepts:** "summarize my workspace diff", "what changed"
* **Intent:** `summarize_diff`
* **Slots:** `raw_diff` (the patch), `level` (0 executive, 1 file-by-file, 2 drill-down)
* **Response:** spoken digest, the counts, the security findings, `synthesis_mode` saying
  whether a model or the local path produced the words, and the earcon that carries the
  verdict: `SECURITY_FINDING` when the patch has a critical finding or a
  `SECURITY_SENSITIVE` section, `DIFF_READY` when it has neither. One selector,
  `earcon_for_report` in `src/domain/sonification.py`, makes that choice for every surface
* **Implementation:** `src/application/voice_turn_use_case.py`

### Drill into one file
* **Spoken form:** "inspect section one", "explain the changes in auth dot py"
* **Endpoint:** `POST /api/drill_down_section`, or MCP tool `drill_down_section`
* **Response:** symbol-level explanation, the category, the significance, the security
  flags, and the `DRILL_DOWN_OPENED` earcon, replaced by `SECURITY_FINDING` when this
  section is the flagged one, so the verdict survives the descent into a single file

### Stage a command
* **Spoken form:** "stage running the unit tests"
* **Intent:** `stage_action`
* **Slots:** `action_id`, `action_type`, `command`, `summary_spoken`
* **Response:** the payload hash, a single-use authorization grant, the lease expiry, the
  dry-run plan, and the `GOVERNANCE_CHALLENGE` earcon
* **Note:** the command is planned. It is never executed.

### Release a staged command
* **Spoken form:** "approve action act four four with grant ..."
* **Intent:** `approve_action`
* **Slots:** `action_id`, `approval_grant`, `approver_id`
* **Response on success:** the plan that was approved, and the `ACTION_COMMITTED` earcon
* **Response on refusal:** a named refusal code and a spoken reason, with the `TEST_FAILED`
  earcon. Refusals are `BAD_SIGNATURE`, `WRONG_ACTION`, `CONTENT_MISMATCH`, `EXPIRED`,
  `REPLAYED`, `AGENT_MAY_NOT_APPROVE`, `SELF_APPROVAL`, `NOT_PENDING` and `UNKNOWN_ACTION`.

### Reject a staged command
* **Spoken form:** "reject", "cancel that"
* **Intent:** `reject_action`
* **Response:** the action is discarded and recorded in the audit trail as unapproved

---

## 2. Earcon vocabulary

Each cue is synthesized as 16-bit PCM at 22.05 kHz by `src/domain/sonification.py` and is
returned over MCP as an `audio` content block. The spoken fallback is returned beside it so
a client that cannot play audio still says something meaningful.

| Cue | Shape | Spoken fallback |
|---|---|---|
| `AGENT_THINKING` | 440 Hz then 554 Hz | "Volcan is analyzing your workspace." |
| `DIFF_READY` | rising 523, 659, 784 Hz | "Semantic diff digest is ready." |
| `SECURITY_FINDING` | falling 622 Hz then 349 Hz | "Security-sensitive change in this patch." |
| `TEST_PASSED` | 587 Hz then 880 Hz | "All test assertions passed cleanly." |
| `TEST_FAILED` | falling 311 Hz then 220 Hz | "Test suite execution failed." |
| `LINT_WARNING` | single 466 Hz | "Linter raised warnings." |
| `GOVERNANCE_CHALLENGE` | 659, 523, 659 Hz | "Voice authorization required for this action." |
| `ACTION_COMMITTED` | rising 440, 880, 1175 Hz | "Action executed successfully." |
| `DRILL_DOWN_OPENED` | 523 Hz then 784 Hz | "Inspecting symbol details." |

Falling contours mean something went wrong and rising contours mean something completed.
A listener learns the pair in one session, which is the point: the cue arrives before the
sentence does.

That only holds if the cue is a function of the result. It was not until 2026-09-08: every
digest returned `DIFF_READY`, so a benign patch and a security-sensitive one produced
byte-identical audio. `src/domain/sonification.py` now chooses the cue from the report, and
`tests/unit/test_earcon_encodes_the_verdict.py` compares the two payloads. That test prints
the fingerprints it asserts on, so the claim is checkable in one command:

```
$ python -m pytest tests/unit/test_earcon_encodes_the_verdict.py -q -s
benign   | earcon DIFF_READY       | sha256[:16] 08f48648388bff02 | 19448 WAV bytes | 25932 base64 chars
security | earcon SECURITY_FINDING | sha256[:16] 22c91bec11e275d1 | 26504 WAV bytes | 35340 base64 chars
8 passed in 0.60s
```

---

## 3. What an Alexa+ integration would need, and does not have here

| Requirement | Status |
|---|---|
| A skill manifest and interaction model | Not written; the earlier one pointed at a route that returns HTTP 404 and was deleted |
| A publicly reachable HTTPS endpoint serving `/mcp` | Not available; the deployed endpoint runs an older commit and answers 404 for `/mcp` |
| Account linking for a developer's repository | Not designed |
| Certification | Not attempted |
| Testing on an Echo device | Not performed |

Anyone extending this project toward a real skill starts from the turns in section 1: they
are implemented, tested, and reachable over both HTTP surfaces today.
