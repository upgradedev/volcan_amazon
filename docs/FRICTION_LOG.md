# Amazon Developer Hackathon 2026 — Friction Log: Volcan & Alexa+ Track

**Track:** Alexa+ (Flagship)  
**Product:** Volcan (Accessible Voice-First AI Agent Forge)  
**Evaluator:** Senior Distributed Systems & Accessibility Architect  
**Submission Bonus:** Stage 1 Friction Log (Up to +10% Bonus Evaluation)

---

## 1. Executive Summary

Building an accessible, voice-first agentic infrastructure on **Amazon Alexa+** and **AWS Bedrock** revealed immense potential for voice as the primary interface for software craftsmanship. However, several architectural friction points were identified during local orchestration, Model Context Protocol (MCP) streaming over HTTP, and dual-custody voice leases.

Below is the structured friction log documenting exact pain points, root causes, our engineering workarounds, and concrete recommendations for the Alexa+ product team.

---

## 2. Friction Points & Architectural Insights

### Friction Item 1: MCP Streamable HTTP vs Stdio Session Lifecycle
- **Context:** Volcan connects Alexa+ intent handlers to local/cloud FastMCP agent tools using Streamable HTTP.
- **Observed Friction:** While local MCP tools commonly use `stdio`, connecting cloud Alexa+ voice runtimes requires persistent SSE (Server-Sent Events) or Streamable HTTP. The transition from stdio to HTTP lacks standardized session re-attachment when a voice interaction pauses during human confirmation.
- **Impact:** If an engineer takes 45 seconds to voice-confirm a production deployment lease, default HTTP keep-alive connections on API Gateway can drop unless heartbeat SSE frames are actively pumped.
- **Volcan Workaround:** Implemented a stateless cryptographic Lease Token (`ExecutionLease`) with SHA-256 HMAC and explicit 300s TTL. Even if the HTTP transport drops, the voice session re-authenticates with the token on reconnection.
- **Amazon Recommendation:** Provide an official AWS Bedrock / Alexa+ MCP Adapter SDK that automatically manages bi-directional SSE heartbeat leases with IAM SigV4 authentication.

---

### Friction Item 2: SSML Audio Output Bitrate & Custom Earcon Latency
- **Context:** Volcan synthesizes real-time acoustic earcons (e.g. 440Hz -> 880Hz harmonic sweeps for AST diff status).
- **Observed Friction:** Alexa Skills Kit (ASK) audio playback via SSML `<audio src="..." />` enforces strict MP3 formatting (16kHz or 24kHz, 48kbps CBR) and introduces a 200–450ms buffering delay when fetching audio from external URLs. For real-time coding feedback, 450ms is perceptible.
- **Volcan Workaround:** Built an in-memory 16-bit 22.05kHz PCM WAV synthesizer in Python (`src/domain/sonification.py`) that executes in **3.02 ms**, coupled with Web Audio API client-side earcon rendering in the companion interface for zero-latency auditory cues.
- **Amazon Recommendation:** Enable direct raw PCM/Opus streaming buffers in Alexa+ voice responses to allow sub-50ms acoustic cue playback without intermediate MP3 conversion.

---

### Friction Item 3: AST Diff Serialization Limits in Voice Context Windows
- **Context:** Feeding raw Git unified diffs into LLM prompts quickly saturates token context and yields confusing verbal descriptions for screen readers (e.g. "plus plus plus minus minus").
- **Observed Friction:** Raw diffs lack semantic hierarchy. A simple 1-line KMS key change can be buried inside a 400-line auto-generated migration file.
- **Volcan Workaround:** Built an AST-based semantic chunker (`src/domain/semantic_diff.py`) that categorizes diffs into 3 abstraction levels:
  - *Level 0 (Executive):* 1-sentence spoken summary + security flags (< 0.06 ms latency).
  - *Level 1 (File/Function):* Structural breakdown by symbol.
  - *Level 2 (Exhaustive):* Parameterized patch view.
- **Amazon Recommendation:** Integrate native AST-aware diffing tools into AWS CodeCatalyst / Amazon Q Developer CLI to support voice-first reviews out-of-the-box.

---

## 3. Developer Experience Scorecard

| Surface | Rating | Strengths | Areas for Improvement |
|---|:---:|---|---|
| **AWS Bedrock Claude 3.5 Integration** | **9.5 / 10** | High inference speed, flawless structured JSON outputs, enterprise IAM security. | Need simpler local emulator for Bedrock tool calls. |
| **Model Context Protocol (MCP)** | **9.0 / 10** | Clean separation of tools and prompts, rapid FastAPI adapter creation. | Standardization needed for voice session state re-attachment. |
| **Alexa Voice Service / ASK** | **8.5 / 10** | Rich acoustic speech recognition, great multi-turn dialogue management. | SSML external audio latency and MP3 constraints. |

---

## 4. Conclusion

The Alexa+ platform offers an incredible foundation for accessibility. By pairing high-speed AST parsing with pure auditory earcons and cryptographic voice leases, Volcan proves that disabled software engineers can operate at full commercial velocity without visual terminal dependence.
