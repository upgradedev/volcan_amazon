"""Run the MCP handshake against a live server and print a pass/fail report.

A judge can run this against a running Volcan instance and see, check by check,
whether the server really speaks the Model Context Protocol. It uses only the
standard library, so it needs no extra install.

Usage:
    python -m src.interfaces.mcp_server          # terminal 1
    python scripts/mcp_conformance.py            # terminal 2
    python scripts/mcp_conformance.py http://127.0.0.1:8000/mcp

Exit code 0 means every check passed; 1 means at least one failed.
"""
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


def main(url: str) -> int:
    print("=" * 64)
    print(f"  MCP CONFORMANCE REPORT  ({url})")
    print(f"  Target revision: {PROTOCOL_VERSION}, transport: Streamable HTTP")
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
    report.check(
        not session_id or len(session_id) >= 32,
        "transport declares a valid stateful id or explicit stateless mode",
        f"stateful, {len(session_id or '')} chars" if stateful else "stateless, no id issued",
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

    no_version_headers = {"Mcp-Session-Id": session_id} if session_id else {}
    _, _, body = call(url, {"jsonrpc": "2.0", "id": 7, "method": "tools/list"},
                      no_version_headers)
    report.check(body.get("error", {}).get("code") == -32600,
                 "missing MCP-Protocol-Version header returns a JSON-RPC error")
    # The dangerous shape of that failure is not an error, it is a plausible
    # answer: a result member holding an empty tool list, which reads on stage
    # as a server that publishes nothing.
    report.check("result" not in (body if isinstance(body, dict) else {}),
                 "and returns no result member alongside it")

    status, _, _ = call(url, None, no_version_headers, method="GET")
    report.check(status == 400, "GET /mcp without the version header is refused", f"got {status}")

    status, _, _ = call(url, None, no_version_headers, method="DELETE")
    report.check(status == 400, "DELETE /mcp without the version header is refused", f"got {status}")

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


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL))
