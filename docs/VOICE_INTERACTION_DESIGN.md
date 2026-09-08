# Volcan: voice interaction design

> **This is a design document, not a skill.** No Alexa skill package is submitted with this
> project, no skill has been through certification, and nothing here has run on an Echo
> device. What follows is the dialogue design the web companion implements and that an
> Alexa+ integration would map onto, together with the API each turn calls.

The companion at `docs/index.html` implements the same turns using the browser's Web Speech
API: `SpeechRecognition` for input where the browser exposes it, with a typed twin for every
command, and `speechSynthesis` for output. Its header carries the label **Not an Alexa skill**
above the fold at all times, and it prints the command that starts a server whenever none
answers.

---

## 0. The review dialogue, one turn at a time

The journey a blind developer needs from start to finish is a conversation, not a summary, and
it is implemented as one state machine per session in `src/domain/review_dialogue.py` with the
grammar in `src/domain/review_grammar.py`. Both surfaces reach it with a transcript:
`POST /api/review/turn` and the MCP tool `review_dialogue_turn`. What comes back, in order, is
the **readback** (`Understood: next line.` or `Corrected, previous.`), the **answer**, the
**earcon** when the turn has one, and the machine-readable detail: state, focus, the current
line with its old and new numbers, the speech rate, and on `confirm` the review outcome.

| State | How you get there | What you can do |
|---|---|---|
| `IDLE` | Before anything is open | `open <url>`, `open the patch`, `help` |
| `OVERVIEW` | `open`, `summary`, `file by file`, `findings` | Focus a file by name or number, `next`, `previous` |
| `FILE` | `what changed in auth.py`, `file 2`, `next`, `previous` | `read the lines`, `line 14`, `next`, `previous` |
| `LINES` | `read the lines`, `line 14` | `next line`, `previous line`, `next hunk`, `spell that`, `repeat` |
| `CONFIRM_REVIEW` | `request changes: <comment>` after a pull request is open | `confirm` or `cancel`; every navigation is refused until one is said |
| `RECORDED`, `SUBMITTED`, `REFUSED` | `confirm`, as the server resolved it | Anything from `OVERVIEW`; `where am I` reports the last outcome |

Three properties hold in every state and each has a test in `tests/unit/test_review_dialogue.py`:
the readback precedes the action; `no, I said <command>` restores the state before the
misheard command and applies the meant one, without undoing a `slower` or `faster`; and
`stop` is silent and changes nothing. The design rule behind the readback is that a
misheard command is cheap when the listener hears it a second before its consequence, and
expensive after.

The review itself is a governed action. `request changes` mints a single-use HMAC grant bound
to the repository, the pull request number, the head commit and the SHA-256 of the comment,
with a 300 second lease. `confirm` presents it; the server checks custody (the human who said
confirm is the approver, the dialogue is the staging principal), verifies the grant, re-reads
the live head commit and refuses with `STALE_HEAD` if it moved, and then either records the
exact request (the default, `RECORDED`), sends it when the server runs with
`VOLCAN_GITHUB_WRITE=1` and a `GITHUB_TOKEN` (`SUBMITTED`), or reports GitHub's refusal
(`REFUSED`, `UNAUTHORIZED` for a token without `pull_requests: write`). The earcon says which:
`DRY_RUN_RECORDED` is two level notes, deliberately unlike the rising `ACTION_COMMITTED`,
because a listener who cannot see the page has only the cue to tell "sent" from "would have
sent".

**What a microphone changes, and what it does not.** Nothing in the machine knows whether a
transcript came from `SpeechRecognition` or from a keyboard. That is why the whole dialogue is
proven with injected transcripts and why the page keeps a typed path for every command: the
recogniser's accuracy is the browser vendor's, and the readback is the product's answer to it.

---

## 1. Turns the product also implements

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
| `DRY_RUN_RECORDED` | two level notes, 494 Hz then 494 Hz | "Recorded and not sent." |

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
