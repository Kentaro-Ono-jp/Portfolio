from __future__ import annotations

import pytest
from pydantic import ValidationError

from reactorfront_ml.settings import Settings


@pytest.fixture(autouse=True)
def isolate_storage_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "PORTFOLIO_ML_S3_ENDPOINT_URL",
        "PORTFOLIO_ML_S3_ACCESS_KEY_ID",
        "PORTFOLIO_ML_S3_SECRET_ACCESS_KEY",
    ):
        monkeypatch.delenv(name, raising=False)


def test_settings_have_no_database_boundary() -> None:
    settings = Settings()

    assert "database" not in " ".join(Settings.model_fields).lower()
    assert settings.rabbitmq_timeout_seconds == 5
    assert settings.s3_mode == "local"
    assert settings.s3_bucket == "portfolio-documents"
    assert settings.promotion_manifest_path.name == "promoted-model-v1.json"
    assert settings.promotion_manifest_schema_path.name == "promoted-model-v1.schema.json"


def test_aws_storage_mode_uses_no_application_credentials() -> None:
    settings = Settings(s3_mode="aws")

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
