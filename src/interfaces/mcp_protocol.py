"""Interfaces Layer: Model Context Protocol (revision 2025-11-25) message layer.

This module implements the JSON-RPC 2.0 semantics of MCP by hand. It has no
dependency on any MCP SDK, and no dependency on FastAPI or Starlette either:
it takes a decoded JSON message and returns a decoded JSON response, so the
whole protocol is unit-testable without a transport.

The Streamable HTTP transport that carries these messages lives in
``src/interfaces/mcp_server.py``.

Scope and limits, stated plainly:

* Transport: Streamable HTTP only. Neither stdio nor the deprecated
  HTTP+SSE transport of revision 2024-11-05 is implemented.
* Capabilities: ``tools`` only. This server advertises no ``resources``,
  ``prompts``, ``logging``, ``completions`` or ``elicitation`` capability and
  answers those methods with -32601, because it does not implement them.
* Batching: a top-level JSON array is rejected with -32600. JSON-RPC batching
  was removed from MCP after revision 2025-03-26.
"""
import base64
import json
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

PROTOCOL_VERSION = "2025-11-25"
SUPPORTED_PROTOCOL_VERSIONS = (PROTOCOL_VERSION, "2025-06-18", "2025-03-26")

SERVER_NAME = "volcan-accessible-forge"
SERVER_VERSION = "0.1.0"

# JSON-RPC 2.0 error codes (JSON-RPC specification, section 5.1).
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


class JsonRpcError(Exception):
    """A JSON-RPC error that the dispatcher converts into an error response."""

    def __init__(self, code: int, message: str, data: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.data is not None:
            payload["data"] = self.data
        return payload


# --- MCP content blocks -----------------------------------------------------

def text_block(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


def json_block(payload: Any) -> dict[str, Any]:
    """A text block whose body is JSON, for machine-readable tool detail."""
    return {"type": "text", "text": json.dumps(payload, indent=2, sort_keys=True)}


def audio_block(raw_audio: bytes, mime_type: str = "audio/wav") -> dict[str, Any]:
    """An MCP audio content block.

    Volcan's earcons are the product, not decoration: a blind reviewer hears the
    result before any text is spoken. Returning them as a first-class audio
    block means an MCP client plays them without a side channel.
    """
    return {
        "type": "audio",
        "data": base64.b64encode(raw_audio).decode("ascii"),
        "mimeType": mime_type,
    }


ToolHandler = Callable[[BaseModel], Awaitable[list[dict[str, Any]]]]


@dataclass(frozen=True)
class ToolDefinition:
    """One entry of the MCP tool catalog.

    ``input_model`` is the same pydantic model the REST surface validates with,
    so ``inputSchema`` is generated from the code that actually parses the
    arguments and cannot drift away from it.
    """

    name: str
    title: str
    description: str
    input_model: type[BaseModel]
    handler: ToolHandler

    def to_catalog_entry(self) -> dict[str, Any]:
        schema = self.input_model.model_json_schema()
        schema.pop("title", None)
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "inputSchema": schema,
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Duplicate MCP tool name: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def catalog(self) -> list[dict[str, Any]]:
        return [self._tools[name].to_catalog_entry() for name in sorted(self._tools)]

    def names(self) -> list[str]:
        return sorted(self._tools)


class SessionRegistry:
    """Tracks the session identifiers this server actually issued.

    A session id the server never minted is not accepted, which is what lets
    the transport answer HTTP 404 for an unknown or terminated session.
    """

    def __init__(self) -> None:
        self._sessions: set[str] = set()

    def create(self) -> str:
        session_id = secrets.token_urlsafe(32)
        self._sessions.add(session_id)
        return session_id

    def exists(self, session_id: str) -> bool:
        return session_id in self._sessions

    def terminate(self, session_id: str) -> bool:
        if session_id in self._sessions:
            self._sessions.discard(session_id)
            return True
        return False

    @property
    def count(self) -> int:
        return len(self._sessions)


@dataclass
class DispatchOutcome:
    """What the transport should send back.

    ``body`` is ``None`` for a JSON-RPC notification, which by specification
    receives no response at all; the transport answers HTTP 202 in that case.
    """

    body: dict[str, Any] | None = None
    is_initialize: bool = False
    negotiated_version: str = PROTOCOL_VERSION
    tool_timings_ms: dict[str, float] = field(default_factory=dict)


class McpDispatcher:
    """Routes a decoded JSON-RPC message to an MCP method implementation."""

    def __init__(
        self,
        registry: ToolRegistry,
        server_name: str = SERVER_NAME,
        server_version: str = SERVER_VERSION,
        instructions: str | None = None,
    ) -> None:
        self._registry = registry
        self._server_name = server_name
        self._server_version = server_version
        self._instructions = instructions

    # -- envelope ----------------------------------------------------------

    @staticmethod
    def error_response(request_id: Any, error: JsonRpcError) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "error": error.to_payload()}

    @staticmethod
    def result_response(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    async def dispatch(self, message: Any) -> DispatchOutcome:
        if isinstance(message, list):
            raise JsonRpcError(
                INVALID_REQUEST,
                "Batched JSON-RPC arrays are not supported by MCP revision 2025-11-25.",
            )
        if not isinstance(message, dict):
            raise JsonRpcError(INVALID_REQUEST, "A JSON-RPC message must be a JSON object.")
        if message.get("jsonrpc") != "2.0":
            raise JsonRpcError(INVALID_REQUEST, "Field 'jsonrpc' must be exactly '2.0'.")

        method = message.get("method")
        if not isinstance(method, str) or not method:
            raise JsonRpcError(INVALID_REQUEST, "Field 'method' must be a non-empty string.")

        params = message.get("params", {})
        if params is None:
            params = {}
        if not isinstance(params, dict):
            raise JsonRpcError(INVALID_PARAMS, "Field 'params' must be a JSON object when present.")

        has_id = "id" in message
        request_id = message.get("id")

        # Notifications carry no id and by specification get no response body.
        if not has_id:
            if method.startswith("notifications/"):
                return DispatchOutcome(body=None)
            raise JsonRpcError(
                INVALID_REQUEST,
                f"Method '{method}' is a request and requires an 'id' field.",
            )

        if method == "initialize":
            result, negotiated = self._handle_initialize(params)
            return DispatchOutcome(
                body=self.result_response(request_id, result),
                is_initialize=True,
                negotiated_version=negotiated,
            )

        if method == "ping":
            return DispatchOutcome(body=self.result_response(request_id, {}))

        if method == "tools/list":
            return DispatchOutcome(
                body=self.result_response(request_id, {"tools": self._registry.catalog()})
            )

        if method == "tools/call":
            result = await self._handle_tools_call(params)
            return DispatchOutcome(body=self.result_response(request_id, result))

        raise JsonRpcError(
            METHOD_NOT_FOUND,
            f"Method '{method}' is not implemented by this server.",
            {"implemented": ["initialize", "ping", "tools/list", "tools/call"]},
        )

    # -- methods -----------------------------------------------------------

    def _handle_initialize(self, params: dict[str, Any]) -> tuple[dict[str, Any], str]:
        requested = params.get("protocolVersion")
        if requested is not None and not isinstance(requested, str):
            raise JsonRpcError(INVALID_PARAMS, "'protocolVersion' must be a string.")
        # The lifecycle rule: a server that supports the requested revision
        # answers with that same revision, and only otherwise names its own.
        # Volcan used to answer 2025-11-25 to everyone, so a client that asked
        # for 2025-03-26, as Amazon documents its Alexa+ MCP client doing, was
        # told a revision it had not asked for while this server accepted the
        # older one in its version header all along.
        negotiated = requested if requested in SUPPORTED_PROTOCOL_VERSIONS else PROTOCOL_VERSION

        result: dict[str, Any] = {
            "protocolVersion": negotiated,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": self._server_name, "version": self._server_version},
        }
        if self._instructions:
            result["instructions"] = self._instructions
        return result, negotiated

    async def _handle_tools_call(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        if not isinstance(name, str) or not name:
            raise JsonRpcError(INVALID_PARAMS, "'name' must be a non-empty tool name.")

        tool = self._registry.get(name)
        if tool is None:
            raise JsonRpcError(
                INVALID_PARAMS,
                f"Unknown tool '{name}'.",
                {"available": self._registry.names()},
            )

        arguments = params.get("arguments", {})
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            raise JsonRpcError(INVALID_PARAMS, "'arguments' must be a JSON object.")

        try:
            payload = tool.input_model(**arguments)
        except ValidationError as exc:
            raise JsonRpcError(
                INVALID_PARAMS,
                f"Arguments for tool '{name}' failed schema validation.",
                {"errors": json.loads(exc.json())},
            ) from exc

        # A tool that raises is a tool failure, not a transport failure: the
        # specification wants it reported inside the result with isError.
        try:
            content = await tool.handler(payload)
        except Exception as exc:  # noqa: BLE001 - surfaced to the model, not swallowed
            return {
                "content": [text_block(f"Tool '{name}' failed: {type(exc).__name__}: {exc}")],
                "isError": True,
            }

        return {"content": content, "isError": False}
