# 🧪 End-to-End User Acceptance Testing (UAT) Testbook
## Project: Volcan — Accessible Voice-First AI Agent Forge on Alexa+

---

## 🎯 Target Persona
* **Persona:** Blind and mobility-impaired software developers (e.g. Maria, Senior Backend Engineer with severe visual impairment).
* **Hardware Setup:** Echo Show 10 (Voice Input) + Refreshable 40-cell Braille Terminal (`U+2800`).

---

## 📋 UAT Test Scenario Matrix

| Test ID | Scenario Description | Preconditions | Action Steps | Expected Outcome | Automated Test Mapping |
|:---:|---|---|---|---|---|
| **UAT-VOL-01** | **Voice Code Synthesis via Natural Language** | Echo Show active, microphone connected | 1. User says *"Alexa, ask Volcan Forge to create a binary search function in Python"*. | • HTTP 200 OK from `/mcp/tools/synthesize`.<br>• Synthesizes valid AST tree.<br>• Generates clean Python code. | `tests/unit/test_synthesizer.py`<br>`test_alexa_integration.py` |
| **UAT-VOL-02** | **Tactile Braille U+2800 Stream Translation** | Braille display connected via USB/Bluetooth | 1. Invoke `translate_to_braille` with code snippet.<br>2. Inspect Unicode byte stream. | • Returns 6-dot Braille characters (`⠠⠁⠇⠑⠭`).<br>• Preserves indentation blocks tactually. | `tests/unit/test_braille_translator.py`<br>`test_lsp_bridge.py` |
| **UAT-VOL-03** | **AST Safety & Syntax Mutation Analysis** | Invalid syntax prompt submitted | 1. Submit incomplete code chunk.<br>2. Trigger AST analyzer. | • Identifies exact line & column error.<br>• Voice guidance gives actionable fix advice without reading 100 lines. | `tests/unit/test_ast_analyzer.py` |
| **UAT-VOL-04** | **AWS Strands Multi-Turn Code Repair** | Broken code requiring iterative fix | 1. Request refactoring with Strands Agent.<br>2. Verify Bedrock tool dispatch. | • Strands Agent routes tool call.<br>• Corrects logic error in <150ms. | `tests/unit/test_strands_agent.py` |
| **UAT-VOL-05** | **Sub-200ms Voice Latency & Zero Error Rate** | 50 concurrent requests | 1. Execute load test harness. | • P95 latency <25ms.<br>• 0.00% error rate. | `tests/performance/test_load_and_latency.py` |

---

## 🛡️ CI/CD Verification
All scenarios above are automated and executed on every push via `.github/workflows/ci.yml`.
