"""Replay Amazon's documented Alexa+ MCP client requests against a Volcan server.

Built and tested locally, not certified or deployed; needs the owner's Amazon
developer account. Alexa+ has never called this server. This script sends the
request bodies Amazon documents for its Alexa+ MCP client
(``tests/fixtures/alexa_plus_envelopes.py`` names the page and the date) to a
Volcan MCP endpoint and prints what came back and how long each round trip
took, beside the documented requirement of a round trip under 500 ms.

The documentation shows bodies, not headers, so each protocol revision is
replayed twice: once with no ``MCP-Protocol-Version`` header after initialize,
and once with it set to the negotiated revision. A client on revision
2025-03-26 has no reason to send that header, because the header arrived in a
later revision, and Volcan refuses a request without it. The replay prints
that refusal rather than hiding it.

Run command:
    python -m src.interfaces.mcp_server --port 8743      # terminal 1
    python scripts/replay_alexa_plus_envelopes.py http://127.0.0.1:8743/mcp
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tests.fixtures import alexa_plus_envelopes as envelopes  # noqa: E402

#: "Your MCP server must meet a round-trip query response latency of less than
#: 500 ms." Alexa+ MCP QuickStart Guide, page dated Jul 10, 2026.
DOCUMENTED_LATENCY_MS = 500.0

#: The sentence the digest must lead with for the inverted admin check.
EXPECTED_FINDING = "an authorization comparison was inverted"

Post = Callable[[dict, dict], tuple[int, dict, object]]


def _decode(raw: bytes) -> object:
    text = raw.decode("utf-8", "replace").strip()
    if text.startswith("{"):
        return json.loads(text)
    for line in text.splitlines():  # an SSE-framed answer: take the data line
        if line.startswith("data:"):
            return json.loads(line[5:].strip())
    return text


def http_post(url: str) -> Post:
    def post(payload: dict, headers: dict) -> tuple[int, dict, object]:
        request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST")
        request.add_header("Content-Type", "application/json")
        request.add_header("Accept", "application/json, text/event-stream")
        for key, value in headers.items():
            request.add_header(key, value)
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return response.status, {k.lower(): v for k, v in response.headers.items()}, _decode(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, {k.lower(): v for k, v in exc.headers.items()}, _decode(exc.read())
    return post


def _summary(body: object) -> tuple[bool, str]:
    """(ok, one line) for a JSON-RPC answer."""
    if not isinstance(body, dict):
        return False, f"not JSON-RPC: {str(body)[:80]}"
    if "error" in body:
        return False, f"JSON-RPC error {body['error'].get('code')}: {body['error'].get('message')}"
    result = body.get("result") or {}
    if "protocolVersion" in result:
        return True, f"negotiated {result['protocolVersion']}"
    if "tools" in result:
        return True, f"{len(result['tools'])} tools"
    if "content" in result:
        kinds = [block.get("type") for block in result["content"]]
        text = next((b.get("text", "") for b in result["content"] if b.get("type") == "text"), "")
        return not result.get("isError", False), f"content {kinds}; first text: {text[:110]}"
    return True, "accepted"


def replay(post: Post, protocol_version: str, send_version_header: bool) -> dict:
    """One documented session: initialize, initialized, tools/list, tools/call."""
    steps: list[dict] = []
    headers: dict[str, str] = {}

    def step(name: str, payload: dict) -> dict:
        started = time.perf_counter()
        status, response_headers, body = post(payload, dict(headers))
        elapsed = (time.perf_counter() - started) * 1000.0
        ok, line = _summary(body) if body not in ("", None) else (200 <= status < 300, f"HTTP {status}, empty body")
        record = {"step": name, "status": status, "ok": ok and status < 400, "summary": line,
                  "round_trip_ms": round(elapsed, 1), "body": body, "headers": response_headers}
        steps.append(record)
        return record

    first = step("initialize", envelopes.initialize(protocol_version))
    session = first["headers"].get("mcp-session-id")
    if session:
        headers["Mcp-Session-Id"] = session
    negotiated = ((first["body"] or {}).get("result") or {}).get("protocolVersion") if isinstance(first["body"], dict) else None
    if send_version_header and negotiated:
        headers["MCP-Protocol-Version"] = negotiated
    step("notifications/initialized", envelopes.initialized_notification())
    step("tools/list", envelopes.tools_list())
    call = step("tools/call digest_semantic_diff", envelopes.tool_call())
    text = ""
    if isinstance(call["body"], dict):
        content = (call["body"].get("result") or {}).get("content") or []
        text = next((b.get("text", "") for b in content if b.get("type") == "text"), "")
    return {
        "protocol_version": protocol_version,
        "version_header_sent": send_version_header,
        "negotiated": negotiated,
        "steps": steps,
        # The first text block is the spoken digest; the finding leads it.
        "finding_in_spoken_text": EXPECTED_FINDING in text.split(". ")[0].lower(),
        "tool_call_round_trip_ms": call["round_trip_ms"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("url", nargs="?", default="http://127.0.0.1:8000/mcp")
    parser.add_argument("--warmups", type=int, default=3,
                        help="documented sessions run first and not reported, so the figures are warm")
    args = parser.parse_args(argv)
    post = http_post(args.url)
    print("Replay of Amazon's documented Alexa+ MCP client requests. Built and tested locally,")
    print("not certified or deployed; needs the owner's Amazon developer account. Alexa+ did not send these.")
    print(f"Source: {envelopes.SOURCE_URL} (fetched {envelopes.FETCHED_ON}). Target: {args.url}")
    for _ in range(args.warmups):
        replay(post, "2025-11-25", True)
    worst = 0
    for version in envelopes.DOCUMENTED_VERSIONS:
        for with_header in (False, True):
            run = replay(post, version, with_header)
            label = "with MCP-Protocol-Version" if with_header else "headers as documented (none)"
            print(f"\n[{version}, {label}]")
            for record in run["steps"]:
                mark = "ok  " if record["ok"] else "FAIL"
                print(f"  {mark} {record['step']}: HTTP {record['status']}, {record['round_trip_ms']} ms; {record['summary']}")
            call_ok = run["steps"][-1]["ok"]
            if call_ok:
                within = run["tool_call_round_trip_ms"] < DOCUMENTED_LATENCY_MS
                print(f"  tool call answered; finding in its first sentence: "
                      f"{'yes' if run['finding_in_spoken_text'] else 'no'}; round trip "
                      f"{run['tool_call_round_trip_ms']} ms against the documented < {DOCUMENTED_LATENCY_MS:.0f} ms: "
                      f"{'within' if within else 'OVER'}")
            else:
                print("  tool call refused, so there is no answer and no latency to compare")
                worst = 1
    print("\nA refusal above is a real incompatibility risk, not a test artefact: see docs/EVIDENCE.md, Road to Alexa+.")
    return worst


if __name__ == "__main__":
    sys.exit(main())
