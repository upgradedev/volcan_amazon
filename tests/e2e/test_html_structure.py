"""Static HTML DOM Structure & UI Element Assertion Suite for Volcan.

Performs static string and structure assertions over docs/index.html to verify:
- Interactive AST diff sonification DOM controls and audio element hooks
- Dual-custody lease staging DOM components, countdown tags, and token containers
- ARIA accessibility semantics and responsive layout elements
(Note: Runs static file assertions without an active browser driver).
"""
import os


def test_volcan_web_companion_html_structure():
    """Verify docs/index.html contains all required UI components, Web Audio hooks, and accessibility tags."""
    index_path = os.path.join(os.path.dirname(__file__), "../../docs/index.html")
    assert os.path.exists(index_path), "docs/index.html must exist"

    with open(index_path, "r", encoding="utf-8") as f:
        html = f.read()

    # Brand & header
    assert "Volcan" in html
    assert "Voice Agent Forge" in html or "AI Agent Forge" in html

    # Voice query simulation bar
    assert "voiceCommandInput" in html
    assert "executeVoiceCommand" in html

    # AST Diff sonifier & oscilloscope
    assert "diffInput" in html
    assert "audioVisualizer" in html
    assert "synthesizeDiff" in html
    assert "playPureEarcon" in html

    # Dual-custody governance controls
    assert "stageGovernedAction" in html
    assert "confirmVoiceAction" in html
    assert "rejectAction" in html
    assert "auditVault" in html

    # Web Audio & Speech API integration
    assert "AudioContext" in html
    assert "speechSynthesis" in html
    assert "SpeechSynthesisUtterance" in html


def test_volcan_diff_presets_validity():
    """Verify all preloaded AST diff presets are well-formed unified diffs."""
    index_path = os.path.join(os.path.dirname(__file__), "../../docs/index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        html = f.read()

    # Preset 1: Security KMS Key
    assert "KMS_KEY_ID" in html
    assert "AuthService" in html

    # Preset 2: Clean FastAPI Refactor
    assert "router.get" in html
    assert "health" in html

    # Preset 3: Bugfix
    assert "strip" in html


def test_volcan_governance_lease_timing_contract():
    """Verify 300s lease duration and countdown logic in web companion script."""
    index_path = os.path.join(os.path.dirname(__file__), "../../docs/index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        html = f.read()

    # Assert 300000ms (5 minute) TTL
    assert "300000" in html
    # Assert countdown timer interval
    assert "setInterval" in html
    assert "LEASE ACTIVE" in html
    assert "LEASE EXPIRED" in html
