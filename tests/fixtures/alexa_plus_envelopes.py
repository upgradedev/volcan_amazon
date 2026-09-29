"""The Alexa+ MCP client's request bodies, as Amazon documents them.

Source: "Alexa+ MCP Client and App Lifecycle",
https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-client-lifecycle.html
(page dated Jul 10, 2026; fetched with curl on 2026-09-27).

``DOCUMENTED_INITIALIZE`` and ``DOCUMENTED_TOOL_CALL`` are copied from that page
field for field. The page shows request bodies only, never HTTP headers, so
which headers the real Alexa+ client sends is not documented there.

Two things here are not Amazon's text and are named as such:

* ``initialize(version)`` swaps the documented ``protocolVersion``
  (2025-03-26) for another one. The overview page,
  https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-overview.html
  (dated Aug 03, 2026), says Alexa+ supports revision 2025-11-25, so both
  versions are replayed.
* ``tool_call(...)`` keeps the documented envelope and id but swaps the example
  hotel-search tool for Volcan's ``digest_semantic_diff`` with Volcan's own
  arguments.

None of this has been sent by Alexa+. It is a local replay of documented shapes.
"""
import copy

SOURCE_URL = "https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-client-lifecycle.html"
FETCHED_ON = "2026-09-27"

DOCUMENTED_INITIALIZE = {
    "jsonrpc": "2.0",
    "method": "initialize",
    "id": "4e3bdaee-0",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {"roots": {"listChanged": True}},
        "clientInfo": {"name": "Alexa+ MCP Client", "version": "1.0.0"},
    },
}

DOCUMENTED_TOOL_CALL = {
    "jsonrpc": "2.0",
    "method": "tools/call",
    "id": "4a5bda6e-1",
    "params": {
        "name": "search_hotels",
        "arguments": {
            "checkIn": "2026-04-18",
            "destination": "Seattle",
            "guests": {"adults": 2},
            "checkOut": "2026-04-19",
        },
    },
}

#: The two protocol revisions Amazon's pages name for the Alexa+ client.
DOCUMENTED_VERSIONS = ("2025-03-26", "2025-11-25")

#: The patch on Volcan's first screen: the admin check inverted.
INVERTED_CHECK_PATCH = (
    "diff --git a/p.py b/p.py\n--- a/p.py\n+++ b/p.py\n@@ -1 +1 @@\n"
    '-    return user.role == "admin"\n'
    '+    return user.role != "admin"\n'
)


def initialize(protocol_version: str = "2025-03-26") -> dict:
    body = copy.deepcopy(DOCUMENTED_INITIALIZE)
    body["params"]["protocolVersion"] = protocol_version
    return body


def initialized_notification() -> dict:
    return {"jsonrpc": "2.0", "method": "notifications/initialized"}


def tools_list() -> dict:
    return {"jsonrpc": "2.0", "method": "tools/list", "id": "4e3bdaee-list", "params": {}}


def tool_call(name: str = "digest_semantic_diff", arguments: dict | None = None) -> dict:
    body = copy.deepcopy(DOCUMENTED_TOOL_CALL)
    body["params"]["name"] = name
    body["params"]["arguments"] = arguments if arguments is not None else {
        "raw_diff": INVERTED_CHECK_PATCH, "level": 0,
    }
    return body
