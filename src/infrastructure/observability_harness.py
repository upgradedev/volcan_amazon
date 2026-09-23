"""Bounded operational telemetry emitted through the application's Python logger.

Only an explicit metric/event schema reaches the EMF sink. Arbitrary content,
identities, tenant labels and nested details are not telemetry. This module does
not configure log shipping, prove CloudWatch delivery, or guarantee AWS costs.
"""
from __future__ import annotations

import json
import logging
import math
import os
import time
import uuid
from typing import Any

logger = logging.getLogger("volcan-voice-ide")
logger.setLevel(logging.INFO)

NAMESPACE = "Volcan/VoiceIDE"
SERVICE_NAME = "volcan-voice-ide"
REDACTED = "[REDACTED_PII]"
METRIC_UNITS = {
    "McpToolDurationMs": "Milliseconds",
    "ASTParseDurationMs": "Milliseconds",
    "BrailleStreamChunks": "Count",
}
ENVIRONMENTS = frozenset({"local", "test", "staging", "production-eu-west-1"})
ACTORS = frozenset({"mcp-client", "system"})
ACTIONS = frozenset({"tools/call", "EXECUTE_ACTION"})
TOOL_NAMES = frozenset({
    "digest_semantic_diff", "drill_down_section", "stage_governed_action",
    "confirm_governed_action", "play_earcon", "voice_turn", "review_dialogue_turn",
    "translate_text_to_braille", "braille_diff_digest", "process_switch_pulse",
    "get_haptic_profile", "check_ast_completeness",
})
MAX_EVENTS = 32
MAX_DURATION_MS = 86_400_000.0
MAX_COUNT = 1_000_000.0


def _label(value: Any, allowed: frozenset[str], fallback: str) -> str:
    # Do not stringify arbitrary objects or retain unknown keys/values.
    return value if type(value) is str and value in allowed else fallback


def _number(value: Any, maximum: float) -> float | None:
    if type(value) not in (int, float):
        return None
    try:
        numeric = float(value)
    except (ValueError, OverflowError):
        return None
    return numeric if math.isfinite(numeric) and 0 <= numeric <= maximum else None


def _event(actor: Any, action: Any, details: Any) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    if type(details) is dict:
        if "tool" in details:
            safe["tool"] = _label(details["tool"], TOOL_NAMES, "unknown")
        duration = _number(details.get("duration_ms"), MAX_DURATION_MS)
        if duration is not None:
            safe["duration_ms"] = duration
    return {
        "actor": _label(actor, ACTORS, REDACTED),
        "action": _label(action, ACTIONS, "UNCLASSIFIED"),
        "details": safe,
    }


class PrivateObservabilityHarness:
    """Build EMF metrics without accepting free-form log properties.

    The legacy request_id parameter remains accepted but is deliberately ignored:
    correlation is generated here, never copied from request bodies or identities.
    Mutable collections are revalidated at emission as well as at insertion.
    """

    NAMESPACE = NAMESPACE
    SERVICE_NAME = SERVICE_NAME

    def __init__(self, request_id: str | None = None):
        self._generated_request_id = str(uuid.uuid4())
        self.start_time = time.perf_counter()
        self.metrics: dict[str, float] = {}
        self.dimensions: dict[str, str] = {
            "ServiceName": SERVICE_NAME,
            "Environment": _label(os.environ.get("VOLCAN_ENVIRONMENT", "local"),
                                  ENVIRONMENTS, "unknown"),
        }
        self.audit_events: list[dict[str, Any]] = []

    @property
    def request_id(self) -> str:
        return self._generated_request_id

    def mask_pii(self, text: Any) -> str:
        """Legacy helper: omit the entire value, not a guessed regex subset.

        An opaque token or a person's name need not match a recognisable pattern.
        This is intentionally lossy and is not a general-purpose text redactor.
        """
        return REDACTED

    def record_metric(self, metric_name: str, value: float,
                      unit: str | None = None) -> PrivateObservabilityHarness:
        if type(metric_name) is not str or metric_name not in METRIC_UNITS:
            raise ValueError("metric name is not allowed")
        expected_unit = METRIC_UNITS[metric_name]
        if unit is not None and unit != expected_unit:
            raise ValueError("metric unit does not match the schema")
        number = _number(value, MAX_COUNT if expected_unit == "Count" else MAX_DURATION_MS)
        if number is None:
            raise ValueError("metric value must be a finite number within the schema bounds")
        self.metrics[metric_name] = number
        return self

    def add_audit_event(self, actor: str, action: str,
                        details: dict[str, Any]) -> PrivateObservabilityHarness:
        if len(self.audit_events) < MAX_EVENTS:
            self.audit_events.append(_event(actor, action, details))
        return self

    def build_emf_payload(self) -> dict[str, Any]:
        """Reconstruct the emitted object from the allowlist; never merge input dictionaries."""
        metrics = {}
        for name, unit in METRIC_UNITS.items():
            number = _number(self.metrics.get(name),
                             MAX_COUNT if unit == "Count" else MAX_DURATION_MS)
            if number is not None:
                metrics[name] = number
        elapsed = _number((time.perf_counter() - self.start_time) * 1000.0, MAX_DURATION_MS)
        if elapsed is not None:
            metrics["TotalExecutionLatencyMs"] = round(elapsed, 2)
        dimensions = {
            "ServiceName": SERVICE_NAME,
            "Environment": _label(self.dimensions.get("Environment"), ENVIRONMENTS, "unknown"),
        }
        # Only these fields survive even if an older caller mutates the public collections.
        events = [_event(e.get("actor"), e.get("action"), e.get("details"))
                  for e in self.audit_events[:MAX_EVENTS] if type(e) is dict]
        return {
            "_aws": {
                "Timestamp": int(time.time() * 1000),
                "CloudWatchMetrics": [{
                    "Namespace": NAMESPACE,
                    "Dimensions": [["ServiceName", "Environment"]],
                    "Metrics": [{"Name": name, "Unit": METRIC_UNITS.get(name, "Milliseconds")}
                                for name in metrics],
                }],
            },
            "RequestId": self._generated_request_id,
            **dimensions,
            **metrics,
            "AuditEvents": events,
        }

    def flush(self) -> str:
        """Emit one JSON log message; delivery depends on the deployment's log handler."""
        serialized = json.dumps(self.build_emf_payload(), allow_nan=False)
        logger.info(serialized)
        return serialized
