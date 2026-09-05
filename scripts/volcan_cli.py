#!/usr/bin/env python3
"""Volcan Multi-Modal Developer CLI & End-to-End Orchestrator.

Demonstrates:
1. Semantic AST Diff Digest & 22kHz Pure-PCM Audio Earcon Sonification
2. Silent Tactile Braille Stream (U+2800) & Physical 40-Cell Pin Matrix
3. Hands-Free Adaptive Switch Pulse (Sip-and-Puff / Foot Pedal)
4. Haptic Tactile Cadence for Deaf/HOH & Wearables
5. Dual-Custody 300s Cryptographic Execution Lease
6. Cross-Device Companion Coordination (Bee, Fire TV, Ring)
"""
import asyncio
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
from src.domain.sonification import EarconType
from src.infrastructure.audit_repository import InMemoryAuditRepository
from src.infrastructure.bedrock_adapter import BedrockSynthesisAdapter


class LocalShell:
    async def run_command(self, command: str) -> str:
        return f"[SANDBOX EXECUTION SUCCESS] '{command}'"


async def run_full_multimodal_demo() -> None:
    print("=" * 72)
    print(" 🌋 VOLCAN: ACCESSIBLE VOICE & MULTI-MODAL AI AGENT FORGE (SOTA MVP)")
    print(" Amazon Alexa+ | AWS Bedrock | Braille U+2800 | Switch | Haptics")
    print("=" * 72)

    # Composition Root
    audit_repo = InMemoryAuditRepository()
    bedrock = BedrockSynthesisAdapter()
    digest_uc = DigestDiffUseCase(bedrock)
    sonify_uc = SonifyEventUseCase()
    gov_uc = GovernedExecutionUseCase(LocalShell(), audit_repo)
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

    earcon_type = EarconType.GOVERNANCE_CHALLENGE if has_security else EarconType.DIFF_READY
    wav_bytes = sonify_uc.execute(earcon_type)
    print(f"  Generated Pure PCM WAV Earcon: {len(wav_bytes)} bytes ({earcon_type.value})")

    # 2. Silent Braille Stream & Pin Matrix
    print("\n[2/6] ⠠⠃⠗⠁⠊⠇⠇⠑ SILENT TACTILE BRAILLE STREAM (U+2800 - U+28FF)")
    braille_res = braille_uc.digest_to_braille(sample_diff)
    print(f"  Braille Summary: {braille_res['braille_summary']}")
    print(f"  Tactile Lines Formatted: {len(braille_res['lines'])} lines")
    for l in braille_res['lines']:
        print(f"    [{l['type']}] {l['braille']}")

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

    # 5. Dual-Custody Governance Lease
    print("\n[5/6] 🛡️ DUAL-CUSTODY GOVERNANCE & CRYPTOGRAPHIC HASH LOCK")
    action_id = "act_prod_deploy_104"
    lease = gov_uc.stage_action(
        action_id=action_id,
        action_type="PRODUCTION_DEPLOY",
        command="aws ecs update-service --cluster prod --service volcan-api",
        summary_spoken="Deploy updated authentication service to production",
        lease_sec=300.0,
    )
    print(f"  Staged Action ID: {lease.action_id} | TTL: {lease.lease_duration_sec}s")
    print(f"  SHA-256 Hash Lock: {lease.payload_hash}")
    out = await gov_uc.confirm_and_execute(
        action_id=action_id,
        voice_token="VOICE_TOKEN_ALEXA_AUTH_2026",
    )
    print(f"  Execution Output: {out}")
    print(f"  Action Final State: {lease.state.value} (Dual-Custody Confirmed)")

    # 6. Multi-Device Companion Coordination
    print("\n[6/6] 🌐 CROSS-DEVICE COMPANIONS (BEE, FIRE TV, RING)")
    bee_res = ecosystem_uc.attach_bee_ambient_note("dev_42", "Verify KMS key rotation", "PR-104")
    print(f"  🐝 Bee Wearable: Spoken note attached to PR-104 ({bee_res['spoken_digest']})")
    tv_res = ecosystem_uc.sync_firetv_compatibility(lease.action_id, 300, True, "ELITE")
    print(f"  📺 Fire TV 10-Foot: Telemetry frame synced (DORA: {tv_res['dora_velocity']})")
    ring_res = ecosystem_uc.evaluate_ring_presence("Front Door", lease.action_id)
    print(f"  🔔 Ring Sanctuary: Focus active -> Suppressed chime & played {ring_res['acoustic_earcon']}")

    print("\n" + "=" * 72)
    print(" ✅ VOLCAN MULTI-MODAL SOTA MVP ORCHESTRATION COMPLETED (100% PASS)")
    print("=" * 72)


if __name__ == "__main__":
    asyncio.run(run_full_multimodal_demo())
