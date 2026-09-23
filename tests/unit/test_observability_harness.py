"""
Unit tests for Private Observability Harness in volcan_amazon.
Verifies local EMF structure and bounded telemetry, not deployed delivery or compliance.
"""

import json
import uuid

import pytest

from src.infrastructure.observability_harness import (
    MAX_EVENTS,
    METRIC_UNITS,
    TOOL_NAMES,
    PrivateObservabilityHarness,
)


def test_harness_initialization_and_emf_structure():
    harness = PrivateObservabilityHarness(request_id="test-req-123")
    harness.record_metric("ASTParseDurationMs", 42.5)
    
    payload = harness.build_emf_payload()
    assert payload["RequestId"] != "test-req-123"
    assert uuid.UUID(payload["RequestId"]).version == 4
    assert "ASTParseDurationMs" in payload
    assert payload["ASTParseDurationMs"] == 42.5
    assert "_aws" in payload
    assert payload["_aws"]["CloudWatchMetrics"][0]["Namespace"] == "Volcan/VoiceIDE"

def test_pii_sanitization():
    harness = PrivateObservabilityHarness()
    raw_text = "User test@example.com executed action with secret token 1234"
    masked = harness.mask_pii(raw_text)
    assert "test@example.com" not in masked
    assert "[REDACTED_PII]" in masked

def test_audit_event_logging():
    harness = PrivateObservabilityHarness()
    harness.add_audit_event("user@domain.com", "EXECUTE_ACTION", {"target": "resource-1", "email": "admin@domain.com"})
    harness.record_metric("BrailleStreamChunks", 1.0, "Count")
    
    output = harness.flush()
    parsed = json.loads(output)
    assert len(parsed["AuditEvents"]) == 1
    assert parsed["AuditEvents"][0]["action"] == "EXECUTE_ACTION"
    assert parsed["AuditEvents"][0]["actor"] == "[REDACTED_PII]"
    assert parsed["AuditEvents"][0]["details"] == {}


@pytest.mark.parametrize("secret", [
    "+30 210 1234567", "00302101234567", "(415) 555-0100", "+1-415-555-0100",
    "api_key=synthetic_demo_secret", "Bearer synthetic_access_token", "password: test-password",
    "eyJhbGciOiJIUzI1NiJ9.synthetic.signature", "opaque-synthetic-secret-no-keyword",
    "actor@example.invalid", "\u03ba\u03bb\u03b5\u03b9\u03b4\u03af=synthetic_secret",
])
def test_arbitrary_text_never_reaches_any_telemetry_field(secret, caplog, monkeypatch):
    monkeypatch.setenv("VOLCAN_ENVIRONMENT", secret)
    harness = PrivateObservabilityHarness(request_id=secret)
    harness.dimensions.update({"Tenant": secret, "ServiceName": secret, secret: secret})
    harness.metrics[secret] = 12.0
    harness.add_audit_event(secret, secret, {
        "tool": secret, "duration_ms": secret, secret: secret,
        "nested": {"phone": secret, "tokens": [secret]},
        "tenant": secret, "actor": secret, "action": secret,
    })
    assert harness.mask_pii(secret) == "[REDACTED_PII]"
    text = harness.flush()
    assert secret not in text
    assert secret not in "\n".join(r.getMessage() for r in caplog.records)
    body = json.loads(text)
    assert body["ServiceName"] == "volcan-voice-ide"
    assert body["Environment"] == "unknown"
    assert "Tenant" not in body
    assert body["AuditEvents"][0] == {
        "actor": "[REDACTED_PII]", "action": "UNCLASSIFIED", "details": {"tool": "unknown"},
    }


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, True, "1234",
                                   {"secret": "synthetic"}, ["synthetic"], 10**400])
def test_non_numeric_nonfinite_or_out_of_bounds_metrics_are_rejected(value):
    harness = PrivateObservabilityHarness()
    with pytest.raises(ValueError, match="finite number"):
        harness.record_metric("McpToolDurationMs", value)
    harness.metrics["McpToolDurationMs"] = value  # Older direct-mutation callers cannot bypass it.
    assert "McpToolDurationMs" not in harness.build_emf_payload()


def test_unknown_metric_names_and_wrong_units_are_rejected_without_echoing_them():
    harness = PrivateObservabilityHarness()
    with pytest.raises(ValueError, match="metric name is not allowed"):
        harness.record_metric("synthetic_metric_secret", 1)
    with pytest.raises(ValueError, match="metric unit does not match"):
        harness.record_metric("McpToolDurationMs", 1, "synthetic_unit_secret")
    assert "synthetic" not in harness.flush()


def test_emit_boundary_revalidates_mutated_events_nested_values_and_dimensions():
    harness = PrivateObservabilityHarness()
    harness.add_audit_event("mcp-client", "tools/call", {
        "tool": "digest_semantic_diff", "duration_ms": 12.5,
    })
    harness.audit_events[0]["details"]["extra"] = {"api_key": "synthetic_nested_secret"}
    harness.audit_events.append({"actor": {"email": "synthetic_email"},
                                "action": ["synthetic_action"],
                                "details": {"tool": {"secret": "synthetic_tool"},
                                            "duration_ms": {"value": "synthetic_value"}},
                                "tenant": "synthetic_tenant"})
    harness.dimensions["Environment"] = {"secret": "synthetic_env"}
    body = json.loads(harness.flush())
    assert "synthetic" not in json.dumps(body)
    assert body["AuditEvents"][0]["details"] == {"tool": "digest_semantic_diff", "duration_ms": 12.5}
    assert body["AuditEvents"][1]["details"] == {"tool": "unknown"}


def test_opaque_objects_are_never_stringified_and_events_are_bounded():
    class NeverStringify:
        def __str__(self):
            raise AssertionError("must not stringify application payloads")

    harness = PrivateObservabilityHarness()
    assert harness.mask_pii(NeverStringify()) == "[REDACTED_PII]"
    for _ in range(MAX_EVENTS + 3):
        harness.add_audit_event(NeverStringify(), NeverStringify(), {"tool": NeverStringify()})
    harness.audit_events.extend([None, NeverStringify(), {"extra": "synthetic"}])
    assert len(json.loads(harness.flush())["AuditEvents"]) == MAX_EVENTS


def test_legitimate_metrics_keep_cloudwatch_units_and_finite_dimension_cardinality(monkeypatch):
    monkeypatch.setenv("VOLCAN_ENVIRONMENT", "test")
    harness = PrivateObservabilityHarness()
    for name in METRIC_UNITS:
        harness.record_metric(name, 12.5)
    body = json.loads(harness.flush())
    directive = body["_aws"]["CloudWatchMetrics"][0]
    assert directive["Dimensions"] == [["ServiceName", "Environment"]]
    assert body["Environment"] == "test"
    assert {m["Name"]: m["Unit"] for m in directive["Metrics"]} == {
        **METRIC_UNITS, "TotalExecutionLatencyMs": "Milliseconds",
    }
    assert type(body["_aws"]["Timestamp"]) is int
    assert all(type(body[m["Name"]]) is float for m in directive["Metrics"])
    assert all(type(body[name]) is str for name in directive["Dimensions"][0])


def test_tool_labels_match_the_finite_registered_catalog():
    from src.interfaces.mcp_server import tool_registry
    assert TOOL_NAMES == set(tool_registry.names())
