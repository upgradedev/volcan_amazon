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
* Capabilities: ``tools`` and ``resources``. Three tools declare an
  ``outputSchema`` and return ``structuredContent`` beside their text blocks
  (2025-11-25, server/tools, "Structured Content" and "Output Schema"). The
  resource methods are ``resources/list``, ``resources/read`` and an empty
  ``resources/templates/list``; there is no ``subscribe`` and no
  ``listChanged``. This server advertises no ``prompts``, ``logging``,
  ``completions`` or ``elicitation`` capability and answers those methods, and
  ``resources/subscribe``, with -32601, because it does not implement them.
* MCP Apps: the one resource is a ``ui://`` view in the format of the MCP Apps
  extension (SEP-1865, stable 2026-01-26), linked from a tool through
  ``_meta.ui.resourceUri``. The extension says a server SHOULD check the
  client's ``io.modelcontextprotocol/ui`` capability first. This server does
  not: a stateless deployment keeps no per-client memory between requests, so
  the link is always published, and a client without the extension ignores
  ``_meta`` and reads the text blocks.
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
#: The revisions this server honours. 2025-03-26 is not negotiated: it
#: requires a server to accept JSON-RPC batches, which this server refuses. A
#: client that asks for it is answered with PROTOCOL_VERSION, as the lifecycle
#: rule directs for a revision the server does not support.
SUPPORTED_PROTOCOL_VERSIONS = (PROTOCOL_VERSION, "2025-06-18")
#: The revision the transport specification (2025-11-25, Streamable HTTP,
#: "Protocol Version Header") tells a server to assume when a request after
#: initialize carries no MCP-Protocol-Version header and the server has no
#: other way to identify the version, such as the revision negotiated for the
#: session. Stateless deployments have no session to consult, so they use it.
ASSUMED_VERSION_WITHOUT_HEADER = "2025-03-26"
#: The revisions accepted after initialize, whether declared in the header or
#: resolved without one. This is the negotiable revisions plus 2025-03-26,
#: which is accepted here and never negotiated: initialize still answers
#: PROTOCOL_VERSION, the server still speaks it, and a JSON-RPC batch is still
#: refused with -32600. Amazon documents its Alexa+ MCP client asking for
#: 2025-03-26 and documents none of its headers; tools/list, tools/call and
#: ping have the same shape in 2025-03-26 as in the negotiated revisions.
ACCEPTED_VERSION_HEADERS = SUPPORTED_PROTOCOL_VERSIONS + ("2025-03-26",)

SERVER_NAME = "volcan-accessible-forge"
SERVER_VERSION = "0.1.0"

# JSON-RPC 2.0 error codes (JSON-RPC specification, section 5.1).
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
#: The resources page of revision 2025-11-25 ("Error Handling") names -32002
#: for a resource that does not exist.
RESOURCE_NOT_FOUND = -32002


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


@dataclass(frozen=True)
class ToolOutput:
    """What a tool with an ``outputSchema`` returns: its blocks and its data.

    ``structured`` becomes ``structuredContent``. The specification asks a
    tool that returns structured content to return the same JSON in a text
    block as well, for clients that predate the field; the handlers keep that
    block, and the speech text stays the first block.
    """

    content: list[dict[str, Any]]
    structured: dict[str, Any]


ToolHandler = Callable[[BaseModel], Awaitable["list[dict[str, Any]] | ToolOutput"]]


def _published_schema(model: type[BaseModel], mode: str = "validation") -> dict[str, Any]:
    schema = model.model_json_schema(mode=mode)
    schema.pop("title", None)
    return schema


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
    #: The model whose JSON Schema is published as ``outputSchema``. A tool
    #: that sets it returns ``ToolOutput`` from every successful call.
    output_model: type[BaseModel] | None = None
    #: Published as the tool's ``_meta``; MCP Apps reads ``_meta.ui`` here.
    meta: dict[str, Any] | None = None

    def output_schema(self) -> dict[str, Any] | None:
        if self.output_model is None:
            return None
        return _published_schema(self.output_model, mode="serialization")

    def to_catalog_entry(self) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "inputSchema": _published_schema(self.input_model),
        }
        output_schema = self.output_schema()
        if output_schema is not None:
            entry["outputSchema"] = output_schema
        if self.meta:
            entry["_meta"] = self.meta
        return entry


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


@dataclass(frozen=True)
class ResourceDefinition:
    """One entry of ``resources/list`` and what ``resources/read`` returns for it."""

    uri: str
    name: str
    title: str
    description: str
    mime_type: str
    read_text: Callable[[], str]
    #: Published as ``_meta`` on the read contents, where MCP Apps puts ``ui``.
    contents_meta: dict[str, Any] | None = None

    def to_listing(self) -> dict[str, Any]:
        return {
            "uri": self.uri,
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "mimeType": self.mime_type,
        }

    def to_contents(self) -> dict[str, Any]:
        contents: dict[str, Any] = {
            "uri": self.uri, "mimeType": self.mime_type, "text": self.read_text(),
        }
        if self.contents_meta:
            contents["_meta"] = self.contents_meta
        return contents


class ResourceRegistry:
    def __init__(self) -> None:
        self._resources: dict[str, ResourceDefinition] = {}

    def register(self, resource: ResourceDefinition) -> None:
        if resource.uri in self._resources:
            raise ValueError(f"Duplicate MCP resource URI: {resource.uri}")
        self._resources[resource.uri] = resource

    def get(self, uri: str) -> ResourceDefinition | None:
        return self._resources.get(uri)

    def listing(self) -> list[dict[str, Any]]:
        return [self._resources[uri].to_listing() for uri in sorted(self._resources)]

    def __len__(self) -> int:
        return len(self._resources)


class SessionRegistry:
    """Tracks the session identifiers this server actually issued.

    A session id the server never minted is not accepted, which is what lets
    the transport answer HTTP 404 for an unknown or terminated session. Each id
    keeps the revision negotiated at initialize, which is how the transport
    identifies the version of a request that omits MCP-Protocol-Version.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, str] = {}

    def create(self, negotiated_version: str = PROTOCOL_VERSION) -> str:
        session_id = secrets.token_urlsafe(32)
        self._sessions[session_id] = negotiated_version
        return session_id

    def exists(self, session_id: str) -> bool:
        return session_id in self._sessions

    def negotiated_version(self, session_id: str) -> str | None:
        return self._sessions.get(session_id)

    def terminate(self, session_id: str) -> bool:
        return self._sessions.pop(session_id, None) is not None

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
        resources: ResourceRegistry | None = None,
    ) -> None:
        self._registry = registry
        self._resources = resources if resources is not None else ResourceRegistry()
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

        if self._resources_enabled:
            if method == "resources/list":
                return DispatchOutcome(
                    body=self.result_response(request_id, {"resources": self._resources.listing()})
                )
            if method == "resources/templates/list":
                return DispatchOutcome(
                    body=self.result_response(request_id, {"resourceTemplates": []})
                )
            if method == "resources/read":
                return DispatchOutcome(
                    body=self.result_response(request_id, self._handle_resources_read(params))
                )

        raise JsonRpcError(
            METHOD_NOT_FOUND,
            f"Method '{method}' is not implemented by this server.",
            {"implemented": self.implemented_methods()},
        )

    @property
    def _resources_enabled(self) -> bool:
        return len(self._resources) > 0

    def implemented_methods(self) -> list[str]:
        methods = ["initialize", "ping", "tools/list", "tools/call"]
        if self._resources_enabled:
            methods += ["resources/list", "resources/read", "resources/templates/list"]
        return methods

    # -- methods -----------------------------------------------------------

    def _handle_initialize(self, params: dict[str, Any]) -> tuple[dict[str, Any], str]:
        requested = params.get("protocolVersion")
        if requested is not None and not isinstance(requested, str):
            raise JsonRpcError(INVALID_PARAMS, "'protocolVersion' must be a string.")
        # The lifecycle rule: a server that supports the requested revision
        # answers with that same revision, and otherwise names another one it
        # supports. A client asking for 2025-03-26, as Amazon documents its
        # Alexa+ MCP client doing, is answered 2025-11-25; a client that also
        # speaks 2025-11-25 then sends that revision's header and is served.
        negotiated = requested if requested in SUPPORTED_PROTOCOL_VERSIONS else PROTOCOL_VERSION

        capabilities: dict[str, Any] = {"tools": {"listChanged": False}}
        if self._resources_enabled:
            # Neither optional feature is offered: the one resource is fixed
            # when the server starts, so there is no change to announce.
            capabilities["resources"] = {"listChanged": False}
        result: dict[str, Any] = {
            "protocolVersion": negotiated,
            "capabilities": capabilities,
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

        if isinstance(content, ToolOutput):
            return {
                "content": content.content,
                "structuredContent": content.structured,
                "isError": False,
            }
        return {"content": content, "isError": False}

    def _handle_resources_read(self, params: dict[str, Any]) -> dict[str, Any]:
        uri = params.get("uri")
        if not isinstance(uri, str) or not uri:
            raise JsonRpcError(INVALID_PARAMS, "'uri' must be a non-empty resource URI.")
        resource = self._resources.get(uri)
        if resource is None:
            raise JsonRpcError(RESOURCE_NOT_FOUND, "Resource not found", {"uri": uri})
        return {"contents": [resource.to_contents()]}
