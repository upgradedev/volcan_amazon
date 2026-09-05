"""Security (DAST-style) and parameterized offset tests for the REST surface."""
import pytest
from fastapi.testclient import TestClient

from src.interfaces.mcp_server import app

client = TestClient(app)


# --- C4: malicious payload handling ---

def test_dast_malicious_script_injection_in_diff():
    malicious_diff = """diff --git a/app.py b/app.py
+ <script>alert('XSS')</script>
+ eval("import os; os.system('rm -rf /')")
+ DROP TABLE users;
"""
    res = client.post("/api/digest_semantic_diff", json={"raw_diff": malicious_diff, "level": 0})
    assert res.status_code == 200
    data = res.json()
    assert "voice_summary" in data
    assert any("exec_call" in f or "db_mutation" in f for f in data["critical_findings"])


def test_dast_confirmation_of_an_unknown_action_is_refused():
    res = client.post("/api/confirm_action", json={
        "action_id": "non_existent_action_999",
        "approval_grant": "v1.forged.forged",
        "approver_id": "attacker",
    })
    assert res.status_code == 200
    body = res.json()
    assert body["approved"] is False
    assert body["refusal_code"] == "UNKNOWN_ACTION"


def test_dast_forged_grant_on_a_real_action_is_refused():
    stage = client.post("/api/stage_governed_action", json={
        "action_id": "act_dast_forged",
        "action_type": "RUN_TESTS",
        "command": "pytest tests/unit",
        "summary_spoken": "Run tests",
    })
    grant = stage.json()["approval_grant"]
    # Flip one character of the signature segment.
    version, body, signature = grant.split(".")
    tampered_char = "A" if signature[0] != "A" else "B"
    forged = f"{version}.{body}.{tampered_char}{signature[1:]}"

    res = client.post("/api/confirm_action", json={
        "action_id": "act_dast_forged",
        "approval_grant": forged,
        "approver_id": "attacker",
    })
    assert res.json()["approved"] is False
    assert res.json()["refusal_code"] == "BAD_SIGNATURE"


def test_dast_invalid_earcon_type():
    res = client.post("/api/play_earcon", json={"earcon_type": "MALICIOUS_EARCON_TYPE"})
    assert res.status_code == 400


def test_dast_shell_metacharacters_are_refused_by_the_planner():
    stage = client.post("/api/stage_governed_action", json={
        "action_id": "act_dast_shell",
        "action_type": "TERMINAL_COMMAND",
        "command": "git status; rm -rf /",
        "summary_spoken": "Check status",
    })
    plan = stage.json()["plan"]
    assert plan["allowed"] is False
    assert plan["executed"] is False
    assert "metacharacter" in plan["refusal_reason"]


# --- C6: parameterized offset fixtures ---

@pytest.mark.parametrize("section_offset", [0, 1, 2])
def test_offset_section_drill_down(section_offset):
    multi_diff = """diff --git a/file1.py b/file1.py
+ a = 1
diff --git a/file2.py b/file2.py
+ b = 2
diff --git a/file3.py b/file3.py
+ c = 3
"""
    res = client.post("/api/drill_down_section", json={
        "raw_diff": multi_diff, "section_index": section_offset,
    })
    assert res.status_code == 200
    assert f"file{section_offset + 1}.py" in res.json()["file_path"]


@pytest.mark.parametrize("lease_duration", [1.0, 50.0, 300.0, 600.0])
def test_parameterized_lease_durations(lease_duration):
    res = client.post("/api/stage_governed_action", json={
        "action_id": f"act_lease_{int(lease_duration)}",
        "action_type": "RUN_TESTS",
        "command": "pytest tests/unit",
        "summary_spoken": "Run the unit suite",
        "lease_sec": lease_duration,
    })
    assert res.status_code == 200
    body = res.json()
    assert body["state"] == "PENDING_APPROVAL"
    assert body["lease_sec"] == lease_duration
    assert body["expires_at_epoch"] > 0
