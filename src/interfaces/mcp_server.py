"""Interfaces Layer: the FastAPI application and the MCP Streamable HTTP transport.

This module owns the ASGI application and the ``/mcp`` endpoint. Everything
else is composed from focused modules:

* ``src/interfaces/mcp_protocol.py``  JSON-RPC 2.0 and MCP message semantics
* ``src/interfaces/composition.py``   adapters, use cases and the session registry
* ``src/interfaces/dto.py``           request models both surfaces validate with
* ``src/interfaces/operations.py``    application operations both surfaces call
* ``src/interfaces/rest_api.py``      the REST surface at ``/api`` (not MCP)
* ``src/interfaces/mcp_tools.py``     the MCP tool catalog

Two surfaces, stated plainly:

1. **MCP** at ``POST /mcp`` and ``GET /mcp``: Model Context Protocol, revision
   2025-11-25, Streamable HTTP transport, JSON-RPC 2.0 messages, hand-written
   with no MCP SDK. ``DELETE /mcp`` terminates a session. All three methods are
   bound to one route so an unsupported method returns 405 with an Allow header
   naming every method the endpoint really accepts.
2. **REST** under ``/api/*``: ordinary JSON over HTTP for the web companion.

Run locally, bound to loopback:

    python -m src.interfaces.mcp_server
    # then: python scripts/mcp_conformance.py http://127.0.0.1:8000/mcp
"""
import json
import time
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from src.application.review_authorization import current_review_principal
from src.infrastructure.observability_harness import PrivateObservabilityHarness
from src.interfaces.composition import allowed_origins, sessions
from src.interfaces.mcp_protocol import (
    INVALID_REQUEST,
    PARSE_ERROR,
    PROTOCOL_VERSION,
    SERVER_NAME,
    SERVER_VERSION,
    SUPPORTED_PROTOCOL_VERSIONS,
    JsonRpcError,
    McpDispatcher,
)
from src.interfaces.mcp_tools import build_tool_registry
from src.interfaces.rest_api import router as rest_router
from src.interfaces.review_authorization import authenticated_reviewer
from src.interfaces.web_companion import load_companion_html

app = FastAPI(
    title="Volcan Accessible AI Agent Forge",
    description=(
        "MCP server (revision 2025-11-25, Streamable HTTP) at /mcp, plus a REST "
        "surface at /api for the web companion."
    ),
    version=SERVER_VERSION,
)
app.include_router(rest_router)


@app.middleware("http")
async def review_identity_context(request: Request, call_next):
    # Both HTTP surfaces receive fresh context; read-only routes remain public.
    principal = authenticated_reviewer(request.headers.get("authorization"))
    token = current_review_principal.set(principal)
    try:
        return await call_next(request)
    finally:
        current_review_principal.reset(token)


tool_registry = build_tool_registry()
dispatcher = McpDispatcher(
    tool_registry,
    instructions=(
        "Volcan turns code review into sound and touch for blind and mobility-impaired "
        "developers. Call digest_semantic_diff first; it returns spoken text and an audio "
        "earcon. Commands are planned, never executed."
    ),
)


# --- MCP Streamable HTTP transport -----------------------------------------

MCP_ALLOW = "GET, POST, DELETE"


def _rpc_error(request_id: Any, code: int, message: str, data: Any = None, status: int = 200) -> JSONResponse:
    body = McpDispatcher.error_response(request_id, JsonRpcError(code, message, data))
    return JSONResponse(status_code=status, content=body, headers={"MCP-Protocol-Version": PROTOCOL_VERSION})


def _origin_refusal(request: Request) -> JSONResponse | None:
    """Rejects a present-but-unexpected Origin.

    An absent Origin is allowed: non-browser MCP clients and curl send none.
    The check exists to stop a hostile page in a browser from driving a server
    bound to loopback, which is the DNS-rebinding case the specification warns
    about.
    """
    origin = request.headers.get("origin")
    if origin is None:
        return None
    # A browser calling the companion sends an Origin even when the page and
    # endpoint share an origin. That public origin must still be configured
    # explicitly: trusting Host/request.base_url would reopen the DNS-rebinding
    # case this check exists to prevent.
    if origin in allowed_origins():
        return None
    return JSONResponse(
        status_code=403,
        content={
            "error": "origin_not_allowed",
            "detail": (
                f"Origin '{origin}' is not permitted. Set VOLCAN_ALLOWED_ORIGINS to allow it."
            ),
            "allowed": sorted(allowed_origins()),
        },
    )


def _session_refusal(request: Request) -> JSONResponse | None:
    """A session id this server never issued, or already terminated, is a 404."""
    session_id = request.headers.get("mcp-session-id")
    if session_id is None:
        return None
    if sessions.exists(session_id):
        return None
    return JSONResponse(
        status_code=404,
        content={"error": "unknown_session", "detail": "No such MCP session; run initialize again."},
    )


#: Why a header is refused, and the machine-readable code that goes with it.
#: The two verbs that carry no JSON-RPC envelope reuse these strings, so the
#: refusal a client reads is the same sentence whichever method it sent.
_VERSION_MISSING = (
    "Missing MCP-Protocol-Version header; it is required on every request after initialize."
)


def _protocol_version_problem(request: Request) -> tuple[str, dict[str, Any]] | None:
    """(message, data) when the declared protocol version is unusable.

    This is the whole rule, in one place, so no transport verb can quietly opt
    out of it. It is deliberately stricter than the transport specification,
    which permits a server that receives no ``MCP-Protocol-Version`` header to
    assume the older ``2025-03-26`` revision. Assuming it would let a client and
    this server disagree about the revision they are speaking while both believe
    the handshake succeeded, which is a failure that surfaces later and
    somewhere else. Volcan refuses instead and names the header, and the README
    states that it is required on every request after initialize.
    """
    declared = request.headers.get("mcp-protocol-version")
    if declared is None:
        return _VERSION_MISSING, {"expected": PROTOCOL_VERSION}
    if declared not in SUPPORTED_PROTOCOL_VERSIONS:
        return (
            f"Unsupported MCP-Protocol-Version '{declared}'.",
            {"supported": list(SUPPORTED_PROTOCOL_VERSIONS)},
        )
    return None


def _protocol_version_refusal(request: Request, method: str, request_id: Any) -> JSONResponse | None:
    """The POST form of the rule: a JSON-RPC error against the request id.

    The check runs on the method alone. It does not consult the session, so a
    request that carries a valid ``Mcp-Session-Id`` and omits the version header
    is refused exactly like one that carries neither: a conforming client that
    forgets one header has to see an error, never a successful-looking result
    with an empty tool list.
    """
    if method == "initialize":
        return None
    problem = _protocol_version_problem(request)
    if problem is None:
        return None
    message, data = problem
    return _rpc_error(request_id, INVALID_REQUEST, message, data)


def _transport_version_refusal(request: Request) -> JSONResponse | None:
    """The GET and DELETE form of the rule.

    Neither verb carries a JSON-RPC request, so there is no id to answer and no
    envelope to put an error member in. They answer at the transport level, the
    way the Origin and session refusals above already do, and quote the same
    sentence POST does so a client reads one rule rather than two.
    """
    problem = _protocol_version_problem(request)
    if problem is None:
        return None
    message, data = problem
    return JSONResponse(
        status_code=400,
        content={"error": "bad_protocol_version", "detail": message, **data},
    )


@app.api_route("/mcp", methods=["GET", "POST", "DELETE"], include_in_schema=True)
async def mcp_endpoint(request: Request) -> Response:
    """The single MCP endpoint of the Streamable HTTP transport.

    All three methods are bound to one route so that an unsupported method such
    as PUT receives a 405 whose Allow header lists every method this endpoint
    really accepts, rather than whichever route happened to be registered first.
    """
    if request.method == "POST":
        return await mcp_post(request)
    if request.method == "GET":
        return await mcp_get(request)
    return await mcp_delete(request)


async def mcp_post(request: Request) -> Response:
    refusal = _origin_refusal(request) or _session_refusal(request)
    if refusal is not None:
        return refusal

    raw = await request.body()
    try:
        message = json.loads(raw) if raw else None
    except json.JSONDecodeError as exc:
        return _rpc_error(None, PARSE_ERROR, f"Parse error: {exc.msg} at position {exc.pos}.")

    if message is None:
        return _rpc_error(None, INVALID_REQUEST, "Request body is empty.")

    request_id = message.get("id") if isinstance(message, dict) else None
    method = message.get("method") if isinstance(message, dict) else None

    if isinstance(method, str):
        version_refusal = _protocol_version_refusal(request, method, request_id)
        if version_refusal is not None:
            return version_refusal

    started = time.perf_counter()
    try:
        outcome = await dispatcher.dispatch(message)
    except JsonRpcError as exc:
        # JSON-RPC application errors travel as HTTP 200 with an error member;
        # HTTP status is reserved for transport-level problems.
        return _rpc_error(request_id, exc.code, exc.message, exc.data)

    elapsed_ms = (time.perf_counter() - started) * 1000.0

    if outcome.body is None:
        # A JSON-RPC notification gets no response body at all.
        return Response(status_code=202, headers={"MCP-Protocol-Version": PROTOCOL_VERSION})

    headers = {"MCP-Protocol-Version": outcome.negotiated_version}
    if outcome.is_initialize:
        headers["Mcp-Session-Id"] = sessions.create()

    if isinstance(method, str) and method == "tools/call":
        _emit_tool_metric(message, elapsed_ms)

    return JSONResponse(status_code=200, content=outcome.body, headers=headers)


def _emit_tool_metric(message: dict[str, Any], elapsed_ms: float) -> None:
    """Emits one genuinely measured CloudWatch EMF record per tool call."""
    tool_name = "unknown"
    params = message.get("params")
    if isinstance(params, dict) and isinstance(params.get("name"), str):
        tool_name = params["name"]
    harness = PrivateObservabilityHarness()
    harness.record_metric("McpToolDurationMs", round(elapsed_ms, 3))
    harness.add_audit_event(
        actor="mcp-client",
        action="tools/call",
        details={"tool": tool_name, "duration_ms": round(elapsed_ms, 3)},
    )
    harness.flush()


async def mcp_get(request: Request) -> Response:
    """Opens the server-to-client SSE stream of the Streamable HTTP transport.

    This server has no long-lived server-initiated traffic to push, so the
    stream announces itself and closes rather than holding a socket open for a
    message that will never come. A client that wants request/response traffic
    uses POST.
    """
    refusal = (
        _origin_refusal(request)
        or _session_refusal(request)
        or _transport_version_refusal(request)
    )
    if refusal is not None:
        return refusal

    session_id = request.headers.get("mcp-session-id")

    def event_stream():
        yield ": volcan mcp stream open\n\n"
        notice = {
            "jsonrpc": "2.0",
            "method": "notifications/message",
            "params": {
                "level": "info",
                "logger": SERVER_NAME,
                "data": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "session": session_id,
                    "note": (
                        "Stream opened. This server pushes no unsolicited messages; "
                        "send JSON-RPC requests to POST /mcp."
                    ),
                },
            },
        }
        yield f"event: message\ndata: {json.dumps(notice)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "MCP-Protocol-Version": PROTOCOL_VERSION,
            "X-Accel-Buffering": "no",
        },
    )


async def mcp_delete(request: Request) -> Response:
    """Terminates an MCP session, as the Streamable HTTP transport allows."""
    refusal = _origin_refusal(request) or _transport_version_refusal(request)
    if refusal is not None:
        return refusal
    session_id = request.headers.get("mcp-session-id")
    if session_id is None:
        return JSONResponse(
            status_code=400,
            content={"error": "missing_session", "detail": "DELETE /mcp requires an Mcp-Session-Id header."},
        )
    if not sessions.terminate(session_id):
        return JSONResponse(
            status_code=404,
            content={"error": "unknown_session", "detail": "No such MCP session."},
        )
    return Response(status_code=204, headers={"MCP-Protocol-Version": PROTOCOL_VERSION})


# --- Web companion ----------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
@app.get("/demo", response_class=HTMLResponse)
async def demo_ui() -> HTMLResponse:
    """Serves docs/index.html, the single companion document in this repository."""
    return HTMLResponse(content=load_companion_html())


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
