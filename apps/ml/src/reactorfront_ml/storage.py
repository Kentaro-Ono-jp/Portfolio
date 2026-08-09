from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from reactorfront_ml.domain import (
    PermanentProcessingError,
    ProcessingFailureCode,
    TransientProcessingError,
)

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


class S3SourceStorage:
    def __init__(self, *, client: S3Client, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    @classmethod
    def create(
        cls,
        *,
        mode: Literal["local", "aws"],
        endpoint_url: str | None,
        access_key_id: str | None,
        secret_access_key: str | None,
        bucket: str,
        region: str,
    ) -> S3SourceStorage:
        local_values = (endpoint_url, access_key_id, secret_access_key)
        if mode == "local":
            if not all(local_values):
                raise ValueError("Local S3 mode requires endpoint and bounded credentials.")
            client = boto3.client(
                "s3",
                endpoint_url=endpoint_url,
                aws_access_key_id=access_key_id,
                aws_secret_access_key=secret_access_key,
                region_name=region,
                config=Config(
                    signature_version="s3v4",
                    s3={"addressing_style": "path"},
                    retries={"max_attempts": 3, "mode": "standard"},
                    connect_timeout=3,
                    read_timeout=5,
                ),
            )
        elif mode == "aws":
            if any(value is not None for value in local_values):
                raise ValueError(
                    "AWS S3 mode forbids application-supplied endpoint or credentials."
                )
            client = boto3.client(
                "s3",
                region_name=region,
                config=Config(
                    signature_version="s3v4",
                    retries={"max_attempts": 3, "mode": "standard"},
                    connect_timeout=3,
                    read_timeout=5,
                ),
            )
        else:
            raise ValueError("Unsupported S3 mode.")
        return cls(client=client, bucket=bucket)

    def get(self, *, object_key: str) -> bytes:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=object_key)
            body = response["Body"].read()
        except ClientError as error:
            error_code = str(error.response.get("Error", {}).get("Code", ""))
            if error_code in {"404", "NoSuchKey", "NotFound"}:
                raise PermanentProcessingError(
                    code=ProcessingFailureCode.SOURCE_OBJECT_NOT_FOUND
                ) from None
            raise TransientProcessingError(code=ProcessingFailureCode.SOURCE_UNAVAILABLE) from None
        except BotoCoreError:
            raise TransientProcessingError(code=ProcessingFailureCode.SOURCE_UNAVAILABLE) from None
        if not isinstance(body, bytes):
            raise TransientProcessingError(code=ProcessingFailureCode.SOURCE_UNAVAILABLE)
        return body

    def is_ready(self) -> bool:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except (BotoCoreError, ClientError):
            return False
        return True
