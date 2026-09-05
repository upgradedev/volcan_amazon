#!/usr/bin/env python3
"""Volcan end-to-end walkthrough in one terminal command.

Runs the real use cases in order and prints what they actually returned:

1. Patch digest and PCM earcon synthesis, with the synthesis mode that produced it
2. Silent Unicode Braille stream in the U+2800 block
3. Adaptive switch pulse resolution, sip and puff
4. Haptic cadence and its visual caption
5. A governed action staged, refused for the agent, released by a human, then
   refused on replay, with the audit chain verified afterwards
6. Cross-device companions, simulated locally with no device SDK involved

No shell command is executed at any point. No hardware is contacted. The Bedrock
path runs only if AWS credentials are present, and the synthesis mode printed in
step 1 says which path actually ran.

Usage:
    python scripts/volcan_cli.py
"""
import asyncio
import secrets
import sys
import time
from pathlib import Path

# Ensure volcan_amazon repo root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from src.application.accessibility_use_case import AccessibilityOrchestratorUseCase
from src.application.braille_diff_use_case import BrailleDiffUseCase
from src.application.digest_diff_use_case import DigestDiffUseCase
from src.application.ecosystem_companion_use_case import OrchestrateEcosystemCompanionUseCase
from src.application.governed_execution_use_case import GovernedExecutionUseCase
from src.application.sonify_event_use_case import SonifyEventUseCase
from src.domain.approval_grant import ApprovalGrantIssuer
from src.domain.governed_action import Principal
from src.domain.sonification import EarconType
from src.infrastructure.audit_repository import InMemoryAuditRepository
from src.infrastructure.bedrock_adapter import BedrockSynthesisAdapter
from src.infrastructure.dry_run_executor import DryRunExecutor


async def run_full_multimodal_demo() -> None:
    print("=" * 72)
    print(" VOLCAN: accessible voice and multi-modal review, end to end")
    print(" Every number printed below was measured during this run.")
    print("=" * 72)

    # Composition Root
    audit_repo = InMemoryAuditRepository()
    bedrock = BedrockSynthesisAdapter()
    digest_uc = DigestDiffUseCase(bedrock)
    sonify_uc = SonifyEventUseCase()
    planner = DryRunExecutor()
    gov_uc = GovernedExecutionUseCase(
        planner, audit_repo, ApprovalGrantIssuer(secrets.token_bytes(32)),
    )
    ecosystem_uc = OrchestrateEcosystemCompanionUseCase()
    braille_uc = BrailleDiffUseCase()
    access_uc = AccessibilityOrchestratorUseCase()

    # 1. AST Diff Digest & Sonification
    print("\n[1/6] 🎧 AST SEMANTIC DIFF DIGEST & AUDIO SONIFICATION")
    sample_diff = (
        "diff --git a/src/auth/service.py b/src/auth/service.py\n"
        "--- a/src/auth/service.py\n"
        "+++ b/src/auth/service.py\n"
        "@@ -10,4 +10,6 @@\n"
        "- return token == 'hardcoded_secret'\n"
        "+ kms_key = os.environ.get('KMS_KEY_ID')\n"
        "+ return verify_kms_token(token, kms_key)\n"
    )
    t0 = time.perf_counter()
    report = await digest_uc.execute(sample_diff)
    latency_ms = (time.perf_counter() - t0) * 1000
    has_security = len(report.critical_findings) > 0
    print(f"  Parsed AST in {latency_ms:.3f} ms | Critical Findings: {len(report.critical_findings)}")
    print(f"  Level 0 Executive Spoken Summary: \"{report.to_voice_summary(0)}\"")
    print(f"  Level 1 Detailed Spoken Summary:  \"{report.to_voice_summary(1)}\"")

    print(f"  Synthesis mode: {report.synthesis_mode}")
    earcon_type = EarconType.GOVERNANCE_CHALLENGE if has_security else EarconType.DIFF_READY
    _cue, wav_bytes = sonify_uc.execute(earcon_type)
    print(f"  Generated PCM WAV earcon: {len(wav_bytes)} bytes ({earcon_type.value})")

    # 2. Silent Braille Stream & Pin Matrix
    print("\n[2/6] ⠠⠃⠗⠁⠊⠇⠇⠑ SILENT TACTILE BRAILLE STREAM (U+2800 - U+28FF)")
    braille_res = braille_uc.digest_to_braille(sample_diff)
    print(f"  Braille Summary: {braille_res['braille_summary']}")
    print(f"  Tactile Lines Formatted: {len(braille_res['lines'])} lines")
    for line in braille_res['lines']:
        print(f"    [{line['type']}] {line['braille']}")

    # 3. Adaptive Switch Access (Hands-Free / Sip-and-Puff)
    print("\n[3/6] 🦾 ADAPTIVE SWITCH ACCESS (SIP-AND-PUFF & FOOT PEDALS)")
    puff_res = access_uc.process_switch_signal("SIP_AND_PUFF", signal_strength=0.85)
    print(f"  Sip-and-Puff Input (Puff 0.85): -> Action: {puff_res['resolved_action']}")
    sip_res = access_uc.process_switch_signal("SIP_AND_PUFF", signal_strength=0.15)
    print(f"  Sip-and-Puff Input (Sip 0.15):  -> Action: {sip_res['resolved_action']}")

    # 4. Haptic Vibration Cadence (Deaf / HOH & Wearables)
    print("\n[4/6] 🦻 HAPTIC TACTILE CADENCE & CLOSED CAPTIONS")
    haptic_res = access_uc.generate_haptic_profile("SECURITY_FLAG")
    print(f"  Pattern: {haptic_res['pattern_type']} ({haptic_res['total_duration_ms']}ms)")
    print(f"  Caption: {haptic_res['visual_caption']}")
    print(f"  Tactile Steps: {len(haptic_res['steps'])} vibration pulses")

    # 5. Governed action: staged, refused for an agent, released by a human
    print("\n[5/6] GOVERNED ACTION: STAGE, REFUSE, RELEASE")
    action_id = "act_prod_deploy_104"
    ticket = gov_uc.stage_action(
        action_id=action_id,
        action_type="PRODUCTION_DEPLOY",
        command="aws ecs update-service --cluster prod --service volcan-api",
        summary_spoken="Deploy updated authentication service to production",
        lease_sec=300.0,
        staged_by=Principal.agent("volcan-agent"),
    )
    print(f"  Staged action: {ticket.action.action_id} | lease {ticket.action.lease_duration_sec}s")
    print(f"  Payload hash:  {ticket.action.payload_hash}")
    print(f"  Grant issued:  {ticket.grant[:34]}...")

    plan = planner.plan(ticket.action.command_or_path)
    print(f"  Planner verdict: allowed={plan.allowed} executed={plan.executed}")
    print(f"  Planner reason:  {plan.refusal_reason or plan.would_run}")

    agent_attempt = await gov_uc.confirm_and_execute(
        action_id, ticket.grant, approver=Principal.agent("volcan-agent"),
    )
    print(f"  Agent tries to approve its own proposal -> refused: {agent_attempt.refusal_code}")

    human = await gov_uc.confirm_and_execute(
        action_id, ticket.grant, approver=Principal.human("lead-engineer"),
    )
    print(f"  Human approves -> approved={human.approved}")
    print(f"  Result: {human.output}")

    replay = await gov_uc.confirm_and_execute(
        action_id, ticket.grant, approver=Principal.human("lead-engineer"),
    )
    print(f"  Same grant presented again -> refused: {replay.refusal_code}")

    chain = audit_repo.verify_integrity()
    print(f"  Audit chain: {chain.verified_entries} entries, intact={chain.intact}, {chain.detail}")

    # 6. Multi-Device Companion Coordination
    print("\n[6/6] CROSS-DEVICE COMPANIONS, SIMULATED LOCALLY, NO DEVICE SDK INVOLVED")
    bee_res = ecosystem_uc.attach_bee_ambient_note("dev_42", "Verify KMS key rotation", "PR-104")
    print(f"  🐝 Bee Wearable: Spoken note attached to PR-104 ({bee_res['spoken_digest']})")
    tv_res = ecosystem_uc.sync_firetv_compatibility(action_id, 300, True, "ELITE")
    print(f"  📺 Fire TV 10-Foot: Telemetry frame synced (DORA: {tv_res['dora_velocity']})")
    ring_res = ecosystem_uc.evaluate_ring_presence("Front Door", action_id)
    print(f"  🔔 Ring Sanctuary: Focus active -> Suppressed chime & played {ring_res['acoustic_earcon']}")

    print("\n" + "=" * 72)
    print(" Walkthrough complete. Nothing above executed a shell command.")
    print("=" * 72)


if __name__ == "__main__":
    asyncio.run(run_full_multimodal_demo())
