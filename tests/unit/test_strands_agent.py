"""Unit tests for AWS Strands SDK Agent Adapter."""
import pytest
from src.infrastructure.strands_agent_adapter import AWSStrandsAgentOrchestrator


def test_strands_agent_registration_and_execution():
    agent = AWSStrandsAgentOrchestrator(
        agent_name="volcan_coding_agent",
        system_prompt="You are an accessible voice coding assistant."
    )
    agent.register_tool(
        name="translate_braille",
        description="Translates AST diffs to Braille U+2800",
        parameters_schema={"type": "object", "properties": {"snippet": {"type": "string"}}}
    )

    res = agent.execute_turn("Please translate braille for my counter function")
    assert res.status == "COMPLETED"
    assert "translate_braille" in res.tools_called
    assert "Braille" in res.output_text
    assert res.model_provider == "AmazonBedrock_Strands_Pattern"


def test_strands_agent_rejects_empty_input():
    agent = AWSStrandsAgentOrchestrator("test_agent", "system prompt")
    with pytest.raises(ValueError, match="cannot be empty"):
        agent.execute_turn("   ")
