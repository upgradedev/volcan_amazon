# E2E UAT Testbook — Volcan (Accessible Voice-First AI Agent Forge)

## Test Persona: Alex (Disabled Senior Developer using Voice & Braille Display)

### 📋 Scenario 1: Voice Code Generation & Unicode Braille (U+2800) Feedback
* **Precondition:** Volcan FastMCP server is active.
* **Step 1 (Input):** User speaks: `"Volcan, create an accessible counter component in Python"`.
* **Step 2 (Execution):** Volcan processes AST, generates accessible Python code.
* **Step 3 (Verification):** Volcan translates AST diff to 6-dot Braille Unicode (`⠠⠁⠇⠑⠭`).
* **Expected Result:** HTTP 200, Braille string returned with zero visual dependency.
* **Verification Command:** `pytest tests/unit/test_braille_translator.py -v`

### 📋 Scenario 2: AST Mutation & Security Guardrail
* **Precondition:** Volcan AST parser initialized.
* **Step 1 (Input):** User voice command attempts unsafe eval (`"eval(__import__('os').system('rm -rf /'))"`).
* **Step 2 (Execution):** Security AST filter intercepts command.
* **Expected Result:** Command blocked with SecurityAuditException.
* **Verification Command:** `pytest tests/integration/test_security_audit.py -v`
