"""Web Companion HTML and Static Assets for Zero-Setup Judge Testing."""

COMPANION_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Volcan: Accessible AI Agent Forge</title>
  <style>
    :root {
      --bg: #0f172a;
      --card-bg: #1e293b;
      --accent: #f97316;
      --accent-hover: #ea580c;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --border: #334155;
      --success: #22c55e;
      --danger: #ef4444;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    body { background: var(--bg); color: var(--text); padding: 20px; line-height: 1.5; }
    .container { max-width: 1100px; margin: 0 auto; }
    header { border-bottom: 1px solid var(--border); padding-bottom: 15px; margin-bottom: 25px; display: flex; justify-content: space-between; align-items: center; }
    h1 { font-size: 1.8rem; color: var(--accent); }
    .badge { background: #334155; padding: 4px 10px; border-radius: 999px; font-size: 0.8rem; color: #38bdf8; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
    @media (max-width: 768px) { .grid { grid-template-columns: 1fr; } }
    .card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 8px; padding: 20px; }
    .card h2 { font-size: 1.2rem; margin-bottom: 15px; color: var(--accent); }
    textarea { width: 100%; height: 160px; background: #0f172a; border: 1px solid var(--border); color: #e2e8f0; padding: 10px; border-radius: 6px; font-family: monospace; font-size: 0.85rem; resize: vertical; }
    button { background: var(--accent); color: white; border: none; padding: 10px 18px; border-radius: 6px; cursor: pointer; font-weight: 600; margin-top: 10px; transition: background 0.2s; }
    button:hover { background: var(--accent-hover); }
    .btn-secondary { background: #475569; margin-left: 8px; }
    .btn-secondary:hover { background: #64748b; }
    .output-box { background: #0f172a; border: 1px solid var(--border); border-radius: 6px; padding: 15px; margin-top: 15px; min-height: 120px; font-size: 0.95rem; }
    .earcon-player { display: flex; align-items: center; gap: 10px; margin-top: 10px; padding: 8px 12px; background: #1e293b; border-radius: 6px; border: 1px solid #334155; }
    .status-tag { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: bold; }
    .tag-sec { background: #7f1d1d; color: #fecaca; }
    .tag-biz { background: #1e3a8a; color: #bfdbfe; }
    .audit-log { font-family: monospace; font-size: 0.8rem; color: var(--text-muted); max-height: 180px; overflow-y: auto; }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div>
        <h1>Volcan: Accessible Voice-First Agent Forge</h1>
        <p style="color: var(--text-muted); font-size: 0.9rem;">Model Context Protocol (MCP) on Streamable HTTP & Amazon Alexa+</p>
      </div>
      <span class="badge">Spec 2025-11-25+</span>
    </header>

    <div class="grid">
      <!-- Panel 1: Semantic Diff Sonification -->
      <div class="card">
        <h2>1. Semantic Diff & Audio Sonification</h2>
        <p style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 10px;">
          Paste a unified git diff patch. Volcan extracts AST changes, detects security flags, and generates spoken digests with harmonic earcons.
        </p>
        <textarea id="diffInput">diff --git a/src/auth/jwt.py b/src/auth/jwt.py
--- a/src/auth/jwt.py
+++ b/src/auth/jwt.py
@@ -1,4 +1,7 @@
-import hashlib
+import hmac
+import hashlib
+def verify_token(token: str, secret: str) -> bool:
+    return hmac.compare_digest(token, secret)</textarea>
        <div>
          <button onclick="digestDiff(0)">Digest Level 0 (Executive)</button>
          <button class="btn-secondary" onclick="digestDiff(1)">Level 1 (Detailed)</button>
        </div>
        <div class="output-box" id="diffOutput">
          <span style="color: var(--text-muted);">Awaiting diff execution...</span>
        </div>
        <div id="audioArea" style="margin-top: 10px;"></div>
      </div>

      <!-- Panel 2: Voice-Governed Actions & Leases -->
      <div class="card">
        <h2>2. Dual-Custody Governed Execution</h2>
        <p style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 10px;">
          Stage irreversible actions with cryptographic SHA-256 hash locks and 300s lease duration. Approve with voice token.
        </p>
        <div>
          <button onclick="stageAction()">Stage Deploy Action</button>
          <button class="btn-secondary" onclick="confirmAction()">Voice Confirm</button>
          <button class="btn-secondary" style="background:#dc2626;" onclick="rejectAction()">Reject</button>
        </div>
        <div class="output-box" id="governanceOutput">
          <span style="color: var(--text-muted);">No staged action currently pending.</span>
        </div>
        
        <h3 style="font-size: 0.95rem; margin-top: 15px; margin-bottom: 8px; color: var(--text-muted);">Immutable Audit Vault:</h3>
        <div class="output-box audit-log" id="auditLog">
          <div>[INIT] Volcan governance ledger active.</div>
        </div>
      </div>
    </div>
  </div>

  <script>
    let currentActionId = null;

    async function digestDiff(level) {
      const rawDiff = document.getElementById('diffInput').value;
      document.getElementById('diffOutput').innerHTML = '<span style="color:#f59e0b;">Synthesizing semantic AST diff...</span>';
      
      try {
        const res = await fetch('/mcp/tools/digest_semantic_diff', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ raw_diff: rawDiff, level: level })
        });
        const data = await res.json();
        
        let html = '<strong>Voice Digest:</strong> ' + data.voice_summary + '<br><br>';
        html += '<strong>Files Changed:</strong> ' + data.total_files + ' (+' + data.insertions + ', -' + data.deletions + ')<br>';
        if (data.critical_findings && data.critical_findings.length > 0) {
          html += '<span class="status-tag tag-sec">Security Alert</span> ' + data.critical_findings.join(', ') + '<br>';
        }
        document.getElementById('diffOutput').innerHTML = html;

        // Play Earcon
        if (data.earcon && data.earcon.wav_base64) {
          playBase64Wav(data.earcon.wav_base64, data.earcon.type);
        }
      } catch (err) {
        document.getElementById('diffOutput').innerHTML = '<span style="color:#ef4444;">Error: ' + err.message + '</span>';
      }
    }

    async function stageAction() {
      currentActionId = 'act_' + Date.now();
      try {
        const res = await fetch('/mcp/tools/stage_governed_action', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            action_id: currentActionId,
            action_type: 'DEPLOY_PROD',
            command: 'aws ecs update-service --cluster prod --service volcan-api',
            summary_spoken: 'Deploy Volcan API service to production cluster',
            lease_sec: 300.0
          })
        });
        const data = await res.json();
        document.getElementById('governanceOutput').innerHTML = 
          '<strong>Staged Action:</strong> ' + data.action_id + '<br>' +
          '<strong>State:</strong> <span class="status-tag tag-biz">' + data.state + '</span><br>' +
          '<strong>Hash:</strong> ' + data.payload_hash.substring(0, 16) + '...<br>' +
          '<strong>Prompt:</strong> ' + data.spoken_prompt;
        
        if (data.earcon && data.earcon.wav_base64) {
          playBase64Wav(data.earcon.wav_base64, data.earcon.type);
        }
        refreshAuditLog();
      } catch (err) {
        document.getElementById('governanceOutput').innerText = 'Error: ' + err.message;
      }
    }

    async function confirmAction() {
      if (!currentActionId) {
        alert('Please stage an action first!');
        return;
      }
      try {
        const res = await fetch('/mcp/tools/confirm_action', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            action_id: currentActionId,
            voice_token: 'VOICE_TOKEN_ALEXA_VERIFIED_' + Math.floor(Math.random() * 9000)
          })
        });
        const data = await res.json();
        document.getElementById('governanceOutput').innerHTML = 
          '<strong>Status:</strong> <span class="status-tag" style="background:#166534; color:#bbf7d0;">' + data.status + '</span><br>' +
          '<strong>Output:</strong> ' + data.output;
        
        if (data.earcon && data.earcon.wav_base64) {
          playBase64Wav(data.earcon.wav_base64, data.earcon.type);
        }
        refreshAuditLog();
        currentActionId = null;
      } catch (err) {
        document.getElementById('governanceOutput').innerText = 'Error: ' + err.message;
      }
    }

    async function rejectAction() {
      if (!currentActionId) return;
      document.getElementById('governanceOutput').innerHTML = '<span style="color:#ef4444;">Action cancelled and rejected by user.</span>';
      currentActionId = null;
    }

    async function refreshAuditLog() {
      try {
        const res = await fetch('/mcp/resources/audit_log');
        const data = await res.json();
        let logHtml = '';
        data.records.forEach(r => {
          logHtml += '<div>[' + r.timestamp.substring(11, 19) + '] ' + r.state + ' | ' + r.action + ' (' + r.payload_hash.substring(0, 8) + ')</div>';
        });
        document.getElementById('auditLog').innerHTML = logHtml || '<div>No audit records yet.</div>';
      } catch (e) {}
    }

    function playBase64Wav(base64Data, label) {
      try {
        const byteCharacters = atob(base64Data);
        const byteNumbers = new Array(byteCharacters.length);
        for (let i = 0; i < byteCharacters.length; i++) {
          byteNumbers[i] = byteCharacters.charCodeAt(i);
        }
        const byteArray = new Uint8Array(byteNumbers);
        const blob = new Blob([byteArray], { type: 'audio/wav' });
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        audio.play().catch(() => {});
        document.getElementById('audioArea').innerHTML = 
          '<div class="earcon-player"><span>Earcon Cue (' + label + ') played</span></div>';
      } catch (err) {}
    }
  </script>
</body>
</html>
"""
