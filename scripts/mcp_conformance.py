"""Run the MCP handshake against a live server and print a pass/fail report.

A judge can run this against a running Volcan instance and see, check by check,
whether the server really speaks the Model Context Protocol. It uses only the
standard library, so it needs no extra install.

Usage:
    python -m src.interfaces.mcp_server          # terminal 1
    python scripts/mcp_conformance.py            # terminal 2
    python scripts/mcp_conformance.py http://127.0.0.1:8000/mcp
    python scripts/mcp_conformance.py https://<host>/mcp --expect-mode stateless

Without --expect-mode the report accepts either transport mode the revision
permits and says which one answered. With it, a server in the other mode fails
the transport check, so a deployment that should be stateless cannot pass by
quietly issuing session ids (or the reverse).

Exit code 0 means every check passed; 1 means at least one failed.
"""
import argparse
import base64
import json
import sys
import urllib.error
import urllib.request

DEFAULT_URL = "http://127.0.0.1:8000/mcp"
PROTOCOL_VERSION = "2025-11-25"

PASS = "[PASS]"
FAIL = "[FAIL]"


class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[bool, str, str]] = []

    def check(self, ok: bool, title: str, detail: str = "") -> bool:
        self.rows.append((bool(ok), title, detail))
        print(f"  {PASS if ok else FAIL} {title}" + (f" -> {detail}" if detail else ""))
        return bool(ok)

    @property
    def failures(self) -> int:
        return sum(1 for ok, _, _ in self.rows if not ok)

    @property
    def total(self) -> int:
        return len(self.rows)


def call(url: str, payload, headers: dict[str, str] | None = None, method: str = "POST"):
    """Returns (status, headers, decoded_body_or_text)."""
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Content-Type", "application/json")
    request.add_header("Accept", "application/json, text/event-stream")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read()
            body = json.loads(raw) if raw and raw.lstrip()[:1] in (b"{", b"[") else raw.decode("utf-8", "replace")
            return response.status, dict(response.headers), body
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            body = json.loads(raw)
        except Exception:
            body = raw.decode("utf-8", "replace")
        return exc.code, dict(exc.headers), body


def main(url: str, expect_mode: str | None = None) -> int:
    print("=" * 64)
    print(f"  MCP CONFORMANCE REPORT  ({url})")
    print(f"  Target revision: {PROTOCOL_VERSION}, transport: Streamable HTTP")
    if expect_mode:
        print(f"  Expected transport mode: {expect_mode}")
    print("=" * 64)
    report = Report()

    print("\n1. Handshake")
    try:
        status, headers, body = call(url, {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                       "clientInfo": {"name": "volcan-conformance", "version": "1.0"}},
        })
    except Exception as exc:  # noqa: BLE001 - connection failures are a report line, not a crash
        print(f"  {FAIL} could not reach {url}: {type(exc).__name__}: {exc}")
        print("\n  Start the server first: python -m src.interfaces.mcp_server")
        return 1

    report.check(status == 200, "initialize returns HTTP 200", f"got {status}")
    result = body.get("result", {}) if isinstance(body, dict) else {}
    report.check(result.get("protocolVersion") == PROTOCOL_VERSION,
                 f"protocolVersion is {PROTOCOL_VERSION}", str(result.get("protocolVersion")))
    report.check(result.get("capabilities", {}).get("tools") is not None,
                 "capabilities advertise tools", json.dumps(result.get("capabilities")))
    report.check(bool(result.get("serverInfo", {}).get("name")),
                 "serverInfo carries a name and version", json.dumps(result.get("serverInfo")))

    session_id = headers.get("Mcp-Session-Id") or headers.get("mcp-session-id")
    stateful = bool(session_id)
    answered_mode = "stateful" if stateful else "stateless"
    detail = f"stateful, {len(session_id or '')} chars" if stateful else "stateless, no id issued"
    if expect_mode:
        detail += f"; expected {expect_mode}"
    report.check(
        (not session_id or len(session_id) >= 32)
        and (expect_mode is None or expect_mode == answered_mode),
        "transport declares a valid stateful id or explicit stateless mode",
        detail,
    )
    session_headers = {"MCP-Protocol-Version": PROTOCOL_VERSION}
    if session_id:
        session_headers["Mcp-Session-Id"] = session_id

    status, _, body = call(url, {"jsonrpc": "2.0", "method": "notifications/initialized"}, session_headers)
    report.check(status == 202, "notifications/initialized returns HTTP 202 with no body", f"got {status}")

    print("\n2. Tool catalog")
    status, _, body = call(url, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, session_headers)
    tools = body.get("result", {}).get("tools", []) if isinstance(body, dict) else []
    report.check(len(tools) > 0, "tools/list returns a catalog", f"{len(tools)} tools")
    schema_ok = all(
        isinstance(tool.get("inputSchema"), dict)
        and tool["inputSchema"].get("type") == "object"
        and isinstance(tool["inputSchema"].get("properties"), dict)
        for tool in tools
    )
    report.check(schema_ok, "every tool carries a JSON Schema object inputSchema")
    if tools:
        print("        " + ", ".join(sorted(tool["name"] for tool in tools)))

    status, stream_headers, stream_body = call(url, None, session_headers, method="GET")
    content_type = stream_headers.get("Content-Type") or stream_headers.get("content-type") or ""
    comment_only = (
        isinstance(stream_body, str)
        and stream_body.startswith(":")
        and "event:" not in stream_body
        and "data:" not in stream_body
        and "notifications/message" not in stream_body
    )
    report.check(
        status == 200 and "text/event-stream" in content_type and comment_only,
        "GET /mcp returns a comment-only terminating SSE stream",
        f"status {status}, content-type {content_type or '(absent)'}",
    )

    print("\n3. Tool invocation")
    status, _, body = call(url, {
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "play_earcon", "arguments": {"earcon_type": "ACTION_COMMITTED"}},
    }, session_headers)
    content = body.get("result", {}).get("content", []) if isinstance(body, dict) else []
    audio = next((block for block in content if block.get("type") == "audio"), None)
    report.check(audio is not None, "play_earcon returns an MCP audio content block")
    if audio:
        decoded = base64.b64decode(audio.get("data", ""))
        report.check(decoded.startswith(b"RIFF"), "audio block decodes to a real WAV file",
                     f"{len(decoded)} bytes, mimeType {audio.get('mimeType')}")

    print("\n4. Error handling")
    _, _, body = call(url, {
        "jsonrpc": "2.0", "id": 4, "method": "tools/call",
        "params": {"name": "no_such_tool", "arguments": {}},
    }, session_headers)
    report.check(body.get("error", {}).get("code") == -32602, "unknown tool returns -32602")

    _, _, body = call(url, {"jsonrpc": "2.0", "id": 5, "method": "no/such/method"}, session_headers)
    report.check(body.get("error", {}).get("code") == -32601, "unknown method returns -32601")

    _, _, body = call(url, {"jsonrpc": "1.0", "id": 6, "method": "ping"}, session_headers)
    report.check(body.get("error", {}).get("code") == -32600, "wrong jsonrpc version returns -32600")

    # The transport specification (2025-11-25, "Protocol Version Header"): with
    # no MCP-Protocol-Version header the server uses the revision it can
    # identify, such as the one negotiated for the session, and otherwise
    # assumes 2025-03-26; an invalid or unsupported header MUST get HTTP 400.
    no_version_headers = {"Mcp-Session-Id": session_id} if session_id else {}
    status, _, body = call(url, {"jsonrpc": "2.0", "id": 7, "method": "tools/list"},
                           no_version_headers)
    listed = body.get("result", {}).get("tools", []) if isinstance(body, dict) else []
    report.check(status == 200 and len(listed) == len(tools) and len(tools) > 0,
                 "tools/list without the version header is served, not refused",
                 f"HTTP {status}, {len(listed)} tools")

    status, _, _ = call(url, None, no_version_headers, method="GET")
    report.check(status == 200, "GET /mcp without the version header is served", f"got {status}")

    bad_version_headers = dict(no_version_headers, **{"MCP-Protocol-Version": "1999-01-01"})
    status, _, body = call(url, {"jsonrpc": "2.0", "id": 9, "method": "tools/list"},
                           bad_version_headers)
    report.check(
        status == 400 and isinstance(body, dict) and body.get("error", {}).get("code") == -32600
        and "result" not in body,
        "POST with an unsupported version header returns HTTP 400 and a JSON-RPC error",
        f"got {status}",
    )

    status, _, _ = call(url, None, bad_version_headers, method="GET")
    report.check(status == 400, "GET /mcp with an unsupported version header returns 400", f"got {status}")

    status, _, _ = call(url, None, bad_version_headers, method="DELETE")
    report.check(status == 400, "DELETE /mcp with an unsupported version header returns 400",
                 f"got {status}")

    status, _, _ = call(url, {"jsonrpc": "2.0", "id": 8, "method": "tools/list"},
                        {"Mcp-Session-Id": "never-issued", "MCP-Protocol-Version": PROTOCOL_VERSION})
    report.check(status == 404, "unknown session id returns HTTP 404", f"got {status}")

    status, headers, _ = call(url, {}, session_headers, method="PUT")
    report.check(status == 405, "unsupported HTTP method returns 405", f"got {status}")
    allow = headers.get("Allow") or headers.get("allow") or ""
    report.check("POST" in allow and "GET" in allow, "405 carries an Allow header", allow or "(absent)")

    print("\n5. Session termination")
    status, _, _ = call(url, None, session_headers, method="DELETE")
    expected_delete = 204 if stateful else 405
    report.check(
        status == expected_delete,
        "DELETE terminates a stateful session or is unavailable in stateless mode",
        f"got {status}; mode {'stateful' if stateful else 'stateless'}",
    )

    print("\n" + "=" * 64)
    passed = report.total - report.failures
    print(f"  SUMMARY: {passed}/{report.total} checks passed, {report.failures} failed")
    print("=" * 64)
    return 1 if report.failures else 0


def _parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python scripts/mcp_conformance.py")
    parser.add_argument("url", nargs="?", default=DEFAULT_URL,
                        help=f"the MCP endpoint (default {DEFAULT_URL})")
    parser.add_argument("--expect-mode", choices=["stateful", "stateless"], default=None,
                        help="fail unless the server answers in this transport mode")
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = _parse(sys.argv[1:])
    sys.exit(main(args.url, args.expect_mode))
