"""End-to-end journey: a blind developer reviews a patch and releases an action.

The journey ends the way the product really behaves: the approved action is
*planned* and reported back, not executed, and a command outside the allowlist
is refused with a spoken reason.
"""
from fastapi.testclient import TestClient

from src.interfaces.mcp_server import app

client = TestClient(app)

PR_DIFF = """diff --git a/src/payments/stripe_webhook.py b/src/payments/stripe_webhook.py
new file mode 100644
index 000000..8fa3d2
--- /dev/null
+++ b/src/payments/stripe_webhook.py
@@ -0,0 +1,15 @@
+import hmac
+import hashlib
+
+def verify_stripe_signature(payload: str, sig_header: str, secret: str) -> bool:
+    computed = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
+    return hmac.compare_digest(computed, sig_header)
"""


def test_full_accessible_developer_journey():
    session_id = "sess_e2e_001"
    user_id = "user_blind_engineer"
    repo = "payment-gateway"

    # 1. Ask for a spoken summary of the incoming patch.
    turn_1 = client.post("/api/voice_turn", json={
        "session_id": session_id, "user_id": user_id, "repository": repo,
        "intent": "summarize_diff", "params": {"raw_diff": PR_DIFF, "level": 0},
    })
    assert turn_1.status_code == 200
    res_1 = turn_1.json()
    assert "Modified 1 file with" in res_1["spoken_text"]
    assert "1 files" not in res_1["spoken_text"], "spoken text must be pluralised for a listener"
    # This patch adds HMAC signature verification, so the parser categorises it
    # SECURITY_SENSITIVE. The cue has to say so before the sentence does: this
    # assertion used to read DIFF_READY, which passed against a build where
    # every digest returned the same cue and the security verdict never
    # reached the ear. The stricter form fails against that build.
    assert res_1["earcon_type"] == "SECURITY_FINDING"
    assert res_1["critical_findings"], "a security-sensitive patch must name its finding"
    assert res_1["synthesis_mode"] in {"heuristic-local", "bedrock"}

    # 2. Drill into the one changed file.
    drill = client.post("/api/drill_down_section", json={"raw_diff": PR_DIFF, "section_index": 0})
    assert drill.status_code == 200
    res_drill = drill.json()
    assert "stripe_webhook.py" in res_drill["spoken_text"]
    assert {"crypto", "auth_token"} & set(res_drill["security_flags"])

    # 3. The agent stages a command. Staging returns the grant that can release it.
    stage = client.post("/api/voice_turn", json={
        "session_id": session_id, "user_id": user_id, "repository": repo,
        "intent": "stage_action",
        "params": {
            "action_id": "act_run_tests_44",
            "action_type": "RUN_TESTS",
            "command": "pytest tests/unit",
            "summary_spoken": "Run the unit test suite before release",
        },
    })
    assert stage.status_code == 200
    res_stage = stage.json()
    assert res_stage["earcon_type"] == "GOVERNANCE_CHALLENGE"
    assert res_stage["state"] == "PENDING_APPROVAL"
    grant = res_stage["approval_grant"]
    assert grant.startswith("v1.")

    # 4. A human releases it with the grant. The command is planned, not run.
    confirm = client.post("/api/voice_turn", json={
        "session_id": session_id, "user_id": user_id, "repository": repo,
        "intent": "approve_action",
        "params": {
            "action_id": "act_run_tests_44",
            "approval_grant": grant,
            "approver_id": "user_blind_engineer",
        },
    })
    assert confirm.status_code == 200
    res_confirm = confirm.json()
    assert res_confirm["status"] == "PLANNED"
    assert res_confirm["earcon_type"] == "ACTION_COMMITTED"
    assert "nothing was executed" in res_confirm["output"]
    assert "pytest tests/unit" in res_confirm["output"]

    # 5. The audit trail records who staged and who approved.
    audit = client.get("/api/audit_log")
    assert audit.status_code == 200
    record = next(r for r in audit.json()["records"] if r["action"] == "act_run_tests_44")
    assert record["staged_by"] == "volcan-agent"
    assert record["approved_by"] == "user_blind_engineer"


def test_journey_refuses_a_command_outside_the_allowlist():
    stage = client.post("/api/stage_governed_action", json={
        "action_id": "act_forbidden_1",
        "action_type": "DEPLOY_PROD",
        "command": "aws ecs update-service --cluster prod --service payments",
        "summary_spoken": "Deploy payments service to production",
    })
    assert stage.status_code == 200
    body = stage.json()
    assert body["plan"]["allowed"] is False
    assert body["plan"]["executed"] is False
    assert "not an allowlisted executable" in body["plan"]["refusal_reason"]

    confirm = client.post("/api/confirm_action", json={
        "action_id": "act_forbidden_1",
        "approval_grant": body["approval_grant"],
        "approver_id": "reviewer",
    })
    assert confirm.status_code == 200
    result = confirm.json()
    # Custody is satisfied, so the release is approved; the planner still refuses.
    assert result["approved"] is True
    assert "Refused" in result["output"]
    assert "nothing was executed" in result["output"]
