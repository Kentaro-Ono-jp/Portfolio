from __future__ import annotations

import pytest
from pydantic import ValidationError

from reactorfront_api.settings import Settings


def test_default_settings_keep_explicit_local_storage_and_dex() -> None:
    settings = Settings()

    assert settings.s3_mode == "local"
    assert settings.s3_endpoint_url == "http://127.0.0.1:59000"
    assert settings.oidc_mode == "dex"
    assert settings.oidc_capability_claim == "groups"


def test_aws_storage_mode_requires_the_standard_credential_chain() -> None:
    settings = Settings(s3_mode="aws")

    assert settings.s3_mode == "aws"
    assert settings.s3_endpoint_url is None
    assert settings.s3_access_key_id is None
    assert settings.s3_secret_access_key is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"s3_mode": "local", "s3_endpoint_url": None},
        {"s3_mode": "local", "s3_access_key_id": None},
        {"s3_mode": "local", "s3_secret_access_key": None},
        {"s3_mode": "aws", "s3_endpoint_url": "https://s3.example.invalid"},
        {"s3_mode": "aws", "s3_access_key_id": "static-key"},
        {"s3_mode": "aws", "s3_secret_access_key": "static-secret"},
    ],
)
def test_storage_mode_rejects_partial_or_mixed_configuration(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        Settings(**overrides)


def test_cognito_mode_requires_the_cognito_group_claim() -> None:
    settings = Settings(
        oidc_mode="cognito",
        oidc_capability_claim="cognito:groups",
    )
    assert settings.oidc_mode == "cognito"

    with pytest.raises(ValidationError):
        Settings(oidc_mode="cognito", oidc_capability_claim="groups")
