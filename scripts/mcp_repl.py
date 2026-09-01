"""Interactive FastMCP Terminal REPL for Volcan Agent Forge.

Provides an interactive CLI console for judges to test MCP tools,
synthesize pure PCM earcons, and inspect cryptographic execution leases.

Usage:
    python scripts/mcp_repl.py
"""
import time

from src.application.fastmcp_adapter import FastMcpServer

from src.domain.sonification import EarconType, WaveformSynthesizer


def main():
    mcp = FastMcpServer()
    synth = WaveformSynthesizer()

    print("================================================================")
    print("      VOLCAN VOICE AGENT FORGE — FASTMCP INTERACTIVE REPL       ")
    print("================================================================")
    print("Commands:")
    print("  1. diff        - Synthesize AST semantic diff with security alert")
    print("  2. stage       - Stage high-consequence production action (300s lease)")
    print("  3. confirm     - Confirm action with dual-custody voice token")
    print("  4. earcon      - Generate raw PCM WAV earcon audio bytes")
    print("  5. tools       - List registered FastMCP tools & schemas")
    print("  exit / quit    - Exit console\n")

    staged_action_id = None

    while True:
        try:
            cmd = input("volcan-mcp > ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting Volcan REPL.")
            break

        if cmd in ["exit", "quit", "q"]:
            print("Exiting Volcan REPL.")
            break

        if cmd == "1" or cmd == "diff":
            sample_diff = """diff --git a/src/auth.py b/src/auth.py
+ kms_key = os.environ.get("KMS_KEY_ID")
+ return verify_kms_token(token, kms_key)"""
            t0 = time.perf_counter()
            res = mcp.digest_semantic_diff(sample_diff, abstraction_level=0)
            t_ms = (time.perf_counter() - t0) * 1000.0
            print(f"\n[MCP: digest_semantic_diff] (computed in {t_ms:.3f} ms)")
            print(f"  Summary: \"{res['spoken_summary']}\"")
            print(f"  Files Modified: {res['files_modified']}")
            print(f"  Security Flag: {res['security_flag_detected']}")
            print(f"  Earcon Cue: {res['earcon_cue']}\n")

        elif cmd == "2" or cmd == "stage":
            res = mcp.stage_governed_action("aws ecs update-service --cluster prod --service volcan-api")
            staged_action_id = res["action_id"]
            print("\n[MCP: stage_governed_action]")
            print(f"  Action ID: {res['action_id']}")
            print(f"  Lease Status: {res['status']}")
            print(f"  Expires In: {res['expires_in_seconds']}s")
            print(f"  Voice Challenge Prompt: \"{res['voice_challenge_prompt']}\"")
            print(f"  Hash Lock: {res['action_hash'][:16]}...\n")

        elif cmd == "3" or cmd == "confirm":
            act_id = staged_action_id or "act_sample_01"
            res = mcp.confirm_action(act_id, "VOICE_TOKEN_ALEXA_AUTH_2026")
            print("\n[MCP: confirm_action]")
            print(f"  Status: {res['status']}")
            print(f"  Voice Token Verified: {res['voice_token_verified']}")
            print(f"  Output: {res['execution_output']}")
            print(f"  Audit Seal: {res['audit_receipt_hash'][:16]}...\n")
            staged_action_id = None

        elif cmd == "4" or cmd == "earcon":
            t0 = time.perf_counter()
            wav_bytes = synth.synthesize_earcon(EarconType.DIFF_READY)
            t_ms = (time.perf_counter() - t0) * 1000.0
            print(f"\n[Domain: WaveformSynthesizer] (synthesized in {t_ms:.3f} ms)")
            print(f"  Sample Rate: {synth.sample_rate} Hz (16-bit PCM)")
            print(f"  Generated Audio Payload: {len(wav_bytes)} WAV bytes")
            print(f"  Header: {wav_bytes[:4].decode('ascii')} format: {wav_bytes[8:12].decode('ascii')}\n")

        elif cmd == "5" or cmd == "tools":
            tools = mcp.list_tools()
            print(f"\n[Registered FastMCP Tools: {len(tools)}]")
            for t in tools:
                print(f"  - {t['name']}: {t['description']}")
            print()

        else:
            print(f"Unknown command: '{cmd}'. Type 1, 2, 3, 4, 5, or exit.")


if __name__ == "__main__":
    main()
