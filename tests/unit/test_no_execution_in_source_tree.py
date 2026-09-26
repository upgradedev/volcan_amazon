"""Holds the whole product to the claim the evidence document makes.

docs/EVIDENCE.md says "Never executed". That is a statement about ``src/``, not about
one module, so this test walks every module under ``src/`` and fails if any of
them imports or calls a process-execution primitive. It is deliberately broader
than ``tests/unit/test_dry_run_executor.py``, which guards the planner alone.

``ci/readiness.py`` and ``scripts/`` are out of scope on purpose: the auditor
runs git and pytest to check the repository, and that is a developer tool, not
the product a caller reaches over HTTP.
"""
import ast
import glob
import os

SRC_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "src")

FORBIDDEN_MODULES = {"subprocess", "multiprocessing", "pty", "commands"}
#: ``compile`` is deliberately absent: ``re.compile`` is everywhere and harmless.
#: What matters is that its dangerous partner ``exec`` is listed, along with
#: ``eval`` and every process-spawning call.
FORBIDDEN_CALLS = {"system", "popen", "Popen", "spawn", "spawnv", "spawnl",
                   "execv", "execve", "execl", "fork", "forkpty", "eval", "exec"}


def source_modules() -> list[str]:
    return sorted(glob.glob(os.path.join(SRC_ROOT, "**", "*.py"), recursive=True))


def parse(path: str) -> ast.Module:
    with open(path, "r", encoding="utf-8") as handle:
        return ast.parse(handle.read())


def test_there_is_at_least_one_module_to_check():
    assert len(source_modules()) >= 15


def test_no_source_module_imports_a_process_execution_primitive():
    offenders: list[str] = []
    for path in source_modules():
        imported: set[str] = set()
        for node in ast.walk(parse(path)):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        hits = imported & FORBIDDEN_MODULES
        if hits:
            offenders.append(f"{os.path.relpath(path, SRC_ROOT)} imports {sorted(hits)}")
    assert offenders == [], "the product must not import a process-execution primitive: " + "; ".join(offenders)


def test_no_source_module_calls_a_process_execution_primitive():
    offenders: list[str] = []
    for path in source_modules():
        called: set[str] = set()
        for node in ast.walk(parse(path)):
            if not isinstance(node, ast.Call):
                continue
            target = node.func
            if isinstance(target, ast.Name):
                called.add(target.id)
            elif isinstance(target, ast.Attribute):
                called.add(target.attr)
        hits = called & FORBIDDEN_CALLS
        if hits:
            offenders.append(f"{os.path.relpath(path, SRC_ROOT)} calls {sorted(hits)}")
    assert offenders == [], "the product must not call a process-execution primitive: " + "; ".join(offenders)
