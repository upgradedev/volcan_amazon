"""Language Server Protocol (LSP) Bridge for Volcan Braille AST Engine."""
from dataclasses import dataclass
import json
from typing import Dict, List


@dataclass
class LspBrailleResponse:
    jsonrpc: str = "2.0"
    id: int = 1
    braille_stream: str = ""
    tactile_node_count: int = 0


class VolcanLspBridge:
    """Adapts Volcan's Braille AST engine to standard editor Language Server Protocol."""

    @classmethod
    def format_lsp_diagnostic(cls, code_snippet: str, braille_repr: str) -> LspBrailleResponse:
        return LspBrailleResponse(
            jsonrpc="2.0",
            id=1,
            braille_stream=braille_repr,
            tactile_node_count=len(code_snippet.split())
        )
