"""The committed Lambda bridge and exact-revision health receipt."""
import importlib
import json
import re
from pathlib import Path

from src.interfaces.lambda_handler import handler

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


def test_health_runs_through_the_lambda_bridge_and_exposes_revision(monkeypatch):
    monkeypatch.setenv("SOURCE_REVISION", "abc123def456")
    response = handler(event("GET", "/health"))
    body = json.loads(response["body"])
    assert response["statusCode"] == 200
    assert body["service"] == "volcan-accessible-forge"
    assert body["source_revision"] == "abc123def456"


def test_unknown_path_is_a_404_response():
    assert handler(event("GET", "/not-a-route"))["statusCode"] == 404
