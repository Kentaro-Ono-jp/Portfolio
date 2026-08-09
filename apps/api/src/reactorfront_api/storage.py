from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import boto3
from botocore.config import Config

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

from reactorfront_api.domain import StoredObject


class S3ObjectStorage:
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
    ) -> S3ObjectStorage:
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
                ),
            )
        else:
            raise ValueError("Unsupported S3 mode.")
        return cls(client=client, bucket=bucket)

    def put(
        self,
        *,
        object_key: str,
        content: bytes,
        content_type: str,
        sha256: str,
    ) -> None:
        self._client.put_object(
            Bucket=self._bucket,
            Key=object_key,
            Body=content,
            ContentLength=len(content),
            ContentType=content_type,
            Metadata={"sha256": sha256},
        )

    def delete(self, *, object_key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=object_key)

    def get(self, *, object_key: str, maximum_bytes: int) -> StoredObject:
        response = self._client.get_object(Bucket=self._bucket, Key=object_key)
        body = response["Body"]
        try:
            content = body.read(maximum_bytes + 1)
        finally:
            body.close()
        if len(content) > maximum_bytes:
            raise ValueError("The stored source exceeds the supported size limit.")

        content_type = response.get("ContentType")
        content_length = response.get("ContentLength")
        metadata = response.get("Metadata") or {}
        if not isinstance(content_type, str) or not isinstance(content_length, int):
            raise ValueError("The stored source metadata is incomplete.")

        stored_sha256 = metadata.get("sha256")
        return StoredObject(
            content=content,
            content_type=content_type,
            size_bytes=content_length,
            sha256=stored_sha256 if isinstance(stored_sha256, str) else None,
        )

    def is_ready(self) -> bool:
        self._client.head_bucket(Bucket=self._bucket)
        return True
