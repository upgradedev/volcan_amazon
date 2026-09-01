# Volcan — Full End-to-End User Acceptance Testing (UAT) Testbook

**Product:** Volcan (Accessible Voice-First AI Agent Forge on Amazon Alexa+ & AWS Bedrock)  
**Version:** 0.1.0  
**Target Persona:** Visually and motor-impaired software engineers  
**Standard:** ISO/IEC 25010 & IEEE 829 Test Documentation

---

## 1. Test Strategy & Acceptance Criteria

| ID | Test Category | Objective | Tool / Automation | Acceptance Criteria |
|---|---|---|---|---|
| **UAT-01** | **AST Diff Sonification** | Verify voice digest & acoustic harmonic cue for pull request changes | FastMCP + Web Audio API | Spoken summary generated in < 100ms with harmonic chord |
| **UAT-02** | **Security Vulnerability Flag** | Verify immediate voice alert when sensitive tokens/keys are modified | AST Chunker + Security Rules | High-priority security earcon (320Hz/640Hz) triggered with verbal warning |
| **UAT-03** | **Dual-Custody Staging** | Verify high-consequence deploy requires SHA-256 lock & 300s lease | Governance Engine | Action staged with immutable hash; unapproved actions expire at 300s |
| **UAT-04** | **Voice Token Authorization** | Verify execution only proceeds with valid Alexa voice authorization token | FastMCP Adapter | Action executes and records immutable audit receipt; invalid tokens rejected |
| **UAT-05** | **Accessibility Ergonomics** | Verify web companion operates with screen readers and speech synthesis | Web Speech API | Full ARIA labeling, zero keyboard traps, native speech output |

---

## 2. Step-by-Step Scenario Test Cases

### Test Case UAT-VOLCAN-001: Standard Refactor AST Sonification
- **Pre-Conditions:** Volcan FastMCP server running (`localhost:8000`), Developer workspace initialized.
- **Action Steps:**
  1. Developer utters: *"Alexa, summarize my workspace diff"*.
  2. Alexa forwards intent to Volcan FastMCP `digest_semantic_diff(level=0)`.
  3. FastMCP parses Git patch AST and generates Level 0 executive summary.
- **Expected Outcome:**
  - Volcan plays harmonic earcon chime (`440Hz -> 880Hz`).
  - Alexa speaks: *"One file modified with two additions. Standard logic update."*
  - FastMCP returns JSON payload containing file diff statistics in `< 1.0 ms`.

### Test Case UAT-VOLCAN-002: Security Flag Detection (KMS Key Alteration)
- **Pre-Conditions:** Pull request modifies `src/auth/service.py` introducing `KMS_KEY_ID` or token validation.
- **Action Steps:**
  1. Developer requests Level 1 AST inspection.
  2. Volcan triggers AST parser rule evaluating security-critical modules.
- **Expected Outcome:**
  - Audio alert earcon triggers (`triangle wave 320Hz/640Hz`).
  - Alexa speaks: *"Security alert: Key Management Service token validation updated."*
  - Badge `Security Flag: KMS Token Audit` illuminates in red.

### Test Case UAT-VOLCAN-003: Governed Production Deploy Lease (Dual Custody)
- **Pre-Conditions:** Agent proposes `aws ecs update-service --cluster prod`.
- **Action Steps:**
  1. Developer utters: *"Alexa, stage deploy to production"*.
  2. Volcan creates `ExecutionLease` with 300s TTL and SHA-256 hash lock.
  3. Lease timer starts countdown from 300 seconds.
- **Expected Outcome:**
  - Status transitions to `LEASE ACTIVE (300s)`.
  - Voice challenge prompt announced: *"Action act_XXXX staged. Awaiting confirmation token."*
  - If 300s elapses without token, status transitions to `LEASE EXPIRED` and action is discarded.

### Test Case UAT-VOLCAN-004: Voice Token Confirmation & Audit Sealing
- **Pre-Conditions:** Action `act_XXXX` is staged in active lease.
- **Action Steps:**
  1. Lead engineer utters: *"Alexa, approve action act_XXXX with token VOICE_TOKEN_ALEXA_AUTH_2026"*.
  2. Volcan validates token signature and executes command.
- **Expected Outcome:**
  - Confirmation chime (`523.25Hz -> 659.25Hz -> 783.99Hz`) plays.
  - Production service updated.
  - Cryptographic block appended to Merkle chain audit vault.

---

## 3. Automated Playwright & Test Execution

Run automated Playwright and E2E test suites with:
```bash
python -m pytest tests/e2e/ -v
python scripts/load_test_suite.py
python scripts/security_audit.py
```
