"""The committed Lambda bridge and exact-revision health receipt."""
import asyncio
import importlib
import json
import re
from pathlib import Path

import pytest

from src.interfaces.lambda_handler import _make_receive, handler

ROOT = Path(__file__).resolve().parents[2]


def event(method: str, path: str) -> dict:
    return {
        "version": "2.0", "rawPath": path, "rawQueryString": "", "headers": {},
        "requestContext": {"domainName": "example.execute-api.eu-west-1.amazonaws.com",
                           "http": {"method": method, "path": path, "sourceIp": "203.0.113.10"}},
        "body": None, "isBase64Encoded": False,
    }


def test_terraform_handler_resolves_to_the_committed_callable():
    text = (ROOT / "infra" / "main.tf").read_text(encoding="utf-8")
    match = re.search(r'handler\s*=\s*"([^"]+)"', text)
    assert match
    module_name, _, function_name = match.group(1).rpartition(".")
    assert callable(getattr(importlib.import_module(module_name), function_name))
    assert module_name == "src.interfaces.lambda_handler"


def test_terraform_matches_the_mantle_client_and_browser_transport():
    text = (ROOT / "infra" / "main.tf").read_text(encoding="utf-8")
    quoted_literals = set(re.findall(r'"([^"]+)"', text))
    assert '"bedrock-mantle:CreateInference"' in text
    assert "bedrock:InvokeModel" not in quoted_literals
    assert "project/default" in text
    assert re.search(
        r'VOLCAN_ALLOWED_ORIGINS\s*=\s*"https://[^\"]+\.execute-api\.eu-west-1\.amazonaws\.com"',
        text,
    )


def test_terraform_wires_conditional_durable_state_and_a_stable_secret():
    text = (ROOT / "infra" / "main.tf").read_text(encoding="utf-8")
    assert 'resource "aws_dynamodb_table" "volcan_state"' in text
    assert 'billing_mode = "PAY_PER_REQUEST"' in text
    assert "point_in_time_recovery" in text and "server_side_encryption" in text
    assert "dynamodb:TransactWriteItems" in text
    assert "VOLCAN_STATE_TABLE" in text and "VOLCAN_APPROVAL_SECRET_ARN" in text
    assert 'variable "volcan_approval_secret_arn"' in text
    assert 'variable "volcan_approval_secret"' not in text
    assert not re.search(r"\bVOLCAN_APPROVAL_SECRET\s*=", text)
    assert '"secretsmanager:GetSecretValue"' in text
    assert "Resource = var.volcan_approval_secret_arn" in text
    assert 'allow_methods     = ["GET", "POST"]' in text


def test_default_durable_plan_does_not_grant_bedrock_mantle_permission():
    text = (ROOT / "infra" / "main.tf").read_text(encoding="utf-8")
    assert re.search(
        r'variable "enable_bedrock_mantle"\s*\{[^}]*default\s*=\s*false',
        text,
        re.DOTALL,
    )
    assert re.search(
        r'resource "aws_iam_policy" "volcan_bedrock_mantle"\s*\{\s*'
        r'count\s*=\s*var\.enable_bedrock_mantle \? 1 : 0',
        text,
    )
    core_policy = text.split(
        'resource "aws_iam_policy" "volcan_bedrock_mantle"', 1
    )[0].split('resource "aws_iam_policy" "volcan_serverless_policy"', 1)[1]
    assert "bedrock-mantle:CreateInference" not in core_policy


def test_health_runs_through_the_lambda_bridge_and_exposes_revision(monkeypatch):
    monkeypatch.setenv("SOURCE_REVISION", "abc123def456")
    response = handler(event("GET", "/health"))
    body = json.loads(response["body"])
    assert response["statusCode"] == 200
    assert body["service"] == "volcan-accessible-forge"
    assert body["source_revision"] == "abc123def456"
    assert body["durable_state"]["backend"] == "process_memory"
    assert body["durable_state"]["durable_across_restart"] is False


def test_unknown_path_is_a_404_response():
    assert handler(event("GET", "/not-a-route"))["statusCode"] == 404


def test_sse_stream_body_survives_the_lambda_bridge(monkeypatch):
    monkeypatch.setenv("VOLCAN_MCP_SESSION_MODE", "stateless")
    req = event("GET", "/mcp")
    req["headers"] = {"MCP-Protocol-Version": "2025-11-25"}
    response = handler(req)
    assert response["statusCode"] == 200
    assert response["headers"]["content-type"].startswith("text/event-stream")
    assert response["body"].startswith(": volcan mcp stream open (stateless)")


def test_bridge_receive_blocks_after_the_body_instead_of_a_bogus_disconnect():
    # Whether an immediate http.disconnect cancels a stream before its first
    # chunk is a scheduler race: it passed locally and failed on Lambda's
    # dependency set. This pins the contract instead of the race outcome.
    receive = _make_receive(b'{}')
    assert asyncio.run(receive()) == {"type": "http.request", "body": b"{}", "more_body": False}
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(asyncio.wait_for(receive(), timeout=0.5))
