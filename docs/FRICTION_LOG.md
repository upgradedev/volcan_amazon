# Volcan: Amazon Developer Tools & Alexa+ MCP Friction Log

> **Contest Submission Bonus Requirement:** Detailed developer feedback on tools, APIs, SDKs, onboarding, expected vs. actual results, severity ratings, workarounds, and actionable suggestions. (Up to +10% Stage 2 bonus).

---

## 1. FastMCP & Streamable HTTP Transport Specification (Spec 2025-11-25+)

### Task Attempted
Implement a self-hosted Model Context Protocol (MCP) server over Streamable HTTP to expose accessible developer tools (`digest_semantic_diff`, `stage_governed_action`, `confirm_action`, `play_earcon`) directly to Amazon Alexa+ and agentic coding tools.

### Steps Taken
1. Configured FastAPI application with Streamable HTTP JSON-RPC POST endpoints under `/mcp/tools/*` and `/mcp/resources/*`.
2. Tested streaming chunked responses for audio earcon binary streams and semantic diff summaries.
3. Verified protocol compatibility against Alexa+ Developer Console and local MCP client inspectors.

### Expected vs. Actual Result
* **Expected:** Native schema validation and tool discovery out of the box with standardized error payload schemas.
* **Actual:** Handling bidirectional binary audio streams (`audio/wav`) alongside structured JSON tool responses required custom multipart handling or Base64 envelope wrapping for pure Streamable HTTP transports.

### Severity Rating
* **Medium** (Integration friction).

### Workaround Used
Wrapped audio earcon binary payloads in Base64 string fields inside the JSON tool response (`earcon.wav_base64`), while also maintaining a dedicated `/mcp/tools/play_earcon` endpoint for raw binary audio streaming.

### Actionable Suggestion for Amazon & MCP Core Teams
Introduce standard protocol primitives in the MCP specification for inline binary asset attachments (such as earcon sound waveforms or visual APL layouts) to eliminate Base64 encoding overhead on high-frequency voice turns.

---

## 2. Amazon Bedrock Multimodal Claude 3.5 Sonnet Integration

### Task Attempted
Extract semantic AST-level code changes from unified git patches and generate under-25-word spoken summaries for screen reader users using Amazon Bedrock.

### Steps Taken
1. Integrated `boto3` Bedrock runtime client (`anthropic.claude-3-5-sonnet-20241022-v2:0`).
2. Structured prompt with explicit instructions to avoid markdown formatting, backticks, and raw code syntax that screen readers mispronounce.
3. Implemented a deterministic local regex/AST parser fallback for offline testing.

### Expected vs. Actual Result
* **Expected:** Instant zero-latency responses for small diffs (<50 lines).
* **Actual:** Network round-trip latency to Bedrock ranged from 700ms to 1400ms, which causes perceptible pauses during real-time Alexa voice conversations.

### Severity Rating
* **Minor** (Latency optimization).

### Workaround Used
Implemented a hybrid two-tier pipeline: The deterministic AST parser (`UnifiedDiffParser`) instantly parses file names, security flags, and metrics in <2ms, while Bedrock runs asynchronously to enhance the executive spoken summary.

### Actionable Suggestion for AWS Bedrock Team
Provide edge-cached Bedrock reasoning endpoints or quantized lightweight models (e.g. Amazon Nova Micro / Nano) optimized specifically for ultra-low latency voice-turn interactions.

---

## 3. Product Feedback Questionnaire (Mandatory Hackathon Questions)

### Q1: Which developer tools, APIs, and SDKs did you use and for what?
* **Amazon Alexa+ & MCP Streamable HTTP (Spec 2025-11-25+):** Powers the core conversational and tool-orchestration interface.
* **Amazon Bedrock (Claude 3.5 Sonnet & Nova):** Used for semantic diff synthesis and security risk reasoning.
* **FastAPI & Uvicorn:** Hosts the high-performance asynchronous MCP server.
* **Pure-Python Waveform Synthesizer:** Generates harmonic acoustic earcons (PCM WAV) without binary dependencies.

### Q2: What worked well?
* The open Model Context Protocol (MCP) standard is exceptionally clean and makes connecting Amazon Alexa+ to internal coding engines straightforward.
* Amazon Bedrock's API response consistency and JSON mode output reliability were rock solid.

### Q3: What needs work?
* Documentation on Streamable HTTP transport vs. Server-Sent Events (SSE) in the Alexa+ Preview ecosystem could be more explicit regarding binary audio streaming.
* Emulation tools for testing Alexa Presentation Language (APL) cards locally without cloud console access would speed up developer iteration cycles.

### Q4: How was your onboarding experience (getting from zero to hello world)?
* Exceptional. Setting up the MCP server and testing endpoints locally took under 15 minutes.

### Q5: Would you build with these devices and services again?
* **Yes, absolutely.** The combination of Alexa+ voice agents and MCP open protocols represents the future of accessible, universal computing for developers.
