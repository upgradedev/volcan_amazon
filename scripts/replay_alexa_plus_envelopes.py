"""Replay Amazon's documented Alexa+ MCP client requests against a Volcan server.

Built and tested locally, not certified or deployed; needs the owner's Amazon
developer account. Alexa+ has never called this server. This script sends the
request bodies Amazon documents for its Alexa+ MCP client
(``tests/fixtures/alexa_plus_envelopes.py`` names the page and the date) to a
Volcan MCP endpoint and prints what came back and how long each round trip
took, beside the documented requirement of a round trip under 500 ms.

The documentation shows bodies, not headers, so each requested revision is
replayed by three kinds of client:

* spec: adopts the revision the server answers with, and sends the
  ``MCP-Protocol-Version`` header when that revision defines one (2025-06-18
  and later; 2025-03-26 had no such header). This is a client that speaks
  2025-11-25 as well, which Amazon's overview implies by naming 2025-11-25.
* own: sends the ``MCP-Protocol-Version`` header set to the revision it asked
  for, whatever the server answered. For 2025-11-25 this is the spec client;
  for 2025-03-26 it declares a revision that defines no such header. This does
  not follow the lifecycle rule, but the page documents no headers, so it is
  as plausible for the real client as the other two.
* never: never sends the header, as a client that only knows 2025-03-26
  would. Volcan refuses every request after initialize from such a client, and
  the replay prints that refusal rather than hiding it.

Each shape is replayed ``--runs`` times and the tool-call round trip is
reported as the median with the range, because one sample of a warm local
server varies by about 10 ms from run to run.

Run command:
    python -m src.interfaces.mcp_server --port 8743      # terminal 1
    python scripts/replay_alexa_plus_envelopes.py http://127.0.0.1:8743/mcp
"""
import argparse
import json
import os
import statistics
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


#: Revisions that define the MCP-Protocol-Version header.
REVISIONS_WITH_VERSION_HEADER = ("2025-06-18", "2025-11-25")

CLIENTS = ("spec", "own", "never")


def replay(post: Post, protocol_version: str, client: str) -> dict:
    """One documented session: initialize, initialized, tools/list, tools/call.

    ``client`` is "spec", "own" or "never", as the module docstring describes.
    """
    if client not in CLIENTS:
        raise ValueError(f"client must be one of {CLIENTS}")
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
    if client == "spec" and negotiated in REVISIONS_WITH_VERSION_HEADER:
        headers["MCP-Protocol-Version"] = negotiated
    elif client == "own":
        headers["MCP-Protocol-Version"] = protocol_version
    step("notifications/initialized", envelopes.initialized_notification())
    step("tools/list", envelopes.tools_list())
    call = step("tools/call digest_semantic_diff", envelopes.tool_call())
    text = ""
    if isinstance(call["body"], dict):
        content = (call["body"].get("result") or {}).get("content") or []
        text = next((b.get("text", "") for b in content if b.get("type") == "text"), "")
    return {
        "protocol_version": protocol_version,
        "client": client,
        "version_header_sent": "MCP-Protocol-Version" in headers,
        "version_header": headers.get("MCP-Protocol-Version"),
        "negotiated": negotiated,
        "steps": steps,
        # The first text block is the spoken digest; the finding leads it.
        "finding_in_spoken_text": EXPECTED_FINDING in text.split(". ")[0].lower(),
        "tool_call_round_trip_ms": call["round_trip_ms"],
    }


LABELS = {
    "spec": "spec-following client",
    "own": "client that sends the revision it asked for as MCP-Protocol-Version",
    "never": "client that never sends MCP-Protocol-Version",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("url", nargs="?", default="http://127.0.0.1:8000/mcp")
    parser.add_argument("--warmups", type=int, default=3,
                        help="documented sessions run first and not reported, so the figures are warm")
    parser.add_argument("--runs", type=int, default=15,
                        help="sessions per client shape; the tool-call round trip is their median")
    args = parser.parse_args(argv)
    if args.runs < 1:
        parser.error("--runs must be at least 1")
    post = http_post(args.url)
    print("Replay of Amazon's documented Alexa+ MCP client requests. Built and tested locally,")
    print("not certified or deployed; needs the owner's Amazon developer account. Alexa+ did not send these.")
    print(f"Source: {envelopes.SOURCE_URL} (fetched {envelopes.FETCHED_ON}). Target: {args.url}")
    print(f"{args.warmups} warm-up sessions, then {args.runs} sessions per client shape.")
    for _ in range(args.warmups):
        replay(post, "2025-11-25", "spec")
    worst = 0
    for version in envelopes.DOCUMENTED_VERSIONS:
        for client in CLIENTS:
            runs = [replay(post, version, client) for _ in range(args.runs)]
            run = runs[0]
            print(f"\n[asks for {version}, {LABELS[client]}; answered {run['negotiated']}; "
                  f"header sent: {run['version_header'] or 'none'}]")
            for record in run["steps"]:
                mark = "ok  " if record["ok"] else "FAIL"
                print(f"  {mark} {record['step']}: HTTP {record['status']}; {record['summary']}")
            served = [r for r in runs if r["steps"][-1]["ok"]]
            if len(served) == len(runs):
                times = sorted(r["tool_call_round_trip_ms"] for r in runs)
                median = statistics.median(times)
                heard = all(r["finding_in_spoken_text"] for r in runs)
                within = median < DOCUMENTED_LATENCY_MS
                print(f"  tool call answered in {len(runs)}/{len(runs)} sessions; finding in its first sentence: "
                      f"{'yes' if heard else 'no'}; round trip median {median:.1f} ms "
                      f"(range {times[0]:.1f} to {times[-1]:.1f}) against the documented "
                      f"< {DOCUMENTED_LATENCY_MS:.0f} ms: {'within' if within else 'OVER'}")
            elif served:
                print(f"  tool call answered in only {len(served)}/{len(runs)} sessions")
                worst = 1
            else:
                print("  tool call refused, so there is no answer and no latency to compare")
                worst = 1
    print("\nA refusal above is a real incompatibility risk, not a test artefact: see docs/EVIDENCE.md, Road to Alexa+.")
    return worst


if __name__ == "__main__":
    sys.exit(main())
