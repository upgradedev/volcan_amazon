"""The quickstart has to install the path the product is judged on.

Volcan's AI path is the Amazon Bedrock adapter. It lives behind the optional
``bedrock`` extra, and until 2026-09-08 the quickstart installed a hand-listed
set of packages that did not include it. A judge who followed the README
exactly therefore saw ``SYNTHESIS ENGINE: local heuristic`` and
``the Anthropic SDK is not installed`` and had no way to know the AI was
uninstalled rather than absent.

These tests hold the install line and the honesty that has to travel with it.
Readiness to attempt is not presented as proof that a model answered, and raw
provider errors are not presented as acceptable public diagnostics.
"""
import os
import re

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


def _read(name: str) -> str:
    with open(os.path.join(REPO_ROOT, name), "r", encoding="utf-8") as handle:
        return handle.read()


def _quickstart_block() -> str:
    readme = _read("README.md")
    after_step_one = readme.split("### 1.", 1)[1]
    return after_step_one.split("```", 2)[1]


def test_the_bedrock_extra_still_declares_the_anthropic_client():
    pyproject = _read("pyproject.toml")
    # Split on the closing bracket at the start of a line: the requirement
    # itself contains a bracket, so a naive split truncates it mid-name.
    bedrock = pyproject.split("bedrock = [", 1)[1].split("\n]", 1)[0]
    assert "anthropic[bedrock]" in bedrock, (
        "the bedrock extra must install the client the adapter imports"
    )


def test_the_quickstart_install_line_pulls_in_the_bedrock_extra():
    block = _quickstart_block()
    install_lines = [line for line in block.splitlines() if "pip install" in line]
    assert install_lines, "the first quickstart step must install something"

    line = install_lines[0]
    assert "bedrock" in line, (
        f"the quickstart install line does not reach the model path: {line.strip()!r}"
    )
    assert "dev" in line, (
        f"the quickstart install line must still install the test tooling: {line.strip()!r}"
    )
    # The extras have to be declared in pyproject, or the command fails on a
    # clean machine with an error a judge cannot act on.
    pyproject = _read("pyproject.toml")
    for extra in re.findall(r"\[([a-z,]+)\]", line):
        for name in extra.split(","):
            assert f"{name} = [" in pyproject, f"README asks for an extra pyproject does not declare: {name}"


def test_the_readme_uses_the_response_as_the_model_receipt():
    """Installing the client or passing health is not the same as an answer."""
    readme = _read("README.md")
    install_context = readme.split("### 2.", 1)[0]
    assert "ready to attempt" in install_context
    assert "synthesis_mode: bedrock" in install_context
    assert "do not prove" in install_context


# The known limitations moved from the README to docs/EVIDENCE.md, which the
# README links from its first screen. The receipt procedure is checked there.
def test_an_operator_is_given_the_exact_command_that_reproduces_a_receipt():
    limitations = _read("docs/EVIDENCE.md").split("## Known limitations", 1)[1].split("\n## ", 1)[0]
    assert 'pip install -e ".[dev,bedrock]"' in limitations, (
        "the receipt procedure must name the install that reaches the model path"
    )
    assert "/api/digest_semantic_diff" in limitations, (
        "the receipt procedure must name the call that would exercise it"
    )
    assert "synthesis_mode" in limitations and "bedrock | None" in limitations, (
        "the entry must say what a successful receipt actually reads"
    )


def test_the_evidence_states_the_live_path_can_fail_without_breaking_the_digest():
    limitations = _read("docs/EVIDENCE.md").split("## Known limitations", 1)[1].split("\n## ", 1)[0]
    assert "permission, model availability or network" in limitations
    assert "deterministic digest answers" in limitations
    assert "provider identifiers do not leak" in limitations


def test_the_public_diagnostics_explicitly_reject_raw_provider_payloads():
    readme = _read("README.md")
    assert "raw account, role and" in readme
    assert "request identifiers never enter the anonymous response" in readme
    assert "fixed public category" in readme
