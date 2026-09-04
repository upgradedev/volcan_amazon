"""
Unit tests for ReversibleASTForgeEngine.
"""
from src.domain.reversible_ast_engine import ReversibleASTForgeEngine

def test_ast_snapshot_and_undo():
    engine = ReversibleASTForgeEngine()
    orig = {"nodes": [{"type": "function", "name": "authenticate"}]}
    synth = {"nodes": [{"type": "function", "name": "authenticate_kms"}]}
    
    snap = engine.record_synthesis_snapshot(
        snapshot_id="snap-01",
        original_ast=orig,
        synthesized_ast=synth,
        inverse_patch="--- auth_kms.py\n+++ auth.py"
    )
    assert snap.snapshot_id == "snap-01"
    
    result = engine.undo_last_synthesis()
    assert result["status"] == "ROLLBACK_SUCCESS"
    assert result["restored_ast"] == orig
    assert result["latency_ms"] < 50.0

def test_ast_undo_empty():
    engine = ReversibleASTForgeEngine()
    res = engine.undo_last_synthesis()
    assert res["status"] == "NOTHING_TO_UNDO"
