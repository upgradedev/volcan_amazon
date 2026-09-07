"""The quickstart has to install the path the product is judged on.

Volcan's AI path is the Amazon Bedrock adapter. It lives behind the optional
``bedrock`` extra, and until 2026-09-08 the quickstart installed a hand-listed
set of packages that did not include it. A judge who followed the README
exactly therefore saw ``SYNTHESIS ENGINE: local heuristic`` and
``the Anthropic SDK is not installed`` and had no way to know the AI was
uninstalled rather than absent.

These tests hold the install line and the honesty that has to travel with it.
The second one is the control: making the first pass by promising a Bedrock
answer the repository has never observed would be worse than the bug.
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


def test_the_readme_still_refuses_to_claim_a_model_answered_here():
    """The control. Installing the client is not the same as being answered.

    Nobody working on this repository has AWS access that can confirm the
    pinned model id, so the README must keep saying so next to the install
    instruction. A quickstart that reads as a promise of Bedrock output would
    close the gap by lying about it.
    """
    readme = _read("README.md")
    assert "No model has ever answered here" in readme
    assert "the pinned model id is unverified" in readme
    assert "Bedrock has never answered here" in readme, (
        "the Known limitations entry must survive the quickstart change"
    )


def test_the_published_fallback_transcript_says_which_machine_state_produced_it():
    """A verbatim block is only honest while its conditions are stated.

    The transcript in the README was produced without the extra installed. Now
    that the quickstart installs it, the block has to name that condition or a
    reader will take a stale local state for the product's behaviour.
    """
    readme = _read("README.md")
    transcript_intro = readme.split("synthesis_fallback_reason: the Anthropic SDK", 1)[0]
    tail = transcript_intro.rsplit("Run on", 1)[-1]
    assert "without" in tail.lower(), (
        "the verbatim fallback transcript must say it was measured without the bedrock extra"
    )
