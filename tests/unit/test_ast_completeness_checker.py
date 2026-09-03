"""
Unit tests for ASTGraphCompletenessChecker (Volcan).
"""

from src.domain.ast_completeness_checker import ASTGraphCompletenessChecker

def test_ast_checker_detects_clean_syntax():
    checker = ASTGraphCompletenessChecker()
    code = """
class AgentForge:
    def synthesize(self, prompt: str) -> str:
        return f"Synthesized: {prompt}"
"""
    res = checker.check_syntax_completeness(code)
    assert res.is_valid_ast is True
    assert res.class_count == 1
    assert res.function_count == 1

def test_ast_checker_flags_incomplete_syntax():
    checker = ASTGraphCompletenessChecker()
    bad_code = "def broken_func(x:\n    return x +"
    res = checker.check_syntax_completeness(bad_code)
    assert res.is_valid_ast is False
    assert "SyntaxError" in res.syntax_error_message
