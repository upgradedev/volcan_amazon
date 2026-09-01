# Volcan: Official Devpost Submission Text

---

## Short Tagline (under 25 words)
Volcan empowers blind and mobility-impaired software developers to orchestrate autonomous AI coding agents through semantic diff sonification and governed voice dialogs on Amazon Alexa+.

---

## 1. Inspiration & Problem (The Human Story)

Autonomous AI coding agents (Claude, Codex, Antigravity) promise to democratize software engineering. However, their interfaces rely entirely on high-speed streaming text, complex multi-panel IDE layouts, and visual side-by-side git diffs.

For software engineers who are blind, visually impaired, quadriplegic, or living with severe repetitive strain injury (RSI), these visual interfaces represent an impossible barrier. Traditional screen readers choke on streaming ANSI terminal escape sequences and raw patch syntax (`+`, `-`, `@@ -1,4 +1,7 @@`). A 300-line code patch takes over 15 minutes of exhausting auditory scrubbing to review.

We drew inspiration from **Hephaestus (Vulcan)**, the sole disabled god of the classical pantheon, who built autonomous golden handmaidens to assist his forge. **Volcan** is the modern forge for disabled developers.

---

## 2. What it Does

Volcan introduces an accessible, voice-first intelligence layer between the developer and AI coding agents:
1. **Semantic Diff Sonification:** Converts complex git diffs into concise hierarchical spoken digests (Level 0: Executive summary, Level 1: File impact, Level 2: Line & symbol drill-down) paired with harmonic acoustic earcons (PCM WAV waveforms).
2. **Deterministic Security Scanning:** Scans diffs at the AST level for authentication, cryptographic, or database changes and announces critical alerts before deployment.
3. **Dual-Custody Governed Execution:** Implements a time-leased, cryptographically signed SHA-256 voice authorization protocol for terminal and deployment actions.
4. **FastMCP Streamable HTTP Server:** Built to the open Model Context Protocol (Spec 2025-11-25+), connecting Amazon Alexa+ directly to local coding workspaces.

---

## 3. How We Built It

Volcan is engineered with strict Domain-Driven Design (DDD) and Clean Hexagonal Architecture:
* **Core Domain:** Pure Python AST parsing (`UnifiedDiffParser`), acoustic earcon synthesis (`WaveformSynthesizer`), and lease-based action governance (`GovernedAction`).
* **AI & Cloud:** **Amazon Bedrock (Claude 3.5 Sonnet & Nova)** for variance reasoning and natural language distillation.
* **Voice Transport:** **Streamable HTTP FastMCP Server** on FastAPI/Uvicorn, exposing MCP tools (`digest_semantic_diff`, `stage_governed_action`, `confirm_action`, `drill_down_section`, `play_earcon`).
* **Multi-Modal UI:** Interactive single-page web companion for zero-setup judge testing and Alexa Presentation Language (APL) card layouts for Echo Show devices.

---

## 4. Headline Result

* **Sub-Millisecond AST Diff Synthesis & Security Flagging:** Deterministic AST patch parsing and category extraction executed in < 1.0 ms with automated security flagging and pure PCM harmonic earcon cues.

---

## 5. Track & Mini-Challenge Declarations

* **Primary Track:** **Alexa+ Track** (Self-hosted FastMCP Server over Streamable HTTP, spec 2025-11-25+).
* **Mini Challenge 1:** **AWS Builder** (Amazon Bedrock multimodal synthesis, IAM least-privilege policies, CloudWatch audit logs).
* **Mini Challenge 2:** **Open Source** (Public GitHub repository with detectable MIT License, full documentation, and reproducible test suite).

---

## 6. Mandatory Product Feedback

* **Developer Tools Used:** Amazon Alexa+, Model Context Protocol (Streamable HTTP), Amazon Bedrock (`anthropic.claude-3-5-sonnet-20241022-v2:0`), FastAPI.
* **What Worked Well:** The open MCP standard provides a clean, decoupled tool-orchestration surface. Amazon Bedrock's API performance and structured JSON outputs were exceptionally reliable.
* **What Needs Work:** Native MCP primitives for streaming inline binary audio earcons alongside JSON RPC payloads would reduce Base64 encoding overhead on rapid voice dialogs.
* **Onboarding Experience:** Smooth and rapid (under 15 minutes from zero to running test suite).
* **Would You Build With These Tools Again:** Yes, absolutely. Voice-first MCP agents represent the universal future of accessible developer tooling.
