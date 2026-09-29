"""The whole app in durable mode, with every AWS call answered by a fake.

This is the Phase 2 configuration: VOLCAN_STATE_TABLE, a Secrets Manager
approval secret and VOLCAN_MCP_SESSION_MODE=stateless, with no reviewer
roster. The child process is cut off from real AWS (no keys, no profile, no
instance metadata), and boto3's constructors are replaced before the app is
imported, so a code path the fakes do not cover fails instead of reaching an
account. A judge with no credential must still get the whole public journey,
and no response may carry the secret, its ARN or the table name.
"""
import secrets
import sys

import httpx

from tests.fixtures.live_server import run_script, running_server

TABLE = "volcan-e2e-fake-state"
ARN = "arn:aws:secretsmanager:eu-west-1:000000000000:secret:volcan-e2e-fake"


def _durable_env(secret_string: str) -> dict[str, str]:
    env = {
        "VOLCAN_STATE_TABLE": TABLE,
        "VOLCAN_APPROVAL_SECRET_ARN": ARN,
        "VOLCAN_FAKE_SECRET_STRING": secret_string,
        "VOLCAN_MCP_SESSION_MODE": "stateless",
        "VOLCAN_REVIEWERS": "",
        "VOLCAN_APPROVAL_SECRET": "",
        "AWS_REGION": "eu-west-1",
        "AWS_EC2_METADATA_DISABLED": "true",
        "AWS_CONFIG_FILE": "nonexistent-aws-config",
        "AWS_SHARED_CREDENTIALS_FILE": "nonexistent-aws-credentials",
        "AWS_ACCESS_KEY_ID": "",
        "AWS_SECRET_ACCESS_KEY": "",
        "AWS_SESSION_TOKEN": "",
        "AWS_PROFILE": "",
        "AWS_DEFAULT_PROFILE": "",
    }
    return env


def test_an_anonymous_judge_gets_the_whole_journey_from_a_durable_server():
    secret_string = secrets.token_urlsafe(48)
    launcher = [sys.executable, "tests/fixtures/durable_server.py"]
    with running_server(_durable_env(secret_string), launcher=launcher) as base_url:
        client = httpx.Client(base_url=base_url, timeout=30)
        seen: list[str] = []

        def get(path):
            response = client.get(path)
            seen.append(response.text)
            return response

        def post(path, body):
            response = client.post(path, json=body)
            seen.append(response.text)
            return response

        health = get("/health").json()
        assert health["durable_state"]["backend"] == "dynamodb"
        assert health["durable_state"]["resolved_capability"] == "configured_reachable"
        assert health["durable_state"]["approval_secret_source"] == "secrets_manager"
        assert health["mcp"]["session_mode"] == "stateless"

        audit = get("/api/audit_log")
        assert audit.status_code == 200, audit.text
        assert audit.json()["view"] == "public"

        conformance = run_script(
            "scripts/mcp_conformance.py", f"{base_url}/mcp", "--expect-mode", "stateless",
        )
        assert conformance.returncode == 0, conformance.stdout + conformance.stderr

        journey = run_script("tests/e2e/durable_journey_runner.py", base_url)
        assert journey.returncode == 0, journey.stdout + journey.stderr

        audit = get("/api/audit_log").json()
        assert [row["command"] for row in audit["records"]] == ["git diff HEAD"]
        assert audit["records"][0]["state"] == "RELEASED_NOT_RUN"

        turn = {"session_id": "e2e-voice", "user_id": "judge", "repository": "octo/demo"}
        staged = post("/api/voice_turn", {**turn, "intent": "stage_action", "params": {
            "action_id": "act_777", "command": "git diff HEAD", "summary_spoken": "diff",
        }})
        assert staged.status_code == 200, staged.text
        approved = post("/api/voice_turn", {**turn, "intent": "approve_action", "params": {
            "approval_grant": staged.json()["approval_grant"],
        }})
        assert approved.json()["status"] == "RELEASED_NOT_RUN", approved.text

        review = post("/api/review/turn", {
            "session_id": "e2e-review", "user_id": "judge", "transcript": "open",
            "raw_diff": "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n",
        })
        assert review.status_code == 200, review.text

        seen.append(get("/").text)
        for text in seen:
            assert secret_string not in text
            assert ARN not in text and "secret:volcan" not in text
            assert TABLE not in text
