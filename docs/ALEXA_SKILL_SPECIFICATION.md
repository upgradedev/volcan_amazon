# Volcan: Alexa+ Skill & Multi-Modal Interaction Specification

> **Transport:** Streamable HTTP over Model Context Protocol (MCP Spec 2025-11-25+)  
> **Supported Devices:** Echo Show, Echo Dot, Fire TV, Alexa Desktop Companion, Accessible Terminal  

---

## 1. Intent Schema & Sample Utterances

### Intent: `SummarizeDiffIntent`
* *Utterances:*
  * "Alexa, ask Volcan to summarize my workspace changes."
  * "Alexa, ask Volcan what code was modified."
  * "Alexa, ask Volcan for a high-level review of the pull request."
* *Response:* Spoken executive digest + Audio Earcon (`DIFF_READY`) + APL Card with line metrics.

### Intent: `DrillDownIntent`
* *Slots:* `FileIndex` (Number), `FileName` (String)
* *Utterances:*
  * "Alexa, ask Volcan to inspect section one."
  * "Alexa, ask Volcan to explain changes in auth.py."
* *Response:* Symbol-level explanation + Security flags + Audio Earcon (`DRILL_DOWN_OPENED`).

### Intent: `StageActionIntent`
* *Slots:* `ActionCommand` (String), `ActionSummary` (String)
* *Utterances:*
  * "Alexa, tell Volcan to stage a deployment to staging."
  * "Alexa, tell Volcan to stage running unit tests."
* *Response:* Spoken confirmation prompt + Audio Earcon (`GOVERNANCE_CHALLENGE`) + SHA-256 payload hash lock.

### Intent: `ApproveActionIntent`
* *Slots:* `VoiceToken` (String)
* *Utterances:*
  * "Alexa, tell Volcan to confirm action."
  * "Alexa, tell Volcan to approve with voice signature."
* *Response:* Execution confirmation + Output summary + Audio Earcon (`ACTION_COMMITTED`).

---

## 2. Alexa Presentation Language (APL) Visual Card Layout

```json
{
  "type": "APL",
  "version": "2024.1",
  "mainTemplate": {
    "parameters": ["payload"],
    "items": [
      {
        "type": "Container",
        "width": "100%",
        "height": "100%",
        "direction": "column",
        "padding": "24dp",
        "items": [
          {
            "type": "Text",
            "text": "${payload.cardTitle}",
            "style": "header",
            "fontSize": "32dp",
            "color": "#FF9900"
          },
          {
            "type": "Text",
            "text": "${payload.voiceSummary}",
            "style": "body",
            "fontSize": "22dp",
            "spacing": "16dp"
          },
          {
            "type": "Text",
            "text": "${payload.metrics}",
            "style": "detail",
            "fontSize": "18dp",
            "color": "#888888",
            "spacing": "12dp"
          }
        ]
      }
    ]
  }
}
```
