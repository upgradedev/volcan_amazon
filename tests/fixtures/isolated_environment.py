"""Child test processes never inherit deploy credentials or app configuration."""
import os
from collections.abc import Mapping


def isolated_test_environment(
    overrides: Mapping[str, str] | None = None,
) -> dict[str, str]:
    env = {
        key: value for key, value in os.environ.items()
        if not key.upper().startswith(("AWS_", "BOTO_", "VOLCAN_"))
        and key.upper() not in ("GITHUB_TOKEN", "GH_TOKEN")
    }
    env.update(overrides or {})
    # Explicit fake-app settings are allowed, but credentials are not, even
    # through an override. Block file, process/SSO, web-identity, container
    # and instance-metadata providers, including the legacy boto config file.
    for key in list(env):
        if key.upper().startswith(("AWS_", "BOTO_")) and key.upper() not in (
            "AWS_REGION", "AWS_DEFAULT_REGION",
        ):
            del env[key]
        elif key.upper() in ("GITHUB_TOKEN", "GH_TOKEN"):
            del env[key]
    env.update({
        "AWS_SHARED_CREDENTIALS_FILE": os.devnull,
        "AWS_CONFIG_FILE": os.devnull,
        "BOTO_CONFIG": os.devnull,
        "AWS_EC2_METADATA_DISABLED": "true",
    })
    return env
