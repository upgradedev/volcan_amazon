"""Security DAST & Parameterized Offset Tests for Volcan."""
import pytest
from fastapi.testclient import TestClient
from src.interfaces.mcp_server import app


client = TestClient(app)


# --- C4: DAST / Malicious Payload Handling ---

def test_dast_malicious_script_injection_in_diff():
    malicious_diff = """diff --git a/app.py b/app.py
+ <script>alert('XSS')</script>
+ eval("import os; os.system('rm -rf /')")
+ DROP TABLE users;
"""
    res = client.post("/mcp/tools/digest_semantic_diff", json={"raw_diff": malicious_diff, "level": 0})
    assert res.status_code == 200
    data = res.json()
    assert "voice_summary" in data
    # Security scanner should flag the exec_call and db_mutation
    assert any("exec_call" in f or "db_mutation" in f for f in data["critical_findings"])


def test_dast_invalid_action_confirmation_rejected():
    res = client.post("/mcp/tools/confirm_action", json={
        "action_id": "non_existent_action_999",
        "voice_token": "FAKE_TOKEN"
    })
    assert res.status_code == 400


def test_dast_invalid_earcon_type():
    res = client.post("/mcp/tools/play_earcon", json={"earcon_type": "MALICIOUS_EARCON_TYPE"})
    assert res.status_code == 400


# --- C6: Parameterized Offset Fixtures ---

@pytest.mark.parametrize("section_offset", [0, 1, 2])
def test_offset_section_drill_down(section_offset):
    multi_diff = """diff --git a/file1.py b/file1.py
+ a = 1
diff --git a/file2.py b/file2.py
+ b = 2
diff --git a/file3.py b/file3.py
+ c = 3
"""
    res = client.post("/mcp/tools/drill_down_section", json={
        "raw_diff": multi_diff,
        "section_index": section_offset
    })
    assert res.status_code == 200
    data = res.json()
    expected_file = f"file{section_offset + 1}.py"
    assert expected_file in data["file_path"]


@pytest.mark.parametrize("lease_duration", [1.0, 50.0, 300.0, 600.0])
def test_parameterized_lease_durations(lease_duration):
    action_id = f"act_lease_{int(lease_duration)}"
    res = client.post("/mcp/tools/stage_governed_action", json={
        "action_id": action_id,
        "action_type": "DEPLOY",
        "command": "deploy staging",
        "summary_spoken": "Deploy to staging",
        "lease_sec": lease_duration
    })
    assert res.status_code == 200
    assert res.json()["state"] == "PENDING_APPROVAL"
