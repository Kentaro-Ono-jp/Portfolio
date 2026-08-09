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
        env_prefix="PORTFOLIO_ML_",
        extra="ignore",
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
    model_artifact_path: Path = REPOSITORY_ROOT / "artifacts" / "model" / "model.json"
    model_checksum_path: Path = REPOSITORY_ROOT / "artifacts" / "model" / "model.sha256"
    promotion_manifest_path: Path = (
        REPOSITORY_ROOT / "apps" / "ml" / "evaluation" / "promoted-model-v1.json"
    )
    promotion_manifest_schema_path: Path = (
        REPOSITORY_ROOT / "apps" / "ml" / "evaluation" / "promoted-model-v1.schema.json"
    )
    evaluation_repository_root: Path = REPOSITORY_ROOT
    event_contract_directory: Path = REPOSITORY_ROOT / "packages" / "contracts" / "events"

    @model_validator(mode="after")
    def validate_storage_mode(self) -> Self:
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
        local_values = (self.s3_endpoint_url, self.s3_access_key_id, secret)
        if self.s3_mode == "local" and not all(local_values):
            raise ValueError("Local S3 mode requires endpoint and bounded credentials.")
        if self.s3_mode == "aws" and any(value is not None for value in local_values):
            raise ValueError("AWS S3 mode forbids application-supplied endpoint or credentials.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
