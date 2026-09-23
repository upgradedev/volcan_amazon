"""Approval-grant secret resolution without Terraform secret material.

Durable Lambda deployments receive only a Secrets Manager ARN. The value is
fetched once while the composition root initializes and is never returned by a
health endpoint or written to Terraform state.
"""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from typing import Any

MIN_SECRET_BYTES = 32


class SecretConfigurationError(RuntimeError):
    """The stable approval signing secret is unavailable or too weak."""


@dataclass(frozen=True)
class ApprovalSecret:
    value: bytes
    source: str


def load_approval_secret(
    *, durable: bool, client: Any | None = None
) -> ApprovalSecret:
    """Resolve the grant secret, failing closed in durable mode."""
    if durable:
        secret_arn = os.getenv("VOLCAN_APPROVAL_SECRET_ARN", "").strip()
        if not secret_arn:
            raise SecretConfigurationError(
                "VOLCAN_APPROVAL_SECRET_ARN is required when durable state is enabled."
            )
        if os.getenv("VOLCAN_APPROVAL_SECRET"):
            raise SecretConfigurationError(
                "Direct approval-secret environment values are forbidden in durable mode."
            )
        if client is None:
            import boto3

            client = boto3.client(
                "secretsmanager", region_name=os.getenv("AWS_REGION", "eu-west-1")
            )
        try:
            response = client.get_secret_value(SecretId=secret_arn)
            raw = response.get("SecretString")
        except Exception as exc:
            raise SecretConfigurationError(
                "The approval signing secret could not be resolved from Secrets Manager."
            ) from exc
        if not isinstance(raw, str):
            raise SecretConfigurationError(
                "The approval signing secret must be stored as SecretString."
            )
        value = raw.encode("utf-8")
        if len(value) < MIN_SECRET_BYTES:
            raise SecretConfigurationError(
                f"The approval signing secret must be at least {MIN_SECRET_BYTES} bytes."
            )
        return ApprovalSecret(value=value, source="secrets_manager")

    configured = os.getenv("VOLCAN_APPROVAL_SECRET")
    if configured is not None:
        value = configured.encode("utf-8")
        if len(value) < MIN_SECRET_BYTES:
            raise SecretConfigurationError(
                f"VOLCAN_APPROVAL_SECRET must be at least {MIN_SECRET_BYTES} bytes."
            )
        return ApprovalSecret(value=value, source="environment")
    return ApprovalSecret(value=secrets.token_bytes(MIN_SECRET_BYTES), source="ephemeral")
