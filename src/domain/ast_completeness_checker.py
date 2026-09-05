"""
AST Graph Completeness Checker for Volcan (CE Pattern).
Validates syntactic completeness of AST mutations before generating Braille diffs.
"""

import ast
from dataclasses import dataclass
from typing import Optional


@dataclass
class ASTSyntaxCheckResult:
    is_valid_ast: bool
    syntax_error_message: Optional[str] = None
    node_count: int = 0
    function_count: int = 0
    class_count: int = 0

class ASTGraphCompletenessChecker:
    """
    Parses and verifies Python syntax tree integrity.
    """
    
    def check_syntax_completeness(self, source_code: str) -> ASTSyntaxCheckResult:
        try:
            tree = ast.parse(source_code)
            nodes = list(ast.walk(tree))
            funcs = sum(1 for n in nodes if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
            classes = sum(1 for n in nodes if isinstance(n, ast.ClassDef))
            
            return ASTSyntaxCheckResult(
                is_valid_ast=True,
                node_count=len(nodes),
                function_count=funcs,
                class_count=classes
            )
        except SyntaxError as e:
            return ASTSyntaxCheckResult(
                is_valid_ast=False,
                syntax_error_message=f"SyntaxError at line {e.lineno}: {e.msg}"
            )
