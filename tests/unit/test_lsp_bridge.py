"""Unit tests for Volcan LSP Bridge."""
from src.interfaces.lsp_bridge import VolcanLspBridge


def test_lsp_braille_response_formatting():
    res = VolcanLspBridge.format_lsp_diagnostic("def count(): return 42", "⠙⠑⠋ ⠉⠕⠥⠝⠞")
    assert res.jsonrpc == "2.0"
    assert res.braille_stream == "⠙⠑⠋ ⠉⠕⠥⠝⠞"
    assert res.tactile_node_count == 4
