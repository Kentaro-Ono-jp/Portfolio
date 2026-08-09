from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
LOCAL_S3_ENDPOINT_URL = "http://127.0.0.1:59000"
LOCAL_S3_ACCESS_KEY_ID = "portfolio-local-access"
LOCAL_S3_SECRET_ACCESS_KEY = "portfolio-local-secret"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="PORTFOLIO_",
        extra="ignore",
    )

    database_url: str = (
        "postgresql+psycopg://portfolio:portfolio-local-password@127.0.0.1:55432/portfolio"
    )
    s3_mode: Literal["local", "aws"] = "local"
    s3_endpoint_url: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: SecretStr | None = None
    s3_bucket: str = "portfolio-documents"
    s3_region: str = "us-east-1"
    rabbitmq_url: SecretStr = SecretStr(
        "amqp://portfolio:portfolio-local-password@127.0.0.1:55672/%2F"
    )
    rabbitmq_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    outbox_batch_size: int = Field(default=8, ge=1, le=100)
    outbox_lease_seconds: float = Field(default=30.0, gt=0, le=300)
    outbox_poll_seconds: float = Field(default=0.25, gt=0, le=30)
    outbox_retry_base_seconds: float = Field(default=1.0, gt=0, le=60)
    outbox_retry_max_seconds: float = Field(default=30.0, gt=0, le=300)
    events_prefetch_count: int = Field(default=1, ge=1, le=100)
    events_requeue_delay_seconds: float = Field(default=0.25, gt=0, le=5)
    events_reconnect_delay_seconds: float = Field(default=1.0, gt=0, le=30)
    oidc_issuer: str = "http://127.0.0.1:5556/dex"
    oidc_discovery_url: str = "http://127.0.0.1:5556/dex/.well-known/openid-configuration"
    oidc_jwks_url: str = "http://127.0.0.1:5556/dex/keys"
    oidc_audience: str = "reactorfront-api"
    oidc_allowed_algorithm: str = "RS256"
    oidc_jwks_cache_seconds: int = Field(default=300, ge=1, le=3600)
    oidc_clock_skew_seconds: int = Field(default=30, ge=0, le=300)
    oidc_http_timeout_seconds: float = Field(default=2.0, gt=0, le=10)
    oidc_mode: Literal["dex", "cognito"] = "dex"
    oidc_capability_claim: str = "groups"
    oidc_capability_mapping: dict[str, list[str]] = Field(
        default_factory=lambda: {
            "reactorfront-reviewers": [
                "documents:submit",
                "documents:read",
                "reviews:write",
                "audit:read",
            ]
        }
    )
    event_contract_directory: Path = REPOSITORY_ROOT / "packages" / "contracts" / "events"

    @model_validator(mode="after")
    def validate_managed_runtime_modes(self) -> Self:
        storage_fields = {
            "s3_endpoint_url",
            "s3_access_key_id",
            "s3_secret_access_key",
        }
        supplied_storage_fields = storage_fields & self.model_fields_set
        if self.s3_mode == "local" and not supplied_storage_fields:
            self.s3_endpoint_url = LOCAL_S3_ENDPOINT_URL
            self.s3_access_key_id = LOCAL_S3_ACCESS_KEY_ID
            self.s3_secret_access_key = SecretStr(LOCAL_S3_SECRET_ACCESS_KEY)
        secret = (
            self.s3_secret_access_key.get_secret_value()
            if self.s3_secret_access_key is not None
            else None
        )
        storage_values = (self.s3_endpoint_url, self.s3_access_key_id, secret)
        if self.s3_mode == "local" and not all(storage_values):
            raise ValueError("Local S3 mode requires endpoint and bounded credentials.")
        if self.s3_mode == "aws" and any(value is not None for value in storage_values):
            raise ValueError("AWS S3 mode forbids application-supplied endpoint or credentials.")
        expected_claim = "cognito:groups" if self.oidc_mode == "cognito" else "groups"
        if self.oidc_capability_claim != expected_claim:
            raise ValueError("OIDC capability claim does not match the selected provider mode.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
