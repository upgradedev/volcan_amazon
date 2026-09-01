"""End-to-End User Journey Test: Visually Impaired Developer Workflow."""
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
    """Simulate a blind developer using Alexa+ voice to review a PR and authorize deployment."""
    session_id = "sess_e2e_001"
    user_id = "user_blind_engineer"
    repo = "payment-gateway"

    # Step 1: Developer asks Alexa to summarize the incoming pull request
    turn_1 = client.post("/mcp/tools/voice_turn", json={
        "session_id": session_id,
        "user_id": user_id,
        "repository": repo,
        "intent": "summarize_diff",
        "params": {"raw_diff": PR_DIFF, "level": 0}
    })
    assert turn_1.status_code == 200
    res_1 = turn_1.json()
    assert "Modified 1 files" in res_1["spoken_text"]
    assert res_1["earcon_type"] == "DIFF_READY"

    # Step 2: Developer drills down into section 0
    drill_turn = client.post("/mcp/tools/drill_down_section", json={
        "raw_diff": PR_DIFF,
        "section_index": 0
    })
    assert drill_turn.status_code == 200
    res_drill = drill_turn.json()
    assert "stripe_webhook.py" in res_drill["spoken_text"]
    assert "crypto" in res_drill["security_flags"] or "auth_token" in res_drill["security_flags"]

    # Step 3: Developer asks agent to stage production deployment
    stage_turn = client.post("/mcp/tools/voice_turn", json={
        "session_id": session_id,
        "user_id": user_id,
        "repository": repo,
        "intent": "stage_action",
        "params": {
            "action_id": "act_deploy_prod_44",
            "action_type": "DEPLOY_PROD",
            "command": "aws ecs update-service --cluster prod --service payments",
            "summary_spoken": "Deploy payments service to production ECS cluster"
        }
    })
    assert stage_turn.status_code == 200
    res_stage = stage_turn.json()
    assert res_stage["earcon_type"] == "GOVERNANCE_CHALLENGE"
    assert res_stage["state"] == "PENDING_APPROVAL"

    # Step 4: Developer speaks confirmation voice token
    confirm_turn = client.post("/mcp/tools/voice_turn", json={
        "session_id": session_id,
        "user_id": user_id,
        "repository": repo,
        "intent": "approve_action",
        "params": {
            "action_id": "act_deploy_prod_44",
            "voice_token": "TOKEN_ALEXA_VOICE_VERIFIED_772"
        }
    })
    assert confirm_turn.status_code == 200
    res_confirm = confirm_turn.json()
    assert res_confirm["status"] == "EXECUTED"
    assert res_confirm["earcon_type"] == "ACTION_COMMITTED"
